"""
Project Intelligence capability - analyzes a GitHub repo via the free
REST API (5,000 req/hr with a personal access token).

Unlike the LangGraph-level routing (which decides WHICH capability module
to invoke), this module demonstrates real Anthropic tool-calling: Claude
is given separate tool definitions and decides, per query, which ones it
actually needs. Specific code-vs-doc checks can also read one allowed
source file by path.
"""
import base64
import json
import os
from datetime import datetime, timezone

import requests
from anthropic import Anthropic

from app.project_config import get_active_project

GITHUB_API = "https://api.github.com"
MAX_TOOL_ROUNDS = 4  # safety cap so a confused model can't loop forever
ALLOWED_READ_PREFIXES = ("app/", "frontend/")
BLOCKED_PATH_PATTERNS = (".env", "secret", "credential", ".git/", "config", ".pem", ".key")
MAX_FILE_CHARS = 8000


def _headers():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# --- Raw data fetchers: one per tool, each hits exactly one endpoint ---

def _fetch_open_issues(repo: str) -> list:
    url = f"{GITHUB_API}/repos/{repo}/issues"
    resp = requests.get(url, headers=_headers(), params={"state": "open", "per_page": 30})
    data = resp.json()
    return data if isinstance(data, list) else []


def _fetch_recent_commits(repo: str) -> list:
    url = f"{GITHUB_API}/repos/{repo}/commits"
    resp = requests.get(url, headers=_headers(), params={"per_page": 10})
    data = resp.json()
    return data if isinstance(data, list) else []


def _fetch_repo_metadata(repo: str) -> dict:
    url = f"{GITHUB_API}/repos/{repo}"
    resp = requests.get(url, headers=_headers())
    data = resp.json()
    return data if isinstance(data, dict) else {}


def _fetch_file_contents(repo: str, path: str) -> dict:
    normalized = (path or "").lstrip("/")
    lowered = normalized.lower()

    if not normalized.startswith(ALLOWED_READ_PREFIXES):
        return {
            "error": (
                f"Reads are restricted to {ALLOWED_READ_PREFIXES}. "
                f"'{path}' is out of scope."
            )
        }
    if any(pattern in lowered for pattern in BLOCKED_PATH_PATTERNS):
        return {
            "error": f"'{path}' matches a blocked pattern (secrets/config) and cannot be read."
        }

    url = f"{GITHUB_API}/repos/{repo}/contents/{normalized}"
    resp = requests.get(url, headers=_headers())

    if resp.status_code == 404:
        return {"error": f"File not found: '{normalized}'"}
    if resp.status_code >= 400:
        return {"error": f"GitHub API error {resp.status_code}: {resp.text[:300]}"}

    data = resp.json()
    if isinstance(data, list) or data.get("type") != "file":
        return {"error": f"'{normalized}' is not a file; directory reads are not supported."}

    encoded = data.get("content")
    encoding = data.get("encoding")
    if encoding != "base64" or not encoded:
        return {"error": f"Could not decode '{normalized}' from GitHub Contents API."}

    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        return {"error": f"Failed to decode '{normalized}': {exc}"}

    truncated = len(decoded) > MAX_FILE_CHARS
    if truncated:
        decoded = decoded[:MAX_FILE_CHARS]

    return {
        "path": normalized,
        "content": decoded,
        "truncated": truncated,
    }


# --- Tool schemas handed to Claude ---

TOOLS = [
    {
        "name": "get_open_issues",
        "description": "Fetch all currently open issues in the GitHub repo, including their labels. Use this for questions about blockers, bugs, backlog size, or what's outstanding.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_recent_commits",
        "description": "Fetch the 10 most recent commits to the repo's default branch. Use this for questions about recent activity, whether the project is actively being worked on, or commit history.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_repo_metadata",
        "description": "Fetch basic repo metadata: full name, default branch, description. Use this only if the query specifically needs repo identity or metadata info.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_file_contents",
        "description": "Read one specific known source file by path from the repo to verify whether code matches documentation or a user claim. Use only for a direct file-path lookup, not for searching or browsing the repo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Exact repo-relative file path to read, limited to approved source directories like app/ or frontend/.",
                }
            },
            "required": ["path"],
        },
    },
]

TOOL_DISPATCH = {
    "get_open_issues": lambda repo, _input=None: _fetch_open_issues(repo),
    "get_recent_commits": lambda repo, _input=None: _fetch_recent_commits(repo),
    "get_repo_metadata": lambda repo, _input=None: _fetch_repo_metadata(repo),
    "get_file_contents": lambda repo, tool_input=None: _fetch_file_contents(repo, (tool_input or {}).get("path", "")),
}


def _compute_health_score(issues: list, commits: list, repo_info: dict) -> dict:
    """
    Deterministic, explainable scoring - NOT an LLM judgment call. Only
    meaningful once both issues and commits have actually been gathered;
    callers should check both are present before trusting this.
    """
    open_issue_count = len([i for i in issues if "pull_request" not in i])
    blocker_labels = {"blocker", "bug", "critical"}
    blockers = [
        i for i in issues
        if "pull_request" not in i
        and any(lbl.get("name", "").lower() in blocker_labels for lbl in i.get("labels", []))
    ]

    days_since_last_commit = None
    if commits and isinstance(commits[0], dict):
        try:
            last_commit_date = commits[0]["commit"]["committer"]["date"]
            dt = datetime.fromisoformat(last_commit_date.replace("Z", "+00:00"))
            days_since_last_commit = (datetime.now(timezone.utc) - dt).days
        except (KeyError, TypeError):
            pass

    score = 100
    score -= min(open_issue_count * 3, 30)
    score -= len(blockers) * 10
    if days_since_last_commit is not None and days_since_last_commit > 7:
        score -= 15
    score = max(score, 0)

    return {
        "health_score": score,
        "open_issue_count": open_issue_count,
        "blocker_count": len(blockers),
        "blockers": [{"title": b.get("title"), "url": b.get("html_url")} for b in blockers],
        "days_since_last_commit": days_since_last_commit,
        "repo_name": repo_info.get("full_name"),
        "default_branch": repo_info.get("default_branch"),
    }


GITHUB_AGENT_PROMPT = """You are the Project Intelligence capability of
ProjectPilot AI. You have tools to inspect a GitHub repository. Given the
user's query below, call ONLY the tool(s) you actually need to answer it -
do not call a tool whose data the query doesn't require.

You may read one specific source file by exact path when the user names a
file or asks whether code still matches documentation. If the user has NOT
provided the exact repo-relative path, do NOT guess one and do NOT call
get_file_contents with a plausible-looking path. Instead, stop and say you need
the exact path (for example: app/graph/agent.py). You may NOT search, grep,
browse directories, or read files outside the tool's allowed source
directories.

User query: {query}

After you have the data you need, respond with a brief plain-text summary
of what you found (do not repeat raw JSON, just the key facts). If the
query is about status, progress, blockers, or priorities (not a narrow
factual lookup), end your summary with a short "Recommended next task:"
line - reason about which single open issue or gap deserves attention
first, based on the actual data you gathered (e.g. an unassigned
blocker-labeled issue with no activity outranks routine backlog items).
Do not invent a recommendation if you don't have enough data to support one."""


def github_node(state: dict) -> dict:
    active_project = get_active_project()
    repo = active_project.get("github_repo") or os.environ.get("GITHUB_REPO")
    if not repo:
        return {
            "github_result": {"error": "GITHUB_REPO not set in .env"},
            "trace": [{"node": "github", "error": "no repo configured"}],
        }

    client = Anthropic()
    messages = [{"role": "user", "content": GITHUB_AGENT_PROMPT.format(query=state["user_query"])}]

    gathered = {}
    tool_calls_made = []

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            break

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            tool_name = block.name
            tool_calls_made.append(tool_name)
            fetch_fn = TOOL_DISPATCH.get(tool_name)
            result_data = fetch_fn(repo, block.input) if fetch_fn else {"error": f"unknown tool {tool_name}"}
            gathered[tool_name] = result_data
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result_data)[:4000],
            })
        messages.append({"role": "user", "content": tool_results})

    final_text_blocks = [b.text for b in response.content if b.type == "text"]
    findings_summary = " ".join(final_text_blocks).strip()

    result = {
        "tools_called": tool_calls_made,
        "findings_summary": findings_summary,
    }

    if "get_open_issues" in gathered and "get_recent_commits" in gathered:
        repo_info = gathered.get("get_repo_metadata", {})
        result["health_score_data"] = _compute_health_score(
            issues=gathered["get_open_issues"],
            commits=gathered["get_recent_commits"],
            repo_info=repo_info,
        )

    return {
        "github_result": result,
        "trace": [{"node": "github", "tools_called": tool_calls_made, "result": result}],
    }
