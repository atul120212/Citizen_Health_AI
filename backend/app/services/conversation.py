import time
import uuid
from typing import Any

from .. import db
from ..schemas import SessionStartResponse, VoiceTurnResponse
from .repository import (
    create_followup_appointment,
    create_interaction,
    create_maternal_reminder,
    get_citizen_by_phone,
    get_nearest_departments,
    set_ayushman_precheck,
)
from .sarvam import SarvamService

# ---------------------------------------------------------------------------
# In-memory session store
# Each session holds a list of {"role": "user"|"assistant", "content": str}
# entries that are injected into every LLM call as conversation history.
# ---------------------------------------------------------------------------

_sessions: dict[str, list[dict[str, str]]] = {}
_session_ts: dict[str, float] = {}
SESSION_TTL = 1800  # 30 minutes

_INTRO_TEXTS: dict[str, str] = {
    "ta-IN": (
        "வணக்கம்! நான் சிட்டிசன் ஹெல்த் AI. "
        "மருத்துவமனை வழிகாட்டல், ஆயுஷ்மான் பாரத் மற்றும் CMCHIS தகுதி சோதனை, "
        "டாக்டர் அப்பாயின்மென்ட் பதிவு, மற்றும் தாய் சுகாதார நினைவூட்டல்களில் "
        "உங்களுக்கு உதவ இங்கே இருக்கிறேன். என்ன உதவி வேண்டும்?"
    ),
    "kn-IN": (
        "ನಮಸ್ಕಾರ! ನಾನು ಸಿಟಿಜನ್ ಹೆಲ್ತ್ AI. "
        "ಆಸ್ಪತ್ರೆ ನ್ಯಾವಿಗೇಷನ್, ಆಯುಷ್ಮಾನ್ ಭಾರತ್ ಮತ್ತು CMCHIS ಅರ್ಹತೆ ಪರಿಶೀಲನೆ, "
        "ಡಾಕ್ಟರ್ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಬುಕಿಂಗ್, ಮತ್ತು ತಾಯಿ ಆರೋಗ್ಯ ರಿಮೈಂಡರ್‌ಗಳಲ್ಲಿ "
        "ಸಹಾಯ ಮಾಡಲು ಇಲ್ಲಿದ್ದೇನೆ. ನಿಮಗೆ ಏನು ಬೇಕು?"
    ),
    "hi-IN": (
        "नमस्ते! मैं Citizen Health AI हूँ। "
        "मैं आपकी मदद कर सकता हूँ — अस्पताल में रास्ता दिखाने, "
        "Ayushman Bharat और CMCHIS पात्रता जाँचने, "
        "डॉक्टर का appointment बुक करने, और मातृ स्वास्थ्य reminders सेट करने में। "
        "आज मैं आपकी कैसे मदद कर सकता हूँ?"
    ),
    "en-IN": (
        "Hello! I'm Citizen Health AI. "
        "I'm here to help you with hospital navigation, Ayushman Bharat and CMCHIS "
        "eligibility checks, doctor appointment booking, and maternal health reminders. "
        "How can I help you today?"
    ),
}


def _cleanup_sessions() -> None:
    now = time.time()
    expired = [sid for sid, t in _session_ts.items() if now - t > SESSION_TTL]
    for sid in expired:
        _sessions.pop(sid, None)
        _session_ts.pop(sid, None)


def get_history(session_id: str | None) -> list[dict[str, str]]:
    if not session_id:
        return []
    _cleanup_sessions()
    return list(_sessions.get(session_id, []))


def append_turn(session_id: str | None, user_msg: str, assistant_msg: str) -> None:
    if not session_id:
        return
    if session_id not in _sessions:
        _sessions[session_id] = []
    _sessions[session_id].append({"role": "user", "content": user_msg})
    _sessions[session_id].append({"role": "assistant", "content": assistant_msg})
    _session_ts[session_id] = time.time()


# ---------------------------------------------------------------------------
# ConversationService
# ---------------------------------------------------------------------------

class ConversationService:
    def __init__(self) -> None:
        self.sarvam = SarvamService()

    # ------------------------------------------------------------------
    # Session intro
    # ------------------------------------------------------------------

    async def start_session(
        self,
        phone_number: str | None,  # noqa: ARG002 — reserved for future citizen pre-fetch
        language_code: str,
    ) -> SessionStartResponse:
        language_code = self._normalise_language(language_code)
        session_id = str(uuid.uuid4())

        intro_text = _INTRO_TEXTS.get(language_code, _INTRO_TEXTS["en-IN"])

        # Pre-populate the session with the assistant's opening line so the
        # LLM sees it as prior context on the very first user turn.
        _sessions[session_id] = [{"role": "assistant", "content": intro_text}]
        _session_ts[session_id] = time.time()

        audio_base64 = await self.sarvam.text_to_speech(intro_text, language_code)

        return SessionStartResponse(
            session_id=session_id,
            intro_text=intro_text,
            audio_base64=audio_base64,
            audio_mime_type="audio/wav",
        )

    # ------------------------------------------------------------------
    # Audio turn (STT → text turn)
    # ------------------------------------------------------------------

    async def handle_audio_turn(
        self,
        audio: bytes,
        filename: str,
        content_type: str,
        phone_number: str | None,
        session_id: str | None = None,
    ) -> VoiceTurnResponse:
        stt = await self.sarvam.speech_to_text(audio, filename, content_type)
        transcript = stt.get("transcript") or stt.get("text") or ""
        language_code = self._normalise_language(
            stt.get("language_code") or stt.get("language") or "ta-IN"
        )
        return await self.handle_text_turn(
            transcript=transcript,
            language_code=language_code,
            phone_number=phone_number,
            language_probability=stt.get("language_probability"),
            session_id=session_id,
        )

    # ------------------------------------------------------------------
    # Text turn (core logic)
    # ------------------------------------------------------------------

    async def handle_text_turn(
        self,
        transcript: str,
        language_code: str,
        phone_number: str | None = None,
        language_probability: float | None = None,
        session_id: str | None = None,
    ) -> VoiceTurnResponse:
        language_code = self._normalise_language(language_code)
        citizen = (
            await get_citizen_by_phone(phone_number)
            if phone_number and db.is_configured()
            else None
        )
        context: dict[str, Any] = {
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

        # Retrieve prior conversation history for context-aware replies
        history = get_history(session_id)

        turn = await self.sarvam.classify_and_reply(
            transcript, language_code, context, history=history
        )
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

        response_text = self._augment_response(
            turn["response_text"], turn["intent"], actions, language_code
        )
        audio_base64 = await self.sarvam.text_to_speech(response_text, language_code)

        # Persist this turn into the session history
        append_turn(session_id, transcript, response_text)

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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _apply_actions(
        self, turn: dict[str, Any], citizen: dict[str, Any] | None
    ) -> list[dict[str, Any]]:
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
                actions.append(
                    {"type": "appointment_created", "appointment_id": appointment["id"]}
                )

        if intent == "maternal_health_reminder":
            reminder = await create_maternal_reminder(
                citizen_id=citizen["id"],
                reminder_type=turn.get("maternal_reminder_type") or "anc",
            )
            if reminder:
                actions.append(
                    {"type": "maternal_reminder_created", "reminder_id": reminder["id"]}
                )

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

    def _augment_response(
        self,
        response: str,
        intent: str,
        actions: list[dict[str, Any]],
        language_code: str,
    ) -> str:
        if not actions:
            return response
        if intent == "appointment_booking" and any(
            a["type"] == "appointment_created" for a in actions
        ):
            suffix = {
                "ta-IN": " உங்கள் கோரிக்கை அருகிலுள்ள சுகாதார பணியாளருக்கு அனுப்பப்பட்டது.",
                "kn-IN": " ನಿಮ್ಮ ವಿನಂತಿಯನ್ನು ಸಮೀಪದ ಆರೋಗ್ಯ ಕಾರ್ಯಕರ್ತರಿಗೆ ಕಳುಹಿಸಲಾಗಿದೆ.",
                "hi-IN": " आपका अनुरोध नजदीकी स्वास्थ्य कार्यकर्ता को भेज दिया गया है।",
            }.get(language_code, " Your request has been sent to the nearest health worker.")
            return response + suffix
        return response

    def _normalise_language(self, language_code: str) -> str:
        language_code = language_code.lower().replace("_", "-")
        if language_code.startswith("ta"):
            return "ta-IN"
        if language_code.startswith("kn"):
            return "kn-IN"
        if language_code.startswith("hi"):
            return "hi-IN"
        if language_code.startswith("en"):
            return "en-IN"
        # Any other Indian language from Sarvam STT (te, ml, gu, mr, bn, …).
        # Reconstruct as proper BCP-47 with uppercase region.
        parts = language_code.split("-")
        return f"{parts[0]}-{parts[1].upper()}" if len(parts) == 2 else f"{parts[0]}-IN"
