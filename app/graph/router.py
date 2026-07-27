"""
Goal Interpreter + Router — decides WHAT the user wants and WHICH
capability node(s) must run to satisfy it. This is the piece that makes
ProjectPilot an orchestrator instead of a single-tool chatbot: a query
like "are we ready for submission?" should route to knowledge + github
together, not just one.
"""
import json
from anthropic import Anthropic

ROUTER_PROMPT = """You are the goal interpreter for ProjectPilot AI.

Available capabilities:
- "knowledge": answers grounded questions from project docs (README, SRS, design docs) via RAG
- "github": analyzes the GitHub repo (issues, commits, health score, blockers)
- "artifact": generates an engineering artifact (README section, Mermaid diagram) using
  whatever context the other capabilities gathered

Rules:
- A query can require MORE THAN ONE capability. E.g. "are we ready for submission?"
  needs both "knowledge" (do we meet the documented requirements) and "github"
  (is the implementation actually done) — list both.
- "artifact" should only be requested when the user explicitly wants something
  generated (a README, a diagram, a summary document), and it should usually be
  paired with knowledge and/or github so it has real content to work from.

User query: {query}

Respond with ONLY valid JSON:
{{"goal": "<one sentence restating what the user wants>",
  "required_capabilities": ["knowledge"|"github"|"artifact", ...]}}"""


def router_node(state: dict) -> dict:
    client = Anthropic()
    prompt = ROUTER_PROMPT.format(query=state["user_query"])

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].removeprefix("json").strip()

    try:
        decision = json.loads(raw)
    except json.JSONDecodeError:
        decision = {"goal": state["user_query"], "required_capabilities": ["knowledge"]}

    return {
        "goal": decision.get("goal", ""),
        "required_capabilities": decision.get("required_capabilities", []),
        "trace": [{"node": "router", "decision": decision}],
    }


def route_condition(state: dict) -> list:
    """
    Used by LangGraph's conditional edges to decide which capability
    node(s) to fan out to. Returns a list of node names to run.
    """
    if not state.get("in_scope", False):
        return ["reject"]
    caps = state.get("required_capabilities", [])
    return caps if caps else ["knowledge"]
