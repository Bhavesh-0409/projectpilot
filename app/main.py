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

app = FastAPI(title="ProjectPilot AI")


class QueryRequest(BaseModel):
    query: str
    session_id: str = "default"


class QueryResponse(BaseModel):
    response: str
    required_capabilities: list
    trace: list


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    graph = get_graph()

    history = store.get_history(req.session_id)
    state = {
        "user_query": req.query,
        "conversation_history": history,
        "trace": [],
    }

    result = graph.invoke(state)

    store.append_turn(req.session_id, "user", req.query)
    store.append_turn(req.session_id, "assistant", result.get("final_response", ""))

    return QueryResponse(
        response=result.get("final_response", ""),
        required_capabilities=result.get("required_capabilities", []),
        trace=result.get("trace", []),
    )
