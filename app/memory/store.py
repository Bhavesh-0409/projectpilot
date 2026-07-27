"""
Conversation memory — in-memory per-session store. Simple by design for
a 2-week capstone; swap for LangGraph's SqliteSaver checkpointer later
if you want persistence across restarts (see comment below).
"""
from typing import Dict, List

_sessions: Dict[str, List[Dict[str, str]]] = {}

MAX_TURNS_REMEMBERED = 10  # keep prompts small; trim oldest turns first


def get_history(session_id: str) -> List[Dict[str, str]]:
    return _sessions.get(session_id, [])


def append_turn(session_id: str, role: str, content: str) -> None:
    history = _sessions.setdefault(session_id, [])
    history.append({"role": role, "content": content})
    if len(history) > MAX_TURNS_REMEMBERED * 2:
        _sessions[session_id] = history[-MAX_TURNS_REMEMBERED * 2:]


# --- To upgrade to persistent memory later ---
# from langgraph.checkpoint.sqlite import SqliteSaver
# checkpointer = SqliteSaver.from_conn_string("memory.db")
# pass `checkpointer=checkpointer` into graph.compile() and a thread_id
# per session in the config — this gives you full LangGraph-native
# state checkpointing instead of the hand-rolled store above.
