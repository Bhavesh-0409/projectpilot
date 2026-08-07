"""
Reads projects.json (the registry of projects ProjectPilot can analyze)
and tracks which one is currently active in active_project.json. Read
fresh on every request by knowledge/github/artifact nodes, rather than
cached at startup — this is what makes project switching live (no
backend restart needed) rather than requiring a restart: each request
just reads a couple of small local JSON files, which is cheap and avoids
the staleness a startup-time cache would have.
"""
import json
import os

PROJECTS_FILE = os.path.join(os.path.dirname(__file__), "..", "projects.json")
ACTIVE_FILE = os.path.join(os.path.dirname(__file__), "..", "active_project.json")


def list_projects() -> dict:
    with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_active_project_id() -> str:
    projects = list_projects()
    if os.path.exists(ACTIVE_FILE):
        with open(ACTIVE_FILE, "r", encoding="utf-8") as f:
            active_id = json.load(f).get("active")
        if active_id in projects:
            return active_id
    # default: first project in the registry
    return next(iter(projects.keys()))


def get_active_project() -> dict:
    projects = list_projects()
    active_id = get_active_project_id()
    return {"id": active_id, **projects[active_id]}


def set_active_project(project_id: str) -> dict:
    projects = list_projects()
    if project_id not in projects:
        raise ValueError(f"Unknown project id: {project_id}. Known: {list(projects.keys())}")
    with open(ACTIVE_FILE, "w", encoding="utf-8") as f:
        json.dump({"active": project_id}, f)
    return get_active_project()
