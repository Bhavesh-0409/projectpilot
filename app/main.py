"""
FastAPI backend. Run with:
    uvicorn app.main:app --reload
"""
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from pydantic import BaseModel

from app.graph.build import get_graph
from app.memory import store
from app import project_config

app = FastAPI(title="ProjectPilot AI")


class QueryRequest(BaseModel):
    query: str
    session_id: str = "default"


class QueryResponse(BaseModel):
    response: str
    required_capabilities: list
    trace: list


class SwitchProjectRequest(BaseModel):
    project_id: str
    session_id: str = "default"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/projects")
def list_projects():
    projects = project_config.list_projects()
    active_id = project_config.get_active_project_id()
    return {"projects": projects, "active": active_id}


@app.post("/projects/switch")
def switch_project(req: SwitchProjectRequest):
    try:
        active = project_config.set_active_project(req.project_id)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    store.clear_session(req.session_id)  # prevent old project's context leaking in
    return {"success": True, "active_project": active}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    graph = get_graph()

    history = store.get_history(req.session_id)
    state = {
        "user_query": req.query,
        "conversation_history": history,
        "last_artifact": store.get_last_artifact(req.session_id),
        "trace": [],
    }

    result = graph.invoke(state)

    store.append_turn(req.session_id, "user", req.query)
    store.append_turn(req.session_id, "assistant", result.get("final_response", ""))

    artifact_result = result.get("artifact_result")
    if artifact_result and artifact_result.get("content"):
        store.set_last_artifact(
            req.session_id,
            artifact_result.get("artifact_type", "readme_section"),
            artifact_result["content"],
        )

    return QueryResponse(
        response=result.get("final_response", ""),
        required_capabilities=result.get("required_capabilities", []),
        trace=result.get("trace", []),
    )
