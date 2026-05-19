import time
import json
from typing import Any

from .. import db

_mem_sessions: dict[str, list[dict[str, str]]] = {}
_mem_meta: dict[str, dict[str, Any]] = {}
_mem_ts: dict[str, float] = {}
SESSION_TTL = 3600

def _cleanup_mem() -> None:
    now = time.time()
    expired = [sid for sid, t in _mem_ts.items() if now - t > SESSION_TTL]
    for sid in expired:
        _mem_sessions.pop(sid, None)
        _mem_meta.pop(sid, None)
        _mem_ts.pop(sid, None)

class SessionStore:
    def __init__(self, service_type: str):
        self.service_type = service_type

    async def get_history(self, session_id: str | None) -> list[dict[str, str]]:
        if not session_id:
            return []
        if db.is_configured():
            row = await db.fetch_one("SELECT history FROM chat_sessions WHERE session_id = %s", (session_id,))
            if row and row.get("history"):
                hist = row["history"]
                if isinstance(hist, str):
                    try:
                        return json.loads(hist)
                    except Exception:
                        return []
                return hist
        _cleanup_mem()
        return list(_mem_sessions.get(session_id, []))

    async def get_meta(self, session_id: str | None) -> dict[str, Any]:
        if not session_id:
            return {}
        if db.is_configured():
            row = await db.fetch_one("SELECT metadata FROM chat_sessions WHERE session_id = %s", (session_id,))
            if row and row.get("metadata"):
                meta = row["metadata"]
                if isinstance(meta, str):
                    try:
                        return json.loads(meta)
                    except Exception:
                        return {}
                return meta
        _cleanup_mem()
        return dict(_mem_meta.get(session_id, {}))

    async def set_meta(self, session_id: str, updates: dict[str, Any]) -> None:
        if not session_id:
            return
        if db.is_configured():
            meta = await self.get_meta(session_id)
            meta.update(updates)
            await db.execute(
                """
                INSERT INTO chat_sessions (session_id, service_type, metadata)
                VALUES (%s, %s, %s)
                ON CONFLICT (session_id) DO UPDATE
                SET metadata = EXCLUDED.metadata, updated_at = NOW()
                """,
                (session_id, self.service_type, json.dumps(meta, default=str))
            )
            return
        
        if session_id not in _mem_meta:
            _mem_meta[session_id] = {}
        _mem_meta[session_id].update(updates)
        _mem_ts[session_id] = time.time()

    async def append_turn(self, session_id: str | None, user_msg: str, assistant_msg: str) -> None:
        if not session_id:
            return
        
        new_msgs = []
        if user_msg:
            new_msgs.append({"role": "user", "content": user_msg})
        if assistant_msg:
            new_msgs.append({"role": "assistant", "content": assistant_msg})
            
        if not new_msgs:
            return

        if db.is_configured():
            history = await self.get_history(session_id)
            history.extend(new_msgs)
            await db.execute(
                """
                INSERT INTO chat_sessions (session_id, service_type, history)
                VALUES (%s, %s, %s)
                ON CONFLICT (session_id) DO UPDATE
                SET history = EXCLUDED.history, updated_at = NOW()
                """,
                (session_id, self.service_type, json.dumps(history, default=str))
            )
            return

        if session_id not in _mem_sessions:
            _mem_sessions[session_id] = []
        _mem_sessions[session_id].extend(new_msgs)
        _mem_ts[session_id] = time.time()
        
    async def init_session(self, session_id: str, initial_meta: dict, initial_msg: str = "") -> None:
        if db.is_configured():
            history = [{"role": "assistant", "content": initial_msg}] if initial_msg else []
            await db.execute(
                """
                INSERT INTO chat_sessions (session_id, service_type, history, metadata)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (session_id) DO UPDATE
                SET history = EXCLUDED.history, metadata = EXCLUDED.metadata, updated_at = NOW()
                """,
                (session_id, self.service_type, json.dumps(history, default=str), json.dumps(initial_meta, default=str))
            )
            return
            
        _mem_sessions[session_id] = [{"role": "assistant", "content": initial_msg}] if initial_msg else []
        _mem_meta[session_id] = dict(initial_meta)
        _mem_ts[session_id] = time.time()
