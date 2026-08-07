"""
Conversation memory — SQLite-backed per-session store. Same interface as
the old in-memory version, but state now lives in a file (memory_store.db)
instead of a RAM dict, so it survives process restarts/crashes.

Only conversation history and the last-generated artifact are persisted —
everything else in AgentState (in_scope, goal, knowledge_result, etc.) is
still rebuilt fresh per request in main.py, exactly as before. That's a
deliberate choice, not an oversight: those fields are per-turn scratch
data and persisting them would let a stale result from turn 1 leak into
turn 2 if a capability isn't invoked again.
"""
import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(os.environ.get("MEMORY_DB_PATH", str(Path(__file__).resolve().parent.parent.parent / "memory_store.db")))

MAX_TURNS_REMEMBERED = 10  # keep prompts small; trim oldest turns first

_lock = threading.Lock()  # FastAPI sync routes run in a threadpool; one
                           # shared sqlite3 connection needs serialized access


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            history_json TEXT NOT NULL DEFAULT '[]',
            last_artifact_json TEXT
        )
        """
    )
    conn.commit()
    return conn


_conn = _connect()


def _load_row(session_id: str):
    with _lock:
        cur = _conn.execute(
            "SELECT history_json, last_artifact_json FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        return cur.fetchone()


def set_last_artifact(session_id: str, artifact_type: str, content: str) -> None:
    """Cache the most recent artifact generated in a session, REGARDLESS of
    whether the user asked to save/commit it. This lets a later "push it"
    work even if the first request was only a preview."""
    payload = json.dumps({"artifact_type": artifact_type, "content": content})
    with _lock:
        _conn.execute(
            """INSERT INTO sessions (session_id, last_artifact_json) VALUES (?, ?)
               ON CONFLICT(session_id) DO UPDATE SET last_artifact_json = excluded.last_artifact_json""",
            (session_id, payload),
        )
        _conn.commit()


def clear_session(session_id: str) -> None:
    """Wipe a session's conversation history and last-artifact cache —
    used when switching projects, so stale context from the previous
    project can't leak into reasoning for the new one."""
    with _lock:
        _conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        _conn.commit()


def get_last_artifact(session_id: str) -> Optional[Dict[str, str]]:
    row = _load_row(session_id)
    if not row or not row[1]:
        return None
    return json.loads(row[1])


def get_history(session_id: str) -> List[Dict[str, str]]:
    row = _load_row(session_id)
    if not row:
        return []
    return json.loads(row[0])


def format_history(history: List[Dict[str, str]], max_turns: int = 6) -> str:
    """
    Renders the last few turns as plain text for inclusion in a prompt.
    Used by router/agent/artifact so the system can resolve follow-ups
    and references ("push that file", "what about that issue") instead
    of treating every query as if it arrived with no prior context.
    """
    recent = history[-max_turns:] if history else []
    if not recent:
        return "(no prior conversation this session)"
    lines = []
    for turn in recent:
        role = "User" if turn.get("role") == "user" else "Assistant"
        content = turn.get("content", "")
        if len(content) > 300:
            content = content[:300] + "..."
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def append_turn(session_id: str, role: str, content: str) -> None:
    history = get_history(session_id)
    history.append({"role": role, "content": content})
    if len(history) > MAX_TURNS_REMEMBERED * 2:
        history = history[-MAX_TURNS_REMEMBERED * 2:]
    with _lock:
        _conn.execute(
            """INSERT INTO sessions (session_id, history_json) VALUES (?, ?)
               ON CONFLICT(session_id) DO UPDATE SET history_json = excluded.history_json""",
            (session_id, json.dumps(history)),
        )
        _conn.commit()