from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Citizen Health AI"
    environment: str = "local"
    api_base_url: str = "http://localhost:8000"
    frontend_origin: str = "http://localhost:3000"

    database_url: str | None = None

    sarvam_api_key: str | None = None
    sarvam_base_url: str = "https://api.sarvam.ai"
    sarvam_stt_model: str = "saaras:v3"
    sarvam_chat_model: str = "sarvam-30b"
    sarvam_tts_model: str = "bulbul:v3"
    sarvam_tts_speaker: str = "shubh"

    livekit_url: str | None = None
    livekit_api_key: str | None = None
    livekit_api_secret: str | None = None
    livekit_agent_name: str = "citizen-health-ai"

    pool_min_size: int = Field(default=1, ge=0)
    pool_max_size: int = Field(default=5, ge=1)

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
