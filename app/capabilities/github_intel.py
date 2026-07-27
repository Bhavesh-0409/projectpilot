"""
Project Intelligence capability — analyzes a GitHub repo via the free
REST API (5,000 req/hr with a personal access token) to produce a
health score, open-issue summary, and submission-readiness signal.
"""
import os
import requests
from datetime import datetime, timezone

GITHUB_API = "https://api.github.com"


def _headers():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _fetch_repo_data(repo: str) -> dict:
    """repo format: 'owner/name'"""
    base = f"{GITHUB_API}/repos/{repo}"
    repo_info = requests.get(base, headers=_headers()).json()
    issues = requests.get(f"{base}/issues", headers=_headers(), params={"state": "open", "per_page": 30}).json()
    commits = requests.get(f"{base}/commits", headers=_headers(), params={"per_page": 10}).json()
    return {"repo_info": repo_info, "issues": issues, "commits": commits}


def _health_score(data: dict) -> dict:
    """
    Deterministic, explainable scoring — NOT an LLM judgment call, because
    "does this repo have recent commits / open blockers" is exact and
    loggable, matching the Session 10 rule: use a deterministic check
    when the answer doesn't require subjective judgment.
    """
    issues = data.get("issues", [])
    commits = data.get("commits", [])
    repo_info = data.get("repo_info", {})

    if not isinstance(issues, list):
        issues = []
    if not isinstance(commits, list):
        commits = []

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


def github_node(state: dict) -> dict:
    repo = os.environ.get("GITHUB_REPO")
    if not repo:
        return {
            "github_result": {"error": "GITHUB_REPO not set in .env"},
            "trace": [{"node": "github", "error": "no repo configured"}],
        }

    data = _fetch_repo_data(repo)
    summary = _health_score(data)
    return {
        "github_result": summary,
        "trace": [{"node": "github", "summary": summary}],
    }
