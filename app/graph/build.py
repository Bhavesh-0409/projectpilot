"""
Wires all nodes into a LangGraph StateGraph with conditional routing:

    START -> scope_guard -> [reject]                    (if out of scope)
                          -> router -> (knowledge?) --\
                                    -> (github?)    ----+--> agent -> END
                                    -> (artifact?)  --/

A single query can fan out to multiple capability nodes (e.g. "are we
ready for submission?" -> knowledge + github), which is what makes this
an orchestrator rather than a single-tool chatbot.
"""
from langgraph.graph import StateGraph, END

from app.state import AgentState
from app.graph.scope_guard import scope_guard_node
from app.graph.router import router_node, route_condition
from app.graph.agent import agent_node, reject_node
from app.capabilities.knowledge import knowledge_node
from app.capabilities.github_intel import github_node
from app.capabilities.artifact import artifact_node


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("scope_guard", scope_guard_node)
    graph.add_node("router", router_node)
    graph.add_node("knowledge", knowledge_node)
    graph.add_node("github", github_node)
    graph.add_node("artifact", artifact_node)
    graph.add_node("agent", agent_node)
    graph.add_node("reject", reject_node)

    graph.set_entry_point("scope_guard")

    graph.add_conditional_edges(
        "scope_guard",
        lambda s: "router" if s.get("in_scope") else "reject",
        {"router": "router", "reject": "reject"},
    )

    # fan-out: route_condition returns a LIST of capability node names,
    # LangGraph runs all of them before continuing to "agent"
    graph.add_conditional_edges(
        "router",
        route_condition,
        {"knowledge": "knowledge", "github": "github", "artifact": "artifact"},
    )

    graph.add_edge("knowledge", "agent")
    graph.add_edge("github", "agent")
    graph.add_edge("artifact", "agent")
    graph.add_edge("agent", END)
    graph.add_edge("reject", END)

    return graph.compile()


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
