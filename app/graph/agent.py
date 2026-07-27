"""
Agent node — the reasoning layer. Combines whatever capability outputs
ran this turn into one coherent response. It does NOT own any API
directly (per the architecture doc: "It should not directly own APIs").
"""
from anthropic import Anthropic

SYNTH_PROMPT = """You are ProjectPilot AI, an engineering workflow orchestrator
(not a generic chatbot). Combine the results below into one clear, direct answer
to the user's original request. Reference concrete numbers/facts from the
results — don't restate them generically. If a capability returned an error or
no data, acknowledge the gap rather than inventing a value.

The system has EXACTLY three capabilities and no others: (1) knowledge — RAG over
project docs, (2) github — issue/commit/health analysis via the GitHub REST API,
(3) artifact — README/diagram generation. It CANNOT search or read source code
files, cannot access infrastructure/config files, and cannot take any write
action. If information genuinely isn't available from what these three
capabilities returned, say so plainly and stop there — do NOT suggest or imply
next steps involving capabilities the system doesn't have (e.g. "search the
codebase", "check the config files"), since that misrepresents what this system
can actually do.

Original request: {query}
Goal: {goal}

Knowledge (RAG) result: {knowledge}
GitHub Intelligence result: {github}
Generated artifact: {artifact}

Write the final response now."""


def agent_node(state: dict) -> dict:
    client = Anthropic()
    prompt = SYNTH_PROMPT.format(
        query=state["user_query"],
        goal=state.get("goal", ""),
        knowledge=state.get("knowledge_result") or "(not invoked)",
        github=state.get("github_result") or "(not invoked)",
        artifact=state.get("artifact_result") or "(not invoked)",
    )
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    return {
        "final_response": resp.content[0].text.strip(),
        "trace": [{"node": "agent", "synthesized": True}],
    }


def reject_node(state: dict) -> dict:
    """Runs when the scope guard blocks the request."""
    final_response = (
        "I can't help with that — it's outside what ProjectPilot AI does. "
        f"({state.get('scope_reason', 'out of scope')}) "
        "I can answer questions about your project docs, analyze your GitHub repo, "
        "or generate engineering artifacts like READMEs and diagrams."
    )
    return {
        "final_response": final_response,
        "trace": [{"node": "reject", "reason": state.get("scope_reason")}],
    }
