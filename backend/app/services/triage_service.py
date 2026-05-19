"""
Symptom Triage Service.

Given a list of symptoms reported by the user, this service:
  1. Uses LLM to classify severity (low / medium / high / emergency)
  2. Recommends the most appropriate PHC department
  3. For emergency severity, triggers a worker-alert flag

This is NOT a diagnostic tool — it routes citizens to the right care level.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)

TRIAGE_SYSTEM_PROMPT = """You are a clinical triage assistant for Indian PHC (Primary Health Centres).

Given a JSON input with `symptoms` (list of symptom strings) and `language_code`, output ONLY valid JSON:
{
  "severity": "low" | "medium" | "high" | "emergency",
  "department": "<recommended PHC department name>",
  "advice": "<short voice-friendly advice in the user's language>",
  "needs_ambulance": true | false,
  "red_flags": ["<symptom that triggered high severity>"]
}

Severity rules:
- emergency: chest pain, difficulty breathing, heavy bleeding, loss of consciousness, stroke signs
- high: high fever (>103°F), severe abdominal pain, injury, severe vomiting
- medium: persistent cough, mild fever, moderate pain, skin rash
- low: routine checkup, mild cold, minor issues

NEVER diagnose. ALWAYS recommend PHC/ASHA or emergency services for high/emergency.
Reply ONLY with the JSON — no markdown, no explanation."""


class TriageService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def triage(self, symptoms: list[str], language_code: str = "en-IN") -> dict[str, Any]:
        """Classify symptom severity and recommend department."""
        if not symptoms:
            return self._default_triage(language_code)

        if not self.settings.sarvam_api_key:
            return self._rule_based_triage(symptoms, language_code)

        try:
            return await self._llm_triage(symptoms, language_code)
        except Exception as exc:
            logger.warning("LLM triage failed: %s — falling back to rules", exc)
            return self._rule_based_triage(symptoms, language_code)

    # ------------------------------------------------------------------
    # LLM triage
    # ------------------------------------------------------------------

    async def _llm_triage(self, symptoms: list[str], language_code: str) -> dict[str, Any]:
        user_content = json.dumps({"symptoms": symptoms, "language_code": language_code}, ensure_ascii=False)
        payload = {
            "model": self.settings.sarvam_chat_model,
            "temperature": 0.1,
            "max_tokens": 512,
            "messages": [
                {"role": "system", "content": TRIAGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        }
        headers = {
            "api-subscription-key": self.settings.sarvam_api_key or "",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.settings.sarvam_base_url}/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            if resp.status_code == 429:
                logger.warning("Triage API rate limit (429). Falling back to rule-based triage.")
                return self._rule_based_triage(symptoms, language_code)
            resp.raise_for_status()
        content = resp.json()["choices"][0]["message"].get("content") or ""
        try:
            start = content.index("{")
            end = content.rindex("}") + 1
            return json.loads(content[start:end])
        except (ValueError, json.JSONDecodeError):
            return self._rule_based_triage(symptoms, language_code)

    # ------------------------------------------------------------------
    # Rule-based fallback
    # ------------------------------------------------------------------

    EMERGENCY_KEYWORDS = {
        "chest pain", "heart attack", "can't breathe", "stroke", "unconscious",
        "heavy bleeding", "सीने में दर्द", "छाती में दर्द", "மார்பு வலி", "ಎದೆ ನೋವು",
        "breathing difficulty", "accident", "khoon", "saas", "chhati", "seenwa",
    }
    HIGH_KEYWORDS = {
        "high fever", "severe pain", "vomiting blood", "injury", "fracture",
        "तेज बुखार", "சுற்றி வருகிறது", "ಹೆಚ್ಚಿನ ಜ್ವರ", "tez bukhar", "chot", "dard",
    }
    MATERNAL_KEYWORDS = {
        "pregnant", "pregnancy", "anc", "delivery", "गर्भ", "கர்ப்பம்", "ಗರ್ಭ",
    }

    def _rule_based_triage(self, symptoms: list[str], language_code: str) -> dict[str, Any]:
        text = " ".join(symptoms).lower()

        if any(k in text for k in self.EMERGENCY_KEYWORDS):
            advice_map = {
                "ta-IN": "இது அவசரநிலை. உடனே Emergency-க்கு போங்கள் அல்லது 108 call பண்ணுங்கள்.",
                "hi-IN": "यह emergency है। तुरंत Emergency department जाएं या 108 call करें।",
                "bho-IN": "ई emergency बा। तुरंत Emergency विभाग जाईं या 108 कॉल करीं।",
                "kn-IN": "ಇದು ತುರ್ತು. ತಕ್ಷಣ Emergency ಗೆ ಹೋಗಿ ಅಥವಾ 108 ಕರೆ ಮಾಡಿ.",
                "en-IN": "This is an emergency. Go to the Emergency department immediately or call 108.",
            }
            return {
                "severity": "emergency",
                "department": "Emergency / Casualty",
                "advice": advice_map.get(language_code, advice_map["en-IN"]),
                "needs_ambulance": True,
                "red_flags": [s for s in symptoms if any(k in s.lower() for k in self.EMERGENCY_KEYWORDS)],
            }

        if any(k in text for k in self.HIGH_KEYWORDS):
            return {
                "severity": "high",
                "department": "General OPD",
                "advice": "Please visit the OPD immediately. A doctor should examine you today.",
                "needs_ambulance": False,
                "red_flags": [],
            }

        if any(k in text for k in self.MATERNAL_KEYWORDS):
            return {
                "severity": "medium",
                "department": "Maternal & Child Health",
                "advice": "Please visit the MCH section. Your ASHA worker can escort you.",
                "needs_ambulance": False,
                "red_flags": [],
            }

        return self._default_triage(language_code)

    def _default_triage(self, language_code: str) -> dict[str, Any]:
        advice_map = {
            "ta-IN": "Registration counter-ல் பெயர் பதிவு செய்து General OPD-க்கு செல்லுங்கள்.",
            "hi-IN": "Registration counter पर अपना नाम दर्ज करें और General OPD में जाएं।",
            "bho-IN": "Registration काउंटर पर नाम दर्ज करीं आउर General OPD में जाईं।",
            "kn-IN": "Registration counter ನಲ್ಲಿ ನಿಮ್ಮ ಹೆಸರು ನೋಂದಾಯಿಸಿ General OPD ಗೆ ಹೋಗಿ.",
            "en-IN": "Please register at the counter and proceed to General OPD.",
        }
        return {
            "severity": "low",
            "department": "General OPD",
            "advice": advice_map.get(language_code, advice_map["en-IN"]),
            "needs_ambulance": False,
            "red_flags": [],
        }
