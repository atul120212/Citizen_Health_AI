import json

from livekit import api

from ..config import get_settings


def create_livekit_token(
    room_name: str,
    participant_name: str,
    metadata: dict | None = None,
) -> tuple[str, str]:
    """Issue a room join JWT with automatic agent dispatch and participant metadata."""
    settings = get_settings()
    if not (settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret):
        raise RuntimeError("LiveKit credentials are not configured")

    meta = dict(metadata or {})
    meta.setdefault("room_name", room_name)

    grant = api.VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True,
    )

    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(participant_name)
        .with_name(participant_name)
        .with_metadata(json.dumps(meta, ensure_ascii=False))
        .with_grants(grant)
        .with_room_config(
            api.RoomConfiguration(
                agents=[
                    api.RoomAgentDispatch(
                        agent_name=settings.livekit_agent_name,
                        metadata=json.dumps(meta, ensure_ascii=False),
                    )
                ],
            )
        )
    )

    return token.to_jwt(), settings.livekit_url
