"""
The ONLY module in this project that writes to GitHub. Kept deliberately
separate from github_intel.py (read-only) so the write path is small,
isolated, and easy to audit on its own.

Hard safety rule, enforced in code (not just prompted): this can ONLY
ever write inside the 'generated/' folder of the configured repo. Any
other path is refused before any API call is made.
"""
import os
import base64
import requests

from app.capabilities.github_intel import GITHUB_API, _headers
from app.project_config import get_active_project

ALLOWED_PREFIX = "generated/"


def commit_file_to_repo(path: str, content: str, commit_message: str) -> dict:
    """
    Creates or updates a file at `path` in the configured GITHUB_REPO via
    the GitHub Contents API. `path` MUST start with 'generated/' — this is
    checked here, in code, before any network call, not left to the LLM
    to self-police.
    """
    if not path.startswith(ALLOWED_PREFIX):
        return {
            "success": False,
            "error": f"Refused: path '{path}' is outside the allowed '{ALLOWED_PREFIX}' folder. "
                     f"This system will only ever write inside '{ALLOWED_PREFIX}'.",
        }

    repo = os.environ.get("GITHUB_REPO") or get_active_project().get("github_repo")
    if not repo:
        return {"success": False, "error": "No active project's github_repo configured"}

    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
    headers = _headers()

    # Check whether the file already exists so we can update it correctly
    # (GitHub's Contents API requires the current file's sha to overwrite it).
    existing = requests.get(url, headers=headers)
    sha = existing.json().get("sha") if existing.status_code == 200 else None

    payload = {
        "message": commit_message,
        "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
    }
    if sha:
        payload["sha"] = sha

    resp = requests.put(url, headers=headers, json=payload)

    if resp.status_code in (200, 201):
        data = resp.json()
        return {
            "success": True,
            "path": path,
            "commit_sha": data.get("commit", {}).get("sha"),
            "commit_url": data.get("commit", {}).get("html_url"),
        }
    return {
        "success": False,
        "error": f"GitHub API error {resp.status_code}: {resp.text[:300]}",
    }
