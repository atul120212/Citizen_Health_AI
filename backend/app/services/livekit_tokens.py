from livekit import api

from ..config import get_settings


def create_livekit_token(room_name: str, participant_name: str, metadata: dict | None = None) -> tuple[str, str]:
    settings = get_settings()
    if not (settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret):
        raise RuntimeError("LiveKit credentials are not configured")

    grant = api.VideoGrants(room_join=True, room=room_name, can_publish=True, can_subscribe=True)
    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(participant_name)
        .with_name(participant_name)
        .with_grants(grant)
    )
    if metadata:
        token = token.with_metadata(__import__("json").dumps(metadata))
    return token.to_jwt(), settings.livekit_url
