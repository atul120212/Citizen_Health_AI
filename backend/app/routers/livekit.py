from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..schemas import LiveKitTokenRequest, LiveKitTokenResponse
from ..services.livekit_tokens import create_livekit_token

router = APIRouter(prefix="/api/livekit", tags=["livekit"])


@router.get("/health")
async def livekit_health():
    settings = get_settings()
    configured = bool(settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret)
    return {
        "configured": configured,
        "url": settings.livekit_url,
        "agent_name": settings.livekit_agent_name,
    }


@router.post("/token", response_model=LiveKitTokenResponse)
async def token(payload: LiveKitTokenRequest):
    try:
        jwt, url = create_livekit_token(payload.room_name, payload.participant_name, payload.metadata)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return LiveKitTokenResponse(
        token=jwt,
        url=url,
        room_name=payload.room_name,
        agent_name=get_settings().livekit_agent_name,
    )
