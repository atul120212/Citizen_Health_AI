from fastapi import APIRouter, File, Form, UploadFile

from ..schemas import SessionStartRequest, SessionStartResponse, TextTurnRequest, VoiceTurnResponse
from ..services.conversation import ConversationService

router = APIRouter(prefix="/api", tags=["voice"])


@router.post("/session/start", response_model=SessionStartResponse)
async def session_start(payload: SessionStartRequest):
    """Start a new conversation session. Returns a session_id and the agent's
    intro TTS audio. Pass session_id in every subsequent turn so the agent
    maintains full conversation context."""
    service = ConversationService()
    return await service.start_session(
        phone_number=payload.phone_number,
        language_code=payload.language_code or "ta-IN",
    )


@router.post("/voice/turn", response_model=VoiceTurnResponse)
async def voice_turn(
    audio: UploadFile = File(...),
    phone_number: str | None = Form(default=None),
    session_id: str | None = Form(default=None),
):
    service = ConversationService()
    data = await audio.read()
    return await service.handle_audio_turn(
        audio=data,
        filename=audio.filename or "citizen-turn.webm",
        content_type=audio.content_type or "audio/webm",
        phone_number=phone_number,
        session_id=session_id,
    )


@router.post("/text/turn", response_model=VoiceTurnResponse)
async def text_turn(payload: TextTurnRequest):
    service = ConversationService()
    return await service.handle_text_turn(
        transcript=payload.text,
        language_code=payload.language_code or "ta-IN",
        phone_number=payload.phone_number,
        session_id=payload.session_id,
    )
