"""
Engineering Design capability — generates artifacts (README sections,
Mermaid diagrams, summaries) using whatever context knowledge_result
and github_result already gathered in this run. This is what lets the
Agent "act" instead of only answering.
"""
from anthropic import Anthropic

ARTIFACT_PROMPT = """You are generating an engineering artifact for a software
project based on the context below. Match the artifact type to what the user
asked for (README section, Mermaid diagram, project summary, etc.).

If asked for a diagram, output valid Mermaid syntax in a ```mermaid code block.

User request: {query}

Context from project docs (RAG):
{knowledge_context}

Context from GitHub repo analysis:
{github_context}

Generate the artifact now."""


def artifact_node(state: dict) -> dict:
    knowledge = state.get("knowledge_result") or {}
    github = state.get("github_result") or {}

    prompt = ARTIFACT_PROMPT.format(
        query=state["user_query"],
        knowledge_context=knowledge.get("answer", "(none gathered)"),
        github_context=github if github else "(none gathered)",
    )

    client = Anthropic()
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    content = resp.content[0].text.strip()

    return {
        "artifact_result": {"content": content},
        "trace": [{"node": "artifact", "generated": True}],
    }
