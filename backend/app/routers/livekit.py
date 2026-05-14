from fastapi import APIRouter, HTTPException

from ..schemas import LiveKitTokenRequest, LiveKitTokenResponse
from ..services.livekit_tokens import create_livekit_token

router = APIRouter(prefix="/api/livekit", tags=["livekit"])


@router.post("/token", response_model=LiveKitTokenResponse)
async def token(payload: LiveKitTokenRequest):
    try:
        jwt, url = create_livekit_token(payload.room_name, payload.participant_name, payload.metadata)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return LiveKitTokenResponse(token=jwt, url=url, room_name=payload.room_name)
