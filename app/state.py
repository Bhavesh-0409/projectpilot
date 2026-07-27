"""
Shared state that flows through every node in the LangGraph orchestrator.

Keeping this as a single typed dict is what lets the Router attach
capability outputs incrementally (one query can hit RAG *and* GitHub)
and lets the Agent node reason over everything at once.
"""
from typing import TypedDict, List, Optional, Literal, Dict, Any, Annotated
import operator


Capability = Literal["knowledge", "github", "artifact"]


class AgentState(TypedDict, total=False):
    # -- input --
    user_query: str
    conversation_history: List[Dict[str, str]]   # [{"role": "user"/"assistant", "content": "..."}]

    # -- scope guard --
    in_scope: bool
    scope_reason: str

    # -- goal interpreter --
    goal: str                        # plain-language restatement of what the user wants
    required_capabilities: List[Capability]

    # -- capability outputs (each node appends its own key, never overwrites another's) --
    knowledge_result: Optional[Dict[str, Any]]   # {"answer": ..., "citations": [...]}
    github_result: Optional[Dict[str, Any]]      # {"health_score": ..., "issues": [...], ...}
    artifact_result: Optional[Dict[str, Any]]    # {"type": "readme"/"diagram", "content": ...}

    # -- final reasoning --
    final_response: str

    # -- eval / observability hooks --
    # Annotated with operator.add so that when multiple capability nodes run
    # in parallel (fan-out from the router), each one's trace entry is
    # concatenated instead of conflicting on a single "last write wins" key.
    trace: Annotated[List[Dict[str, Any]], operator.add]
