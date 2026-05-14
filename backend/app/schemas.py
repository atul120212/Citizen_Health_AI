from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


LanguageCode = Literal["ta-IN", "kn-IN", "en-IN"]


class CitizenUpsert(BaseModel):
    phone_number: str = Field(min_length=8, max_length=15)
    full_name: str | None = None
    abha_id: str | None = None
    preferred_language: str = "ta"
    district_name: str | None = None
    phc_name: str | None = None
    village_taluka: str | None = None


class AppointmentCreate(BaseModel):
    citizen_id: str
    worker_id: str | None = None
    appointment_date: datetime
    reason: str


class SessionStartRequest(BaseModel):
    phone_number: str | None = None
    language_code: str | None = None


class SessionStartResponse(BaseModel):
    session_id: str
    intro_text: str
    audio_base64: str | None = None
    audio_mime_type: str = "audio/wav"


class TextTurnRequest(BaseModel):
    text: str
    phone_number: str | None = None
    language_code: str | None = None
    session_id: str | None = None


class VoiceTurnResponse(BaseModel):
    transcript: str
    language_code: str
    language_probability: float | None = None
    intent: str
    response_text: str
    audio_base64: str | None = None
    audio_mime_type: str = "audio/wav"
    citizen_id: str | None = None
    interaction_id: str | None = None
    actions: list[dict] = []
    db_configured: bool


class LiveKitTokenRequest(BaseModel):
    room_name: str
    participant_name: str
    metadata: dict | None = None


class LiveKitTokenResponse(BaseModel):
    token: str
    url: str
    room_name: str
