"""
Goal Interpreter + Router - decides WHAT the user wants and WHICH
capability node(s) must run to satisfy it. This is the piece that makes
ProjectPilot an orchestrator instead of a single-tool chatbot: a query
like "are we ready for submission?" should route to knowledge + github
together, not just one.
"""
import json

from anthropic import Anthropic

from app.memory.store import format_history

ROUTER_PROMPT = """You are the goal interpreter for ProjectPilot AI.

Available capabilities:
- "knowledge": answers grounded questions from project docs (README, SRS, design docs) via RAG
- "github": analyzes the GitHub repo (issues, commits, health score, blockers), can read one
  specifically named source file by exact path within app/ or frontend/ to compare code against
  documentation, and can recommend a specific prioritized next task based on real repo data -
  queries like "what should we work on next" or "what should I prioritize" ARE answerable via
  github, not ambiguous; do not send these to clarification
- "artifact": generates an engineering artifact (README section, Mermaid diagram) using
  whatever context the other capabilities gathered

Rules:
- A query can require MORE THAN ONE capability. E.g. "are we ready for submission?"
  needs both "knowledge" (do we meet the documented requirements) and "github"
  (is the implementation actually done) - list both.
- "artifact" should only be requested when the user explicitly wants something
  generated (a README, a diagram, a summary document), and it should usually be
  paired with knowledge and/or github so it has real content to work from. A
  requirement traceability matrix specifically ALWAYS needs both "knowledge"
  (to read the documented requirements) AND "github" (to check actual
  implementation state against them) - never route it with artifact alone.
- If the user names a specific source file path or asks whether a specific file
  still matches the docs or README, include "github" so it can read that one file.
  If the question is a code-vs-doc comparison, also include "knowledge".
- If the user asks to read, inspect, explain, or compare a source file but does
  NOT provide its exact repo-relative path, and that exact path is not clearly
  established earlier in the conversation, do NOT guess. Treat this as a
  clarification case immediately. Ask for the exact path directly, using a
  question like: "What's the exact path to that file? For example
  app/graph/agent.py." Basenames like "agent.py" or partial guesses are NOT
  exact paths.
- Phrases like "push this", "commit this", "save this", "push it to my repo"
  referring to something generated or shown earlier in the conversation ALSO require
  "artifact" - these are action requests on prior content, not new questions.
  Use the recent conversation to recognize this pattern even without the word
  "generate" appearing in the current query.
- Use the recent conversation below to resolve follow-ups and references (e.g.
  "what about that one" refers to something mentioned in a prior turn).
- If the query is GENUINELY too vague to route confidently even with the recent
  conversation as context (e.g. "is it done?", "how many?", "check this", with no
  clear referent) - do NOT guess a capability. Instead set needs_clarification
  to true and write a short, specific clarifying question. Do not use this for
  queries that are merely broad but answerable (e.g. "tell me about the project"
  is fine to route normally) - only for queries where guessing would likely
  produce a wrong or made-up answer.

Recent conversation (for resolving follow-ups and references):
{recent_conversation}

User query: {query}

Respond with ONLY valid JSON:
{{"needs_clarification": <true|false>,
  "clarification_question": "<specific question, or empty string if false>",
  "goal": "<one sentence restating what the user wants, or empty string if clarification needed>",
  "required_capabilities": ["knowledge"|"github"|"artifact", ...]}}

If the user is asking to read a source file but has not given an exact path,
set needs_clarification to true, leave required_capabilities empty, and ask for
the exact path. Zero guessing attempts."""


def router_node(state: dict) -> dict:
    client = Anthropic()
    prompt = ROUTER_PROMPT.format(
        query=state["user_query"],
        recent_conversation=format_history(state.get("conversation_history", [])),
    )

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
        decision = {
            "goal": state["user_query"],
            "required_capabilities": ["knowledge"],
            "needs_clarification": False,
            "clarification_question": "",
        }

    return {
        "goal": decision.get("goal", ""),
        "required_capabilities": decision.get("required_capabilities", []),
        "needs_clarification": decision.get("needs_clarification", False),
        "clarification_question": decision.get("clarification_question", ""),
        "trace": [{"node": "router", "decision": decision}],
    }
