"""
Agent node - the reasoning layer. Combines whatever capability outputs
ran this turn into one coherent response. It does NOT own any API
directly (per the architecture doc: "It should not directly own APIs").
"""
from anthropic import Anthropic

from app.memory.store import format_history

SYNTH_PROMPT = """You are ProjectPilot AI, an engineering workflow orchestrator
(not a generic chatbot). Combine the results below into one clear, direct answer
to the user's original request. Reference concrete numbers and facts from the
results - don't restate them generically. If a capability returned an error or
no data, acknowledge the gap rather than inventing a value.

The system has EXACTLY three capabilities and no others: (1) knowledge - RAG over
project docs, (2) github - issue/commit/health analysis via the GitHub REST API,
including the ability to read one specifically named source file by exact path
within app/ or frontend/ when needed to compare code against documentation, and
(3) artifact - generates engineering artifacts (README sections, architecture/API
docs, diagrams, etc.), and ONLY when the user explicitly asked to save or commit,
can write that artifact to a local file or as a real commit to the repo's
'generated/' folder specifically. It cannot search or grep across the repo,
cannot access infrastructure/config files, cannot modify GitHub issues/PRs, and
cannot write to any repo path outside 'generated/'. When asked to read a source
file and the exact repo-relative path has NOT been stated by the user or clearly
established earlier in the conversation, do NOT call the file-reading capability
with a guessed path. Instead, ask directly for the exact path (for example,
"What's the exact path to that file? For example app/graph/agent.py."). Only
read once a specific stated path is available: zero guessing attempts, and never
answer from memory about what the file probably contains. If information genuinely
isn't available from what these three capabilities returned, say so plainly and
stop there - do NOT suggest or imply next steps involving capabilities the system
doesn't have (e.g. "search the codebase", "check the config files").

If an artifact result includes a commit_result, clearly state whether the commit
succeeded or was refused (and why, if refused) - never imply an action happened
if it didn't.

If state includes an artifact_result, you MUST reflect what it actually contains
- do NOT rewrite, "clean up", or independently re-derive the artifact content
using other context (e.g. do not reconstruct a nicer diagram from the
knowledge/github results if the artifact's own content differs or failed).
Quote or closely paraphrase the artifact_result's actual "content" field. If
artifact_result has "generation_failed": true, you MUST say generation failed
and that nothing was written or committed - do not present a substitute you
invented instead.

Recent conversation (use this to stay coherent across turns, e.g. don't
re-introduce yourself or repeat context the user already has; reference
earlier turns naturally where relevant):
{recent_conversation}

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
        recent_conversation=format_history(state.get("conversation_history", [])),
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
        "I can't help with that - it's outside what ProjectPilot AI does. "
        f"({state.get('scope_reason', 'out of scope')}) "
        "I can answer questions about your project docs, analyze your GitHub repo, "
        "or generate engineering artifacts like READMEs and diagrams."
    )
    return {
        "final_response": final_response,
        "trace": [{"node": "reject", "reason": state.get("scope_reason")}],
    }


def clarify_node(state: dict) -> dict:
    """Runs when the router judged the query too ambiguous to route
    confidently. Asks the specific clarifying question instead of guessing
    a capability and risking a made-up answer."""
    question = state.get("clarification_question") or (
        "Could you clarify what you're asking? I can answer questions about "
        "your project docs, analyze your GitHub repo, or generate engineering "
        "artifacts like READMEs and diagrams."
    )
    return {
        "final_response": question,
        "trace": [{"node": "clarify", "question": question}],
    }
