import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

import logging

logger = logging.getLogger(__name__)

from ..config import get_settings
from .mcp_tools import TOOLS_DESCRIPTION


def _json_default(obj: Any) -> Any:
    """Fallback serializer for psycopg3 types (UUID, datetime, date)."""
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)

_BASE_SYSTEM_PROMPT = Path(__file__).resolve().parents[1].joinpath("prompts/citizen_assistant_system.txt").read_text(encoding="utf-8")

# Append MCP tool descriptions to system prompt
SYSTEM_PROMPT = _BASE_SYSTEM_PROMPT + "\n\n" + TOOLS_DESCRIPTION

_SYMPTOM_WORDS = (
    "fever", "cough", "pain", "headache", "vomiting", "diarrhea", "diarrhoea",
    "rash", "cold", "flu", "infection", "injury", "dizzy", "dizziness", "weakness",
)


def _agent_log(location: str, message: str, data: dict, hypothesis_id: str) -> None:
    logger.debug("[%s] %s: %s (ID: %s)", location, message, data, hypothesis_id)


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

        import logging
        _log = logging.getLogger(__name__)
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
            # Gracefully handle bad audio (too short, silent, wrong format)
            if response.status_code in (400, 422):
                _log.warning("[STT] bad audio (%s): %s", response.status_code, response.text[:200])
                return {
                    "transcript": "",
                    "language_code": "en-IN",
                    "language_probability": None,
                    "request_id": "bad-audio",
                }
            if response.status_code == 429:
                _log.warning("[STT] Sarvam API rate limit (429) exceeded. Gracefully degrading.")
                return {
                    "transcript": "Hello", # Safe fallback so it doesn't crash
                    "language_code": "en-IN",
                    "language_probability": None,
                    "request_id": "rate-limit",
                }
            response.raise_for_status()
            return response.json()

    async def classify_and_reply(
        self,
        transcript: str,
        language_code: str,
        context: dict[str, Any],
        history: list[dict[str, str]] | None = None,
        rag_context: str | None = None,
        active_intent: str | None = None,
        slot_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            return self._fallback_turn(
                transcript, language_code, history=history,
                active_intent=active_intent, slot_state=slot_state,
            )

        user_content = {
            "transcript": transcript,
            "language_code": language_code,
            "citizen_context": context,
            "active_intent": active_intent,
            "slot_state": slot_state or {},
        }

        # Build effective system prompt — inject RAG knowledge if available
        effective_system = SYSTEM_PROMPT
        if rag_context:
            effective_system = effective_system + "\n\n" + rag_context

        # Build messages: system prompt → prior conversation history → current turn.
        # History entries are plain {"role": "user"|"assistant", "content": str} dicts
        # that the LLM uses to maintain context across multiple speech turns.
        messages: list[dict[str, str]] = [{"role": "system", "content": effective_system}]
        if history:
            messages.extend(history)
        messages.append(
            {"role": "user", "content": json.dumps(user_content, ensure_ascii=False, default=_json_default)}
        )

        payload = {
            "model": self.settings.sarvam_chat_model,
            "temperature": 0.2,
            # sarvam-30b is a reasoning model: it writes internal chain-of-thought
            # (reasoning_content) before emitting the final JSON (content).
            # 2048 gives enough room for both reasoning and the JSON reply.
            "max_tokens": 2048,
            "messages": messages,
        }

        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                f"{self.settings.sarvam_base_url}/v1/chat/completions",
                headers={**self._headers(), "Content-Type": "application/json"},
                json=payload,
            )
            if response.status_code == 429:
                import logging
                logging.getLogger(__name__).warning("Sarvam Chat API rate limit (429) exceeded. Using fallback logic.")
                return self._fallback_turn(
                    transcript, language_code, history=history,
                    active_intent=active_intent, slot_state=slot_state,
                )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"].get("content")
            if not content:
                return self._fallback_turn(
                    transcript, language_code, history=history,
                    active_intent=active_intent, slot_state=slot_state,
                )
            return self._parse_json(
                content, transcript, language_code,
                history=history, active_intent=active_intent, slot_state=slot_state,
            )

    async def text_to_speech(self, text: str, language_code: str) -> str | None:
        if not self.configured:
            return None

        _tts_supported = {"ta-IN", "kn-IN", "hi-IN", "en-IN", "te-IN", "ml-IN", "gu-IN", "mr-IN", "bn-IN"}
        target_language_code = language_code if language_code in _tts_supported else "hi-IN"
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
            if response.status_code == 429:
                import logging
                logging.getLogger(__name__).warning("Sarvam TTS API rate limit (429) exceeded. Gracefully degrading to text-only.")
                return None
            response.raise_for_status()
            audios = response.json().get("audios") or []
            return audios[0] if audios else None

    def _parse_json(
        self,
        content: str,
        transcript: str,
        language_code: str,
        *,
        history: list[dict[str, str]] | None = None,
        active_intent: str | None = None,
        slot_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            start = content.index("{")
            end = content.rindex("}") + 1
            parsed = json.loads(content[start:end])
        except (ValueError, json.JSONDecodeError):
            parsed = self._fallback_turn(
                transcript, language_code, history=history,
                active_intent=active_intent, slot_state=slot_state,
            )

        return {
            "intent": parsed.get("intent", "fallback"),
            "response_text": parsed.get("response_text", ""),
            "needs_worker_followup": bool(parsed.get("needs_worker_followup", False)),
            "identifier": parsed.get("identifier"),  # phone/ABHA from verification
            "appointment_reason": parsed.get("appointment_reason"),
            "appointment_date": parsed.get("appointment_date"),
            "appointment_time": parsed.get("appointment_time"),
            "patient_name": parsed.get("patient_name"),
            "patient_email": parsed.get("patient_email"),
            "confirmed": bool(parsed.get("confirmed", False)),
            "maternal_reminder_type": parsed.get("maternal_reminder_type"),
            "missing_slots": parsed.get("missing_slots") or [],
            "call_summary": parsed.get("call_summary"),  # for session_end
            "tool_call": parsed.get("tool_call"),
        }

    @staticmethod
    def _has_keyword(text: str, keywords: list[str], *, whole_word: bool = False) -> bool:
        """Match keywords; use whole_word for short tokens that appear inside other words (e.g. lab in available)."""
        if not whole_word:
            return any(k in text for k in keywords)
        return any(re.search(rf"\b{re.escape(k)}\b", text) for k in keywords)

    @staticmethod
    def _infer_active_intent_from_history(history: list[dict[str, str]] | None) -> str | None:
        if not history:
            return None
        last_assistant = ""
        for msg in reversed(history):
            if msg.get("role") == "assistant":
                last_assistant = (msg.get("content") or "").lower()
                break
        if "health concern" in last_assistant and "appointment" in last_assistant:
            return "appointment_booking"
        if "what time" in last_assistant and ("visit" in last_assistant or "appointment" in last_assistant):
            return "appointment_booking"
        if "email" in last_assistant and "confirmation" in last_assistant:
            return "appointment_booking"
        if "abha" in last_assistant and ("eligibility" in last_assistant or "pre-check" in last_assistant):
            return "eligibility_check"
        if "maternal health reminder" in last_assistant or "anc visit" in last_assistant:
            return "maternal_health_reminder"
        if "which service" in last_assistant and "phc" in last_assistant:
            return "hospital_navigation"
        return None

    def _extract_appointment_slots(self, text: str, slot_state: dict[str, Any]) -> dict[str, Any]:
        slots = dict(slot_state)
        lower = text.lower()
        today = datetime.now(timezone.utc).date()

        if "tomorrow" in lower and not slots.get("appointment_date"):
            slots["appointment_date"] = (today + timedelta(days=1)).isoformat()
        elif "today" in lower and not slots.get("appointment_date"):
            slots["appointment_date"] = today.isoformat()

        concern_match = re.search(
            r"health\s+concern(?:\s+is)?\s+(.+?)(?:\.|$)",
            lower,
        )
        if concern_match:
            slots["appointment_reason"] = concern_match.group(1).strip()
        else:
            for symptom in _SYMPTOM_WORDS:
                if re.search(rf"\b{re.escape(symptom)}\b", lower):
                    slots["appointment_reason"] = symptom
                    break

        time_match = re.search(
            r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
            lower,
        )
        if time_match and not slots.get("appointment_time"):
            hour = int(time_match.group(1))
            minute = int(time_match.group(2) or 0)
            meridiem = time_match.group(3)
            if meridiem == "pm" and hour < 12:
                hour += 12
            elif meridiem == "am" and hour == 12:
                hour = 0
            slots["appointment_time"] = f"{hour:02d}:{minute:02d}"
        elif any(w in lower for w in ("morning", "afternoon", "evening")) and not slots.get("appointment_time"):
            for label, default in (("morning", "09:00"), ("afternoon", "14:00"), ("evening", "17:00")):
                if label in lower:
                    slots["appointment_time"] = default
                    break

        email_match = re.search(r"[\w.+-]+@[\w.-]+\.\w+", text)
        if email_match:
            slots["patient_email"] = email_match.group(0)

        return slots

    def _appointment_missing_slots(self, slots: dict[str, Any]) -> list[str]:
        missing: list[str] = []
        if not slots.get("appointment_reason"):
            missing.append("appointment_reason")
        if not slots.get("appointment_date"):
            missing.append("appointment_date")
        if not slots.get("appointment_time"):
            missing.append("appointment_time")
        if not slots.get("patient_email"):
            missing.append("patient_email")
        return missing

    def _continue_appointment_turn(
        self,
        transcript: str,
        language_code: str,
        slot_state: dict[str, Any],
    ) -> dict[str, Any]:
        slots = self._extract_appointment_slots(transcript, slot_state)
        missing = self._appointment_missing_slots(slots)
        reason = slots.get("appointment_reason") or "your concern"
        date_str = slots.get("appointment_date") or "the chosen day"

        if "appointment_reason" in missing:
            response = {
                "ta-IN": "உங்களுக்கு உதவுகிறேன். Appointment பதிவு செய்ய என்ன காரணம் கூற வேண்டும்?",
                "kn-IN": "ನಾನು ಸಹಾಯ ಮಾಡುತ್ತೇನೆ. Appointment ಬುಕ್ ಮಾಡಲು ಯಾವ ಕಾರಣ ಹೇಳಬೇಕು?",
                "hi-IN": "मैं help करूँगा। Appointment के लिए किस health problem के बारे में mention करना है?",
                "bho-IN": "हम help करब। Appointment खातिर कवन health problem के बारे में बतावल जाव?",
                "en-IN": "I can help book an appointment. What health concern should I mention for the visit?",
            }.get(language_code, "I can help book an appointment. What health concern should I mention for the visit?")
        elif "appointment_time" in missing:
            response = {
                "en-IN": (
                    f"Got it — I'll note {reason} for {date_str}. "
                    "What time works for your visit? For example, 10 AM or afternoon."
                ),
                "hi-IN": (
                    f"ठीक है — {reason} के लिए {date_str} पर appointment है। "
                    "visit का समय क्या सुविधाजनक होगा? जैसे 10 AM या दोपहर।"
                ),
            }.get(
                language_code,
                f"Got it — I'll note {reason} for {date_str}. What time works for your visit?",
            )
        elif "patient_email" in missing:
            response = {
                "en-IN": (
                    f"Thanks. I have {reason} on {date_str} at {slots.get('appointment_time')}. "
                    "Please share your email for the confirmation."
                ),
                "hi-IN": (
                    f"धन्यवाद। {date_str} को {slots.get('appointment_time')} पर {reason} दर्ज है। "
                    "confirmation के लिए अपना email बताइए।"
                ),
            }.get(
                language_code,
                f"Thanks. I have {reason} on {date_str} at {slots.get('appointment_time')}. Please share your email.",
            )
        else:
            response = {
                "en-IN": (
                    f"Perfect. I'll book {reason} on {date_str} at {slots.get('appointment_time')}. "
                    "A confirmation will be sent to your email."
                ),
                "hi-IN": (
                    f"बढ़िया। {date_str} को {slots.get('appointment_time')} पर {reason} के लिए appointment book कर दूँगा। "
                    "confirmation आपके email पर भेज दी जाएगी।"
                ),
            }.get(
                language_code,
                f"Perfect. I'll book {reason} on {date_str} at {slots.get('appointment_time')}.",
            )

        return {
            "intent": "appointment_booking",
            "response_text": response,
            "needs_worker_followup": True,
            "appointment_reason": slots.get("appointment_reason"),
            "appointment_date": slots.get("appointment_date"),
            "appointment_time": slots.get("appointment_time"),
            "patient_name": slots.get("patient_name"),
            "patient_email": slots.get("patient_email"),
            "confirmed": len(missing) == 0,
            "maternal_reminder_type": None,
            "missing_slots": missing,
        }

    def _detect_fresh_intent(self, text: str, script: str) -> str | None:
        """Classify intent from the current utterance only (no session context)."""
        emerg_en = self._has_keyword(
            text,
            [
                "emergency", "chest pain", "can't breathe", "cannot breathe",
                "heavy bleeding", "bleeding", "stroke", "unconscious",
                "accident", "urgent", "108",
            ],
        )
        emerg_hi = self._has_keyword(text, ["emergency", "सीने में दर्द", "खून", "सांस", "एक्सीडेंट", "जल्दी", "108"])
        emerg_bho = self._has_keyword(text, ["emergency", "खून", "सांस", "एक्सीडेंट", "जल्दी", "108"])

        elig_en = self._has_keyword(text, ["ayushman", "cmchis", "insurance", "eligible", "benefit", "money", "card"])
        elig_hi = self._has_keyword(text, ["ayushman", "cmchis", "पात्रता", "eligible", "बीमा", "कार्ड", "पैसा"])
        elig_bho = self._has_keyword(text, ["ayushman", "cmchis", "eligible", "बीमा", "पात्र", "कार्ड", "पैसा"])

        maternal_en = self._has_keyword(
            text, ["pregnant", "mother", "anc", "vaccine", "reminder", "delivery", "baby", "pregnancy"]
        )
        maternal_ta = self._has_keyword(script, ["கர்ப்ப", "தடுப்பூசி", "நினைவூட்டல்", "பிரசவம்", "குழந்தை"])
        maternal_kn = self._has_keyword(script, ["ಗರ್ಭಿಣಿ", "ಲಸಿಕೆ", "ರಿಮೈಂಡರ್", "ಹೆರಿಗೆ", "ಮಗು"])
        maternal_hi = self._has_keyword(
            text, ["pregnant", "गर्भ", "टीका", "vaccine", "reminder", "anc", "माँ", "डिलीवरी", "बच्चा"]
        )
        maternal_bho = self._has_keyword(
            text, ["pregnant", "vaccine", "reminder", "anc", "टीका", "माँ", "डिलीवरी", "बच्चा"]
        )

        nhm_en = self._has_keyword(
            text, ["nhm", "national health mission", "programme", "program", "scheme", "janani", "jsy", "pmmvy"]
        )
        nhm_hi = self._has_keyword(text, ["nhm", "कार्यक्रम", "योजना", "स्कीम"])

        nav_en = self._has_keyword(
            text,
            ["counter", "floor", "room", "where", "navigation", "pharmacy", "registration counter"],
            whole_word=True,
        ) or self._has_keyword(text, ["toilet", "pharmacy"]) or self._has_keyword(text, ["lab"], whole_word=True)
        nav_ta = self._has_keyword(script, ["எங்கே", "கவுண்டர்", "அறை", "வழி", "கழிப்பறை", "மருந்துக்கடை"])
        nav_kn = self._has_keyword(script, ["ಎಲ್ಲಿ", "ಕೌಂಟರ್", "ಕೊಠಡಿ", "ದಾರಿ", "ಶೌಚಾಲಯ", "ಔಷಧಿ ಅಂಗಡಿ"])
        nav_hi = self._has_keyword(text, ["kahan", "counter", "कहाँ", "काउंटर", "कमरा", "रास्ता", "टॉयलेट", "दवाई"])
        nav_bho = self._has_keyword(text, ["kahan", "counter", "कहाँ", "काउंटर", "कमरा", "रास्ता", "टॉयलेट", "दवाई"])
        # "which room" style queries — require room + location cue, not bare "room" in "programme"
        if not nav_en and self._has_keyword(text, ["room"], whole_word=True):
            nav_en = self._has_keyword(text, ["which", "where", "find", "pharmacy", "registration"])

        appt_en = self._has_keyword(
            text, ["appointment", "book", "doctor", "slot", "consultation", "schedule", "visit"]
        )
        appt_ta = self._has_keyword(script, ["அப்பாயின்மென்ட்", "டாக்டர்", "மருத்துவர்"])
        appt_kn = self._has_keyword(script, ["ಅಪಾಯಿಂಟ್ಮೆಂಟ್", "ವೈದ್ಯ", "ಡಾಕ್ಟರ್"])
        appt_hi = self._has_keyword(text, ["appointment", "doctor", "डॉक्टर", "अपॉइंटमेंट", "बुक", "slot"])
        appt_bho = self._has_keyword(text, ["appointment", "doctor", "डॉक्टर"])

        if emerg_en or emerg_hi or emerg_bho:
            return "emergency"
        if elig_en or elig_hi or elig_bho:
            return "eligibility_check"
        if maternal_en or maternal_ta or maternal_kn or maternal_hi or maternal_bho:
            return "maternal_health_reminder"
        if nhm_en or nhm_hi:
            return "nhm_programme_query"
        if nav_en or nav_ta or nav_kn or nav_hi or nav_bho:
            return "hospital_navigation"
        if appt_en or appt_ta or appt_kn or appt_hi or appt_bho:
            return "appointment_booking"
        # Slot-filling replies (symptoms, times) without explicit booking keywords
        if self._has_keyword(text, list(_SYMPTOM_WORDS), whole_word=True):
            return None  # handled by active appointment flow
        if self._has_keyword(text, ["health concern", "concern is"]):
            return None
        # Short confirmations, greetings, numbers — no strong intent signal
        if len(text.split()) <= 4:
            return None
        return "nhm_programme_query"

    def _build_fresh_turn(
        self, intent: str, language_code: str, transcript: str, slot_state: dict[str, Any]
    ) -> dict[str, Any]:
        if intent == "appointment_booking":
            slots = self._extract_appointment_slots(transcript, slot_state)
            turn = self._continue_appointment_turn(transcript, language_code, slots)
            _agent_log(
                "sarvam.py:_build_fresh_turn",
                "fresh appointment turn",
                {"intent": intent, "slots": slots, "missing": turn.get("missing_slots")},
                "H1",
            )
            return turn

        responses: dict[str, dict[str, str]] = {
            "emergency": {
                "ta-IN": "இது அவசரநிலை போல் தெரிகிறது। உடனே அருகிலுள்ள emergency department-க்கு செல்லுங்கள் அல்லது emergency services-ஐ அழையுங்கள்.",
                "kn-IN": "ಇದು ತುರ್ತು ಪರಿಸ್ಥಿತಿ ಇರಬಹುದು. ತಕ್ಷಣ ಹತ್ತಿರದ emergency department-ಗೆ ಹೋಗಿ ಅಥವಾ emergency services-ಗೆ ಕರೆ ಮಾಡಿ.",
                "hi-IN": "यह emergency लग रहा है। तुरंत नजदीकी emergency department जाएँ या emergency services को call करें।",
                "en-IN": "This may be urgent. Please go to the nearest emergency department or call local emergency services now.",
            },
            "eligibility_check": {
                "ta-IN": "உங்களுக்கு உதவுகிறேன். ABHA ID அல்லது பதிவு செய்யப்பட்ட phone number தரவும்.",
                "kn-IN": "ನಾನು ಸಹಾಯ ಮಾಡುತ್ತೇನೆ. ABHA ID ಅಥವಾ ನೋಂದಾಯಿಸಿದ phone number ಕೊಡಿ.",
                "hi-IN": "मैं basic eligibility pre-check कर सकता हूँ। अपना ABHA ID या registered phone number बताइए।",
                "en-IN": "I can do a basic eligibility pre-check. Please share your ABHA ID or registered phone number.",
            },
            "maternal_health_reminder": {
                "ta-IN": "உங்களுக்கு உதவுகிறேன். ANC visit, supplements, vaccination, அல்லது delivery follow-up எது வேண்டும்?",
                "kn-IN": "ನಾನು ಸಹಾಯ ಮಾಡುತ್ತೇನೆ. ANC visit, supplements, vaccination, ಅಥವಾ delivery follow-up ಯಾವುದು ಬೇಕು?",
                "hi-IN": "मैं maternal health reminder set कर सकता हूँ। ANC visit, supplements, vaccination, या delivery follow-up — कौनसा चाहिए?",
                "en-IN": "I can set maternal health reminders. Is this for ANC visit, supplements, vaccination, or expected delivery follow-up?",
            },
            "nhm_programme_query": {
                "ta-IN": "NHM programme பற்றிய கேள்விகளுக்கு உதவுகிறேன்.",
                "kn-IN": "NHM programme ಬಗ್ಗೆ ಸಹಾಯ ಮಾಡುತ್ತೇನೆ.",
                "hi-IN": "मैं NHM programme के बारे में जवाब दे सकता हूँ।",
                "en-IN": "I can answer NHM programme questions and guide you to the right PHC service.",
            },
            "hospital_navigation": {
                "ta-IN": "உங்களுக்கு உதவுகிறேன். Registration, doctor consultation, lab, pharmacy, அல்லது maternal health — எந்த சேவை வேண்டும்?",
                "kn-IN": "ನಾನು ಸಹಾಯ ಮಾಡುತ್ತೇನೆ. Registration, doctor consultation, lab, pharmacy, ಅಥವಾ maternal health — ಯಾವ ಸೇವೆ ಬೇಕು?",
                "hi-IN": "मैं PHC के अंदर guide कर सकता हूँ। Registration, doctor consultation, lab, pharmacy, या maternal health — कौनसी service चाहिए?",
                "en-IN": "I can guide you inside the PHC. Which service do you need: registration, doctor consultation, lab, pharmacy, or maternal health?",
            },
        }
        missing_by_intent: dict[str, list[str]] = {
            "emergency": [],
            "eligibility_check": ["abha_id_or_phone"],
            "maternal_health_reminder": ["reminder_type"],
            "nhm_programme_query": ["programme_or_service"],
            "hospital_navigation": ["service"],
        }
        text = responses.get(intent, responses["nhm_programme_query"])
        response = text.get(language_code, text["en-IN"])
        return {
            "intent": intent,
            "response_text": response,
            "needs_worker_followup": intent in {"emergency", "appointment_booking"},
            "appointment_reason": None,
            "appointment_date": None,
            "appointment_time": None,
            "patient_name": None,
            "patient_email": None,
            "confirmed": False,
            "maternal_reminder_type": "anc" if intent == "maternal_health_reminder" else None,
            "missing_slots": missing_by_intent.get(intent, []),
        }

    def _fallback_turn(
        self,
        transcript: str,
        language_code: str,
        *,
        history: list[dict[str, str]] | None = None,
        active_intent: str | None = None,
        slot_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        text = transcript.lower()
        script = transcript
        slots = dict(slot_state or {})
        flow = active_intent or self._infer_active_intent_from_history(history)
        fresh = self._detect_fresh_intent(text, script)

        _agent_log(
            "sarvam.py:_fallback_turn",
            "fallback routing",
            {
                "transcript_preview": text[:80],
                "flow": flow,
                "fresh": fresh,
                "history_len": len(history or []),
                "slots": slots,
            },
            "H1",
        )

        # Continue in-progress appointment unless user clearly starts a new topic
        if flow == "appointment_booking" and fresh not in {
            "emergency", "eligibility_check", "maternal_health_reminder",
            "nhm_programme_query", "hospital_navigation", "verify_identity",
        }:
            turn = self._continue_appointment_turn(transcript, language_code, slots)
            _agent_log(
                "sarvam.py:_fallback_turn",
                "continued appointment",
                {"intent": turn["intent"], "missing": turn.get("missing_slots"), "reason": turn.get("appointment_reason")},
                "H2",
            )
            return turn

        if fresh == "appointment_booking":
            return self._build_fresh_turn(fresh, language_code, transcript, slots)

        if fresh and fresh != "nhm_programme_query":
            return self._build_fresh_turn(fresh, language_code, transcript, slots)

        if fresh == "nhm_programme_query" and flow == "appointment_booking":
            turn = self._continue_appointment_turn(transcript, language_code, slots)
            _agent_log("sarvam.py:_fallback_turn", "blocked nhm reset during appointment", {"intent": turn["intent"]}, "H3")
            return turn

        intent = fresh or "nhm_programme_query"
        return self._build_fresh_turn(intent, language_code, transcript, slots)
