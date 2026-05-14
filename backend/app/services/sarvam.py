import json
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

from ..config import get_settings


def _json_default(obj: Any) -> Any:
    """Fallback serializer for psycopg3 types (UUID, datetime, date)."""
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)

SYSTEM_PROMPT = Path(__file__).resolve().parents[1].joinpath("prompts/citizen_assistant_system.txt").read_text()


class SarvamService:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.sarvam_api_key)

    def _headers(self) -> dict[str, str]:
        if not self.settings.sarvam_api_key:
            return {}
        return {"api-subscription-key": self.settings.sarvam_api_key}

    async def speech_to_text(self, audio: bytes, filename: str, content_type: str) -> dict[str, Any]:
        if not self.configured:
            return {
                "transcript": "I need help booking an appointment",
                "language_code": "en-IN",
                "language_probability": None,
                "request_id": "local-demo",
            }

        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                f"{self.settings.sarvam_base_url}/speech-to-text",
                headers=self._headers(),
                data={
                    "model": self.settings.sarvam_stt_model,
                    "mode": "transcribe",
                },
                files={"file": (filename, audio, content_type)},
            )
            response.raise_for_status()
            return response.json()

    async def classify_and_reply(self, transcript: str, language_code: str, context: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            return self._fallback_turn(transcript, language_code)

        user_content = {
            "transcript": transcript,
            "language_code": language_code,
            "citizen_context": context,
        }
        payload = {
            "model": self.settings.sarvam_chat_model,
            "temperature": 0.2,
            "max_tokens": 700,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_content, ensure_ascii=False, default=_json_default)},
            ],
        }

        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                f"{self.settings.sarvam_base_url}/v1/chat/completions",
                headers={**self._headers(), "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"].get("content")
            if not content:
                return self._fallback_turn(transcript, language_code)
            return self._parse_json(content, transcript, language_code)

    async def text_to_speech(self, text: str, language_code: str) -> str | None:
        if not self.configured:
            return None

        target_language_code = language_code if language_code in {"ta-IN", "kn-IN", "en-IN"} else "ta-IN"
        payload = {
            "text": text[:2400],
            "target_language_code": target_language_code,
            "model": self.settings.sarvam_tts_model,
            "speaker": self.settings.sarvam_tts_speaker,
            "output_audio_codec": "wav",
            "speech_sample_rate": 24000,
            "pace": 0.95,
        }

        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                f"{self.settings.sarvam_base_url}/text-to-speech",
                headers={**self._headers(), "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            audios = response.json().get("audios") or []
            return audios[0] if audios else None

    def _parse_json(self, content: str, transcript: str, language_code: str) -> dict[str, Any]:
        try:
            start = content.index("{")
            end = content.rindex("}") + 1
            parsed = json.loads(content[start:end])
        except (ValueError, json.JSONDecodeError):
            parsed = self._fallback_turn(transcript, language_code)

        return {
            "intent": parsed.get("intent", "fallback"),
            "response_text": parsed.get("response_text", ""),
            "needs_worker_followup": bool(parsed.get("needs_worker_followup", False)),
            "appointment_reason": parsed.get("appointment_reason"),
            "maternal_reminder_type": parsed.get("maternal_reminder_type"),
            "missing_slots": parsed.get("missing_slots") or [],
        }

    def _fallback_turn(self, transcript: str, language_code: str) -> dict[str, Any]:
        text = transcript.lower()
        tamil_or_kannada = transcript
        if any(word in text for word in ["appointment", "book", "doctor", "slot"]) or any(
            word in tamil_or_kannada
            for word in ["அப்பாயின்மென்ட்", "டாக்டர்", "மருத்துவர்", "ಅಪಾಯಿಂಟ್ಮೆಂಟ್", "ವೈದ್ಯ", "ಡಾಕ್ಟರ್"]
        ):
            intent = "appointment_booking"
            response = "I can help book an appointment. What health concern should I mention for the visit?"
            missing_slots = ["appointment_reason"]
        elif any(word in text for word in ["ayushman", "cmchis", "insurance", "eligible"]):
            intent = "eligibility_check"
            response = "I can do a basic eligibility pre-check. Please share your ABHA ID or registered phone number."
            missing_slots = ["abha_id_or_phone"]
        elif any(word in text for word in ["pregnant", "mother", "anc", "vaccine", "reminder"]) or any(
            word in tamil_or_kannada
            for word in ["கர்ப்ப", "தடுப்பூசி", "நினைவூட்டல்", "ಗರ್ಭಿಣಿ", "ಲಸಿಕೆ", "reminder", "ರಿಮೈಂಡರ್"]
        ):
            intent = "maternal_health_reminder"
            response = "I can set maternal health reminders. Is this for ANC visit, supplements, vaccination, or expected delivery follow-up?"
            missing_slots = ["reminder_type"]
        elif any(word in text for word in ["emergency", "chest pain", "bleeding", "breath"]):
            intent = "emergency"
            response = "This may be urgent. Please go to the nearest emergency department or call local emergency services now."
            missing_slots = []
        elif any(word in text for word in ["counter", "floor", "room", "where", "navigation"]) or any(
            word in tamil_or_kannada
            for word in ["எங்கே", "கவுண்டர்", "அறை", "ಎಲ್ಲಿ", "ಕೌಂಟರ್", "ಕೊಠಡಿ"]
        ):
            intent = "hospital_navigation"
            response = "I can guide you inside the PHC. Which service do you need: registration, doctor consultation, lab, pharmacy, or maternal health?"
            missing_slots = ["service"]
        else:
            intent = "nhm_programme_query"
            response = "I can answer NHM programme questions and guide you to the right PHC service."
            missing_slots = ["programme_or_service"]

        if language_code == "ta-IN":
            response = "உங்களுக்கு உதவுகிறேன். " + response
        elif language_code == "kn-IN":
            response = "ನಾನು ಸಹಾಯ ಮಾಡುತ್ತೇನೆ. " + response

        return {
            "intent": intent,
            "response_text": response,
            "needs_worker_followup": intent in {"emergency", "appointment_booking"},
            "appointment_reason": "General consultation" if intent == "appointment_booking" else None,
            "maternal_reminder_type": "anc" if intent == "maternal_health_reminder" else None,
            "missing_slots": missing_slots,
        }
