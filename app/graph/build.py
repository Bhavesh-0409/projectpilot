"""
Wires all nodes into a LangGraph StateGraph with conditional routing:

    START -> scope_guard -> [reject]                          (if out of scope)
                          -> router
                               -> (knowledge?) --\
                               -> (github?)    ----+--> gate --> (artifact?) --> agent -> END
                               -> (neither needed) -/

IMPORTANT ordering fix: knowledge and github MUST complete before artifact
runs, because artifact generation needs their results as grounding context.
Routing all three directly in parallel (the original design) meant artifact
always ran with empty context, since sibling nodes in the same LangGraph
step haven't written their results yet when the others start. The "gate"
node is a join point: knowledge/github (if selected) always finish first,
THEN gate decides whether to run artifact, THEN agent synthesizes.

A single query can still fan out to multiple capability nodes (e.g. "are we
ready for submission?" -> knowledge + github, in parallel with each other,
just not with artifact), which is what makes this an orchestrator rather
than a single-tool chatbot.
"""
from langgraph.graph import StateGraph, END

from app.state import AgentState
from app.graph.scope_guard import scope_guard_node
from app.graph.router import router_node
from app.graph.agent import agent_node, reject_node, clarify_node
from app.capabilities.knowledge import knowledge_node
from app.capabilities.github_intel import github_node
from app.capabilities.artifact import artifact_node


def _gather_condition(state: dict) -> list:
    """
    Router-level fan-out target: which of knowledge/github need to run
    BEFORE artifact (and before agent). If neither is needed (e.g. a
    standalone artifact request with no grounding capability requested),
    route straight to the gate so artifact still gets its turn. If the
    router judged the query too ambiguous to route confidently, skip
    everything and ask a clarifying question instead of guessing.
    """
    if not state.get("in_scope", False):
        return ["reject"]
    if state.get("needs_clarification", False):
        return ["clarify"]
    caps = set(state.get("required_capabilities", []) or ["knowledge"])
    targets = [c for c in caps if c in ("knowledge", "github")]
    return targets if targets else ["gate"]


def _gate_condition(state: dict) -> str:
    """After knowledge/github (if any) have finished, decide whether artifact needs to run."""
    caps = state.get("required_capabilities", []) or []
    return "artifact" if "artifact" in caps else "agent"


def _gate_node(state: dict) -> dict:
    """Trivial join/pass-through node — exists only to force knowledge and
    github to complete before anything downstream reads their results.
    LangGraph requires every node to write at least one channel, so we
    write a harmless empty update to trace rather than nothing."""
    return {"trace": []}


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("scope_guard", scope_guard_node)
    graph.add_node("router", router_node)
    graph.add_node("knowledge", knowledge_node)
    graph.add_node("github", github_node)
    graph.add_node("gate", _gate_node)
    graph.add_node("artifact", artifact_node)
    graph.add_node("agent", agent_node)
    graph.add_node("reject", reject_node)
    graph.add_node("clarify", clarify_node)

    graph.set_entry_point("scope_guard")

    graph.add_conditional_edges(
        "scope_guard",
        lambda s: "router" if s.get("in_scope") else "reject",
        {"router": "router", "reject": "reject"},
    )

    # fan-out ONLY knowledge/github here (or straight to gate/clarify)
    graph.add_conditional_edges(
        "router",
        _gather_condition,
        {"knowledge": "knowledge", "github": "github", "gate": "gate",
         "reject": "reject", "clarify": "clarify"},
    )

    # both knowledge and github converge at "gate" — LangGraph waits for
    # all incoming edges before running a node, so gate only runs once
    # whichever of knowledge/github were selected have both finished
    graph.add_edge("knowledge", "gate")
    graph.add_edge("github", "gate")

    # gate decides: does this query also need artifact generation?
    graph.add_conditional_edges(
        "gate",
        _gate_condition,
        {"artifact": "artifact", "agent": "agent"},
    )

    graph.add_edge("artifact", "agent")
    graph.add_edge("agent", END)
    graph.add_edge("reject", END)
    graph.add_edge("clarify", END)

    return graph.compile()


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
