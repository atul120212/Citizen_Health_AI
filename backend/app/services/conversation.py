from typing import Any

from .. import db
from ..schemas import VoiceTurnResponse
from .repository import (
    create_followup_appointment,
    create_interaction,
    create_maternal_reminder,
    get_citizen_by_phone,
    get_nearest_departments,
    set_ayushman_precheck,
)
from .sarvam import SarvamService


class ConversationService:
    def __init__(self) -> None:
        self.sarvam = SarvamService()

    async def handle_audio_turn(
        self,
        audio: bytes,
        filename: str,
        content_type: str,
        phone_number: str | None,
    ) -> VoiceTurnResponse:
        stt = await self.sarvam.speech_to_text(audio, filename, content_type)
        transcript = stt.get("transcript") or stt.get("text") or ""
        language_code = self._normalise_language(stt.get("language_code") or stt.get("language") or "ta-IN")
        return await self.handle_text_turn(
            transcript=transcript,
            language_code=language_code,
            phone_number=phone_number,
            language_probability=stt.get("language_probability"),
        )

    async def handle_text_turn(
        self,
        transcript: str,
        language_code: str,
        phone_number: str | None = None,
        language_probability: float | None = None,
    ) -> VoiceTurnResponse:
        language_code = self._normalise_language(language_code)
        citizen = await get_citizen_by_phone(phone_number) if phone_number and db.is_configured() else None
        context = {
            "citizen": citizen,
            "db_configured": db.is_configured(),
            "supported_services": [
                "hospital_navigation",
                "eligibility_check",
                "appointment_booking",
                "maternal_health_reminder",
                "nhm_programme_query",
            ],
        }

        turn = await self.sarvam.classify_and_reply(transcript, language_code, context)
        actions = await self._apply_actions(turn, citizen)
        interaction = None
        if db.is_configured():
            interaction = await create_interaction(
                citizen_id=citizen["id"] if citizen else None,
                transcript=transcript,
                intent=turn["intent"],
                audio_url=None,
                needs_worker_followup=turn.get("needs_worker_followup", False),
                interaction_type="voice_call",
            )

        response_text = self._augment_response(turn["response_text"], turn["intent"], actions, language_code)
        audio_base64 = await self.sarvam.text_to_speech(response_text, language_code)

        return VoiceTurnResponse(
            transcript=transcript,
            language_code=language_code,
            language_probability=language_probability,
            intent=turn["intent"],
            response_text=response_text,
            audio_base64=audio_base64,
            citizen_id=citizen["id"] if citizen else None,
            interaction_id=interaction["id"] if interaction else None,
            actions=actions,
            db_configured=db.is_configured(),
        )

    async def _apply_actions(self, turn: dict[str, Any], citizen: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not db.is_configured() or not citizen:
            return []

        intent = turn["intent"]
        actions: list[dict[str, Any]] = []

        if intent == "appointment_booking":
            appointment = await create_followup_appointment(
                citizen_id=citizen["id"],
                reason=turn.get("appointment_reason") or "Citizen Health AI follow-up",
            )
            if appointment:
                actions.append({"type": "appointment_created", "appointment_id": appointment["id"]})

        if intent == "maternal_health_reminder":
            reminder = await create_maternal_reminder(
                citizen_id=citizen["id"],
                reminder_type=turn.get("maternal_reminder_type") or "anc",
            )
            if reminder:
                actions.append({"type": "maternal_reminder_created", "reminder_id": reminder["id"]})

        if intent == "eligibility_check":
            eligible = bool(citizen.get("abha_id") or citizen.get("ayushman_status"))
            updated = await set_ayushman_precheck(citizen["id"], eligible)
            actions.append(
                {
                    "type": "eligibility_precheck",
                    "eligible": eligible,
                    "citizen_id": updated["id"] if updated else citizen["id"],
                }
            )

        if intent == "hospital_navigation":
            departments = await get_nearest_departments(turn.get("appointment_reason"))
            actions.append({"type": "department_matches", "departments": departments})

        return actions

    def _augment_response(self, response: str, intent: str, actions: list[dict[str, Any]], language_code: str) -> str:
        if not actions:
            return response

        if intent == "appointment_booking" and any(action["type"] == "appointment_created" for action in actions):
            suffix = {
                "ta-IN": " உங்கள் கோரிக்கை அருகிலுள்ள சுகாதார பணியாளருக்கு அனுப்பப்பட்டது.",
                "kn-IN": " ನಿಮ್ಮ ವಿನಂತಿಯನ್ನು ಸಮೀಪದ ಆರೋಗ್ಯ ಕಾರ್ಯಕರ್ತರಿಗೆ ಕಳುಹಿಸಲಾಗಿದೆ.",
            }.get(language_code, " Your request has been sent to the nearest health worker.")
            return response + suffix

        return response

    def _normalise_language(self, language_code: str) -> str:
        language_code = language_code.lower().replace("_", "-")
        if language_code.startswith("ta"):
            return "ta-IN"
        if language_code.startswith("kn"):
            return "kn-IN"
        return "en-IN"
