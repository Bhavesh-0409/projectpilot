"""
Engineering Design capability — generates artifacts (README sections,
architecture docs, API docs, technical summaries, demo scripts,
presentation outlines, Mermaid diagrams) using whatever context
knowledge_result and github_result already gathered this turn.

Two independent, EXPLICIT-ONLY side effects can follow generation:
  - "save"   -> write the artifact to a local file under generated/
  - "commit" -> push it as a real commit to the configured GitHub repo
                (via github_write.py, restricted to generated/ only)

Neither ever fires unless the query clearly asks for it. The default is
"preview" — text only, no side effects — even for requests that sound
important or final.
"""
import os
import re
import json
from anthropic import Anthropic

from app.capabilities.github_write import commit_file_to_repo
from app.memory.store import format_history
from app.project_config import get_active_project

GENERATED_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "generated")

# artifact_type -> (human label used in prompts, default filename)
ARTIFACT_TYPES = {
    "readme_section": ("README section", "readme_section.md"),
    "architecture_doc": ("architecture/design document", "architecture_doc.md"),
    "api_documentation": ("API documentation", "api_documentation.md"),
    "technical_summary": ("technical summary", "technical_summary.md"),
    "demo_script": ("demo script", "demo_script.md"),
    "presentation_outline": ("presentation outline", "presentation_outline.md"),
    "diagram": ("Mermaid diagram", "diagram.mmd"),
    "traceability_matrix": ("requirement traceability matrix", "traceability_matrix.md"),
}

CLASSIFY_PROMPT = """Classify this artifact-generation request.

Recent conversation (use this to resolve references like "that file" or
"the one I saved earlier" to a specific artifact type mentioned previously):
{recent_conversation}

User query: {query}

artifact_type must be exactly one of: {types}

action_intent must be exactly one of:
- "preview"        - user wants to see/read NEW content only, no file action implied
- "save"           - user explicitly wants NEW content generated and saved as a file
- "commit"         - user explicitly wants NEW content generated AND committed to GitHub
- "commit_existing" - user is referring to something ALREADY generated/saved earlier
                       in this conversation (e.g. "push that file", "commit what I
                       saved", "commit the existing one") and wants THAT exact file
                       pushed as-is, NOT regenerated

Default to "preview" unless the query CLEARLY and explicitly asks for a save/commit
action. Use "commit_existing" only when the query refers to prior content rather
than asking for something new to be written.

Respond with ONLY valid JSON:
{{"artifact_type": "...", "action_intent": "preview"|"save"|"commit"|"commit_existing"}}"""

ARTIFACT_PROMPT = """You are a content-generation function, not a conversational
assistant. Your ONLY job is to output the raw {artifact_label} content itself —
nothing else.

Rules:
- Do NOT comment on your own capabilities, permissions, or limitations.
- Do NOT discuss whether you can or cannot commit files, access GitHub, or take
  actions — that is handled entirely by other parts of the system, not you.
- Do NOT refuse. If the context below is sparse, do the best possible job with
  what's given rather than declining or asking for more information.
- Ground the content in the SPECIFIC facts given below (real issue numbers,
  real health score, real doc content) rather than a generic template — a
  generic checklist that could apply to any project is a failure.
- If generating a diagram, output ONLY valid Mermaid syntax inside a ```mermaid
  code block, nothing else before or after it. Otherwise, write clear,
  well-structured Markdown.
- Diagrams specifically: use ONLY component/node names that actually appear in
  the docs context given (e.g. Scope Guard, Router/Goal Interpreter, Knowledge
  Management, Project Intelligence, Engineering Design/Artifact, Gate,
  Conversation Memory, Agent) — do not invent generic-sounding components
  ("Fan-Out Node", "Aggregator") that aren't the real documented names. Do NOT
  invent technology/providers not stated in the context (e.g. never say
  "OpenAI" or "Gemini" if the docs specify Claude/Anthropic — check the docs
  context for the actual stated tech before naming any technology). Do NOT
  embed live issue numbers or GitHub status annotations inside a structural
  diagram — an architecture diagram shows structure, not current status;
  keep those separate. Prefer a smaller, accurate diagram (aim for under 15
  nodes) over an elaborate one — do not add subgraphs or detail not grounded
  in the given context, and do not let the diagram get so large it risks
  being cut off.
- If generating a requirement traceability matrix, output a Markdown table
  with columns: Requirement (this MUST be an actual requirement statement
  from the docs context — e.g. quote or closely paraphrase a specific FR
  item like "FR4 — Repository intelligence" from requirements.md — NOT a
  paraphrase of a GitHub issue title; issues are evidence, not requirements),
  Status (Met / Partially Met / Not Met / No Evidence), Evidence (a specific
  real issue number, commit, or doc reference — never invent one), Gap Notes.
  If the docs context given doesn't actually contain requirements.md content,
  say so explicitly rather than inventing requirement rows from issue titles.

User request: {query}

Context from project docs (RAG):
{knowledge_context}

Context from GitHub repo analysis:
{github_context}

Output the {artifact_label} content now — content only, no preamble, no
meta-commentary."""

_REFUSAL_MARKERS = [
    "i don't have the ability", "i do not have the ability",
    "i'm an ai assistant", "i am an ai assistant",
    "i'm unable to", "i am unable to",
    "i cannot commit", "i can't commit",
    "i don't have access", "i do not have access",
    "please share your project details", "please provide more",
]


def _looks_like_refusal(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _REFUSAL_MARKERS)


def _generate_content(client: Anthropic, prompt: str) -> str:
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def _strip_code_fence(text: str) -> str:
    """
    A .mmd file must contain ONLY raw Mermaid syntax — no markdown ```
    fences. The generation prompt asks the model to wrap diagrams in a
    ```mermaid fence (useful for chat display), but that fence must be
    stripped before the content is ever written to disk or committed,
    or diagram renderers fail to recognize the file's contents.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = lines[1:]  # drop opening ``` or ```mermaid line
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]  # drop closing ```
        return "\n".join(lines).strip()
    return stripped


def _classify(query: str, conversation_history: list) -> dict:
    client = Anthropic()
    prompt = CLASSIFY_PROMPT.format(
        query=query,
        types=", ".join(ARTIFACT_TYPES.keys()),
        recent_conversation=format_history(conversation_history),
    )
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].removeprefix("json").strip()
    try:
        decision = json.loads(raw)
    except json.JSONDecodeError:
        decision = {}

    artifact_type = decision.get("artifact_type")
    if artifact_type not in ARTIFACT_TYPES:
        artifact_type = "readme_section"

    action_intent = decision.get("action_intent")
    if action_intent not in ("preview", "save", "commit", "commit_existing"):
        action_intent = "preview"

    return {"artifact_type": artifact_type, "action_intent": action_intent}


def _safe_filename(name: str) -> str:
    """Strip to a bare safe filename — no path separators, no traversal."""
    name = os.path.basename(name)
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    return name or "artifact.md"


def _write_local(filename: str, content: str, project_id: str) -> dict:
    # Namespaced by project id — without this, generating a README for
    # gesture_control then huffman would silently overwrite the same local
    # file, since GENERATED_DIR is one shared folder for this whole app
    # regardless of which project is active. GitHub commits don't have this
    # problem (each project has its own separate repo), only the local
    # on-disk copy does.
    project_dir = os.path.join(GENERATED_DIR, project_id)
    os.makedirs(project_dir, exist_ok=True)
    safe_name = _safe_filename(filename)
    full_path = os.path.join(project_dir, safe_name)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    return {"local_path": f"generated/{project_id}/{safe_name}"}


def artifact_node(state: dict) -> dict:
    query = state["user_query"]
    knowledge = state.get("knowledge_result") or {}
    github = state.get("github_result") or {}
    project_id = get_active_project()["id"]

    classification = _classify(query, state.get("conversation_history", []))
    artifact_type = classification["artifact_type"]
    action_intent = classification["action_intent"]
    artifact_label, default_filename = ARTIFACT_TYPES[artifact_type]

    if action_intent == "commit_existing":
        safe_name = _safe_filename(default_filename)
        full_path = os.path.join(GENERATED_DIR, project_id, safe_name)

        # PRIORITY ORDER MATTERS: check the session's own conversation-derived
        # cache FIRST. The local file under GENERATED_DIR/<project_id> is
        # still shared across every session working on the SAME project —
        # trusting it first risks pushing stale content left over from a
        # different conversation about the same project. The session cache
        # reflects what THIS conversation actually just discussed, so it's
        # the more trustworthy source of "that file" even though it's
        # checked second in code below only as a fallback.
        existing_content = None
        last_artifact = state.get("last_artifact")
        if last_artifact and last_artifact.get("content"):
            existing_content = last_artifact["content"]
            _write_local(default_filename, existing_content, project_id)  # persist/refresh the local copy to match
        elif os.path.exists(full_path):
            with open(full_path, "r", encoding="utf-8") as f:
                existing_content = f.read()

        if existing_content is None:
            result = {
                "artifact_type": artifact_type,
                "action_intent": action_intent,
                "error": f"No existing {artifact_label} found this session — generate one first.",
            }
        else:
            commit_result = commit_file_to_repo(
                path=f"generated/{safe_name}",
                content=existing_content,
                commit_message=f"Push existing {artifact_label} as-is (ProjectPilot AI)",
            )
            result = {
                "artifact_type": artifact_type,
                "action_intent": action_intent,
                "content": existing_content,
                "local_path": f"generated/{safe_name}",
                "commit_result": commit_result,
            }
        return {
            "artifact_result": result,
            "trace": [{"node": "artifact", "action_intent": action_intent, "pushed_existing": "commit_result" in result}],
        }

    prompt = ARTIFACT_PROMPT.format(
        artifact_label=artifact_label,
        query=query,
        knowledge_context=knowledge.get("answer", "(none gathered)"),
        github_context=github if github else "(none gathered)",
    )

    client = Anthropic()
    content = _generate_content(client, prompt)

    regenerated_after_refusal = False
    if _looks_like_refusal(content):
        # First attempt degraded into meta-commentary instead of real content.
        # Retry once with an explicit corrective instruction before this ever
        # reaches disk or GitHub — never write/commit a refusal.
        corrective_prompt = prompt + (
            "\n\nIMPORTANT: your previous attempt incorrectly discussed your own "
            "capabilities instead of producing content. Do not do that. Output "
            "ONLY the artifact content itself, starting now."
        )
        content = _generate_content(client, corrective_prompt)
        regenerated_after_refusal = True

    result = {
        "artifact_type": artifact_type,
        "action_intent": action_intent,
        "content": content,
        "looked_like_refusal_initially": regenerated_after_refusal,
    }

    still_broken = _looks_like_refusal(content)

    if artifact_type == "diagram" and not still_broken:
        content = _strip_code_fence(content)

    if still_broken:
        result["generation_failed"] = True
    else:
        if action_intent in ("save", "commit"):
            result.update(_write_local(default_filename, content, project_id))

        if action_intent == "commit":
            safe_name = _safe_filename(default_filename)
            commit_result = commit_file_to_repo(
                path=f"generated/{safe_name}",
                content=content,
                commit_message=f"Add {artifact_label} (generated by ProjectPilot AI)",
            )
            result["commit_result"] = commit_result

    return {
        "artifact_result": result,
        "trace": [{
            "node": "artifact",
            "artifact_type": artifact_type,
            "action_intent": action_intent,
            "regenerated_after_refusal": regenerated_after_refusal,
            "generation_failed": still_broken,
            "wrote_local": "local_path" in result,
            "committed": action_intent == "commit" and not still_broken,
        }],
    }
