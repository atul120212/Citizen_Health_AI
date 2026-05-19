"""
Health Worker AI Router — /api/health-worker/*

Endpoints:
  POST /api/health-worker/session/start   — start a new worker session
  POST /api/health-worker/turn            — text turn (protocol / record / referral)
  POST /api/health-worker/voice-turn      — audio turn (STT → turn)
  GET  /api/health-worker/session/{id}    — session summary
"""

from fastapi import APIRouter, File, Form, UploadFile, Depends
from pydantic import BaseModel

from ..auth import verify_admin
from ..services.health_worker_service import HealthWorkerService

router = APIRouter(prefix="/api/health-worker", tags=["health-worker"], dependencies=[Depends(verify_admin)])
_svc = HealthWorkerService()


class SessionStartRequest(BaseModel):
    language_code: str = "en-IN"
    worker_role: str = "asha"


class TurnRequest(BaseModel):
    text: str
    language_code: str = "en-IN"
    session_id: str | None = None
    worker_role: str = "asha"


@router.post("/session/start")
async def session_start(payload: SessionStartRequest):
    return await _svc.start_session(payload.language_code, payload.worker_role)


@router.post("/turn")
async def text_turn(payload: TurnRequest):
    return await _svc.handle_turn(
        payload.text, payload.language_code, payload.session_id, payload.worker_role
    )


@router.post("/voice-turn")
async def voice_turn(
    audio: UploadFile = File(...),
    session_id: str | None = Form(default=None),
    worker_role: str = Form(default="asha"),
):
    data = await audio.read()
    return await _svc.handle_audio_turn(
        audio=data,
        filename=audio.filename or "worker-turn.webm",
        content_type=audio.content_type or "audio/webm",
        session_id=session_id,
        worker_role=worker_role,
    )


@router.get("/session/{session_id}")
async def session_summary(session_id: str):
    return await _svc.get_session_summary(session_id)


@router.get("/live-requests")
async def get_live_requests():
    """Fetches active citizen sessions that need immediate doctor intervention."""
    from .. import db
    if not db.is_configured():
        return {"requests": []}
    
    # Fetch sessions updated in the last 10 minutes that have needs_worker_followup = true
    # We use chat_sessions table
    rows = await db.fetch_all(
        """
        SELECT session_id, metadata, updated_at
        FROM chat_sessions
        WHERE service_type = 'citizen'
          AND metadata->>'needs_worker_followup' = 'true'
          AND updated_at > NOW() - INTERVAL '10 minutes'
        ORDER BY updated_at DESC
        """
    )
    
    requests = []
    for row in rows:
        meta = row.get("metadata") or {}
        # Extract patient name and reason if available in meta
        requests.append({
            "session_id": row["session_id"],
            "patient_name": meta.get("patient_name") or "Unknown Patient",
            "reason": meta.get("appointment_reason") or "High Risk Triage",
            "last_active": row["updated_at"].isoformat()
        })
        
    return {"requests": requests}


@router.get("/leaderboard")
async def get_leaderboard(role: str | None = None):
    """Fetches top performing health workers for the gamification leaderboard."""
    from .. import db
    if not db.is_configured():
        return {"leaderboard": []}
    
    query = "SELECT * FROM worker_performance"
    params = []
    if role:
        query += " WHERE role = %s"
        params.append(role)
    
    query += " ORDER BY performance_score DESC LIMIT 10"
    
    rows = await db.fetch_all(query, tuple(params))
    return {"leaderboard": rows}


@router.get("/outreach-tasks")
async def get_outreach_tasks():
    """Fetches list of patients requiring proactive follow-up (missed meds/vitals)."""
    from ..services.outreach_service import OutreachService
    svc = OutreachService()
    tasks = await svc.get_pending_interventions()
    return {"tasks": tasks}
