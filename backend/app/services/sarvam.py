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

    async def classify_and_reply(
        self,
        transcript: str,
        language_code: str,
        context: dict[str, Any],
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            return self._fallback_turn(transcript, language_code)

        user_content = {
            "transcript": transcript,
            "language_code": language_code,
            "citizen_context": context,
        }

        # Build messages: system prompt → prior conversation history → current turn.
        # History entries are plain {"role": "user"|"assistant", "content": str} dicts
        # that the LLM uses to maintain context across multiple speech turns.
        messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
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
            # 700 tokens was exhausted during reasoning, leaving content=null.
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
            response.raise_for_status()
            content = response.json()["choices"][0]["message"].get("content")
            if not content:
                return self._fallback_turn(transcript, language_code)
            return self._parse_json(content, transcript, language_code)

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
            "appointment_date": parsed.get("appointment_date"),
            "appointment_time": parsed.get("appointment_time"),
            "patient_name": parsed.get("patient_name"),
            "patient_email": parsed.get("patient_email"),
            "confirmed": bool(parsed.get("confirmed", False)),
            "maternal_reminder_type": parsed.get("maternal_reminder_type"),
            "missing_slots": parsed.get("missing_slots") or [],
        }

    def _fallback_turn(self, transcript: str, language_code: str) -> dict[str, Any]:
        text = transcript.lower()
        script = transcript  # original for script-based matching

        # ── Intent detection (multilingual keywords) ─────────────────
        appt_en  = any(w in text for w in ["appointment", "book", "doctor", "slot"])
        appt_ta  = any(w in script for w in ["அப்பாயின்மென்ட்", "டாக்டர்", "மருத்துவர்"])
        appt_kn  = any(w in script for w in ["ಅಪಾಯಿಂಟ್ಮೆಂಟ್", "ವೈದ್ಯ", "ಡಾಕ್ಟರ್"])
        appt_hi  = any(w in text for w in ["appointment", "doctor", "डॉक्टर", "अपॉइंटमेंट", "बुक", "slot"])

        elig_en  = any(w in text for w in ["ayushman", "cmchis", "insurance", "eligible"])
        elig_hi  = any(w in text for w in ["ayushman", "cmchis", "पात्रता", "eligible", "बीमा"])

        maternal_en = any(w in text for w in ["pregnant", "mother", "anc", "vaccine", "reminder"])
        maternal_ta = any(w in script for w in ["கர்ப்ப", "தடுப்பூசி", "நினைவூட்டல்"])
        maternal_kn = any(w in script for w in ["ಗರ್ಭಿಣಿ", "ಲಸಿಕೆ", "ರಿಮೈಂಡರ್"])
        maternal_hi = any(w in text for w in ["pregnant", "गर्भ", "टीका", "vaccine", "reminder", "anc", "माँ"])

        emerg_en = any(w in text for w in ["emergency", "chest pain", "bleeding", "breath"])
        emerg_hi = any(w in text for w in ["emergency", "दर्द", "खून", "सांस", "emergency"])

        nav_en   = any(w in text for w in ["counter", "floor", "room", "where", "navigation"])
        nav_ta   = any(w in script for w in ["எங்கே", "கவுண்டர்", "அறை"])
        nav_kn   = any(w in script for w in ["ಎಲ್ಲಿ", "ಕೌಂಟರ್", "ಕೊಠಡಿ"])
        nav_hi   = any(w in text for w in ["kahan", "counter", "room", "कहाँ", "काउंटर", "कमरा"])

        if appt_en or appt_ta or appt_kn or appt_hi:
            intent = "appointment_booking"
            responses = {
                "ta-IN": "உங்களுக்கு உதவுகிறேன். Appointment பதிவு செய்ய என்ன காரணம் கூற வேண்டும்?",
                "kn-IN": "ನಾನು ಸಹಾಯ ಮಾಡುತ್ತೇನೆ. Appointment ಬುಕ್ ಮಾಡಲು ಯಾವ ಕಾರಣ ಹೇಳಬೇಕು?",
                "hi-IN": "मैं help करूँगा। Appointment के लिए किस health problem के बारे में mention करना है?",
                "en-IN": "I can help book an appointment. What health concern should I mention for the visit?",
            }
            missing_slots = ["appointment_reason"]
        elif elig_en or elig_hi:
            intent = "eligibility_check"
            responses = {
                "ta-IN": "உங்களுக்கு உதவுகிறேன். ABHA ID அல்லது பதிவு செய்யப்பட்ட phone number தரவும்.",
                "kn-IN": "ನಾನು ಸಹಾಯ ಮಾಡುತ್ತೇನೆ. ABHA ID ಅಥವಾ ನೋಂದಾಯಿಸಿದ phone number ಕೊಡಿ.",
                "hi-IN": "मैं basic eligibility pre-check कर सकता हूँ। अपना ABHA ID या registered phone number बताइए।",
                "en-IN": "I can do a basic eligibility pre-check. Please share your ABHA ID or registered phone number.",
            }
            missing_slots = ["abha_id_or_phone"]
        elif maternal_en or maternal_ta or maternal_kn or maternal_hi:
            intent = "maternal_health_reminder"
            responses = {
                "ta-IN": "உங்களுக்கு உதவுகிறேன். ANC visit, supplements, vaccination, அல்லது delivery follow-up எது வேண்டும்?",
                "kn-IN": "ನಾನು ಸಹಾಯ ಮಾಡುತ್ತೇನೆ. ANC visit, supplements, vaccination, ಅಥವಾ delivery follow-up ಯಾವುದು ಬೇಕು?",
                "hi-IN": "मैं maternal health reminder set कर सकता हूँ। ANC visit, supplements, vaccination, या delivery follow-up — कौनसा चाहिए?",
                "en-IN": "I can set maternal health reminders. Is this for ANC visit, supplements, vaccination, or expected delivery follow-up?",
            }
            missing_slots = ["reminder_type"]
        elif emerg_en or emerg_hi:
            intent = "emergency"
            responses = {
                "ta-IN": "இது அவசரநிலை போல் தெரிகிறது। உடனே அருகிலுள்ள emergency department-க்கு செல்லுங்கள் அல்லது emergency services-ஐ அழையுங்கள்.",
                "kn-IN": "ಇದು ತುರ್ತು ಪರಿಸ್ಥಿತಿ ಇರಬಹುದು. ತಕ್ಷಣ ಹತ್ತಿರದ emergency department-ಗೆ ಹೋಗಿ ಅಥವಾ emergency services-ಗೆ ಕರೆ ಮಾಡಿ.",
                "hi-IN": "यह emergency लग रहा है। तुरंत नजदीकी emergency department जाएँ या emergency services को call करें।",
                "en-IN": "This may be urgent. Please go to the nearest emergency department or call local emergency services now.",
            }
            missing_slots = []
        elif nav_en or nav_ta or nav_kn or nav_hi:
            intent = "hospital_navigation"
            responses = {
                "ta-IN": "உங்களுக்கு உதவுகிறேன். Registration, doctor consultation, lab, pharmacy, அல்லது maternal health — எந்த சேவை வேண்டும்?",
                "kn-IN": "ನಾನು ಸಹಾಯ ಮಾಡುತ್ತೇನೆ. Registration, doctor consultation, lab, pharmacy, ಅಥವಾ maternal health — ಯಾವ ಸೇವೆ ಬೇಕು?",
                "hi-IN": "मैं PHC के अंदर guide कर सकता हूँ। Registration, doctor consultation, lab, pharmacy, या maternal health — कौनसी service चाहिए?",
                "en-IN": "I can guide you inside the PHC. Which service do you need: registration, doctor consultation, lab, pharmacy, or maternal health?",
            }
            missing_slots = ["service"]
        else:
            intent = "nhm_programme_query"
            responses = {
                "ta-IN": "NHM programme பற்றிய கேள்விகளுக்கு உதவுகிறேன்.",
                "kn-IN": "NHM programme ಬಗ್ಗೆ ಸಹಾಯ ಮಾಡುತ್ತೇನೆ.",
                "hi-IN": "मैं NHM programme के बारे में जवाब दे सकता हूँ।",
                "en-IN": "I can answer NHM programme questions and guide you to the right PHC service.",
            }
            missing_slots = ["programme_or_service"]

        response = responses.get(language_code, responses["en-IN"])

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
            "missing_slots": missing_slots,
        }
