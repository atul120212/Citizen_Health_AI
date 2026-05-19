"""
Voice-only agent router.

Endpoints:
  POST /api/session/start        — wake-word detected, start verification flow
  POST /api/session/summary      — get post-call summary for a session
  POST /api/voice/turn           — audio chunk → STT → LLM → TTS
"""
from fastapi import APIRouter, File, Form, UploadFile

from ..schemas import (
    SessionStartRequest,
    SessionStartResponse,
    SessionSummaryResponse,
    TextTurnRequest,
    VoiceTurnResponse,
)
from ..services.conversation import ConversationService

router = APIRouter(prefix="/api", tags=["voice"])
_svc = ConversationService()


@router.post("/session/start", response_model=SessionStartResponse)
async def session_start(payload: SessionStartRequest):
    """
    Called when the wake-word (hi / hello / namaste / namaskara / vanakkam) is detected.
    Returns a session_id and the agent's intro TTS audio asking for identity.
    """
    return await _svc.start_session(
        phone_number=payload.phone_number,
        language_code=payload.language_code or "en-IN",
    )


@router.post("/session/{session_id}/summary", response_model=SessionSummaryResponse)
async def session_summary(session_id: str):
    """
    Returns the post-call summary for a completed session.
    Called by the frontend after the user ends the call to display the summary card.
    """
    return await _svc.get_session_summary(session_id)


@router.post("/voice/text-turn", response_model=VoiceTurnResponse)
async def text_turn(payload: TextTurnRequest):
    """
    Text-based turn: skips STT, routes directly through LLM → optionally TTS.
    Used by tests and non-voice clients.
    """
    return await _svc.handle_text_turn(
        transcript=payload.text,
        phone_number=payload.phone_number,
        language_code=payload.language_code or "en-IN",
        session_id=payload.session_id,
    )


@router.post("/voice/turn", response_model=VoiceTurnResponse)
async def voice_turn(
    audio: UploadFile = File(...),
    phone_number: str | None = Form(default=None),
    session_id: str | None = Form(default=None),
):
    """
    Core voice turn:
      1. Read raw audio bytes
      2. STT via Sarvam
      3. Route through verification state machine or free conversation
      4. TTS the response
      5. Return transcript + intent + audio + actions
    """
    data = await audio.read()
    return await _svc.handle_audio_turn(
        audio=data,
        filename=audio.filename or "citizen-turn.webm",
        content_type=audio.content_type or "audio/webm",
        phone_number=phone_number,
        session_id=session_id,
    )
