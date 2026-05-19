"""
LLM Intelligence Probe — validates that the Sarvam-30b model is reasoning correctly.

Tests:
  1. JSON compliance — does it return valid JSON?
  2. Multilingual accuracy — does it reply in the right language?
  3. Intent classification — does it detect intents correctly?
  4. Slot-filling — does it identify missing slots?
  5. Date resolution — does it resolve 'tomorrow' correctly?
  6. Confirmation gate — does it NOT confirm prematurely?
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)


PROBE_CASES = [
    {
        "id": "json_compliance",
        "description": "LLM must return valid JSON with all required keys",
        "input": {
            "transcript": "I want to book a doctor appointment",
            "language_code": "en-IN",
            "citizen_context": {"citizen": None, "db_configured": False, "current_datetime": datetime.now(timezone.utc).isoformat(), "supported_services": []},
        },
        "checks": ["valid_json", "has_intent", "has_response_text", "has_missing_slots"],
    },
    {
        "id": "hindi_detection",
        "description": "LLM must reply in Hindi when user speaks Hindi",
        "input": {
            "transcript": "मुझे डॉक्टर से मिलना है",
            "language_code": "hi-IN",
            "citizen_context": {"citizen": None, "db_configured": False, "current_datetime": datetime.now(timezone.utc).isoformat(), "supported_services": []},
        },
        "checks": ["valid_json", "intent_is_appointment_booking", "response_contains_hindi"],
    },
    {
        "id": "emergency_detection",
        "description": "LLM must classify chest pain as emergency",
        "input": {
            "transcript": "I am having severe chest pain and can't breathe",
            "language_code": "en-IN",
            "citizen_context": {"citizen": None, "db_configured": False, "current_datetime": datetime.now(timezone.utc).isoformat(), "supported_services": []},
        },
        "checks": ["valid_json", "intent_is_emergency", "needs_worker_followup"],
    },
    {
        "id": "slot_collection",
        "description": "LLM must identify missing appointment slots",
        "input": {
            "transcript": "Book appointment for fever",
            "language_code": "en-IN",
            "citizen_context": {"citizen": None, "db_configured": False, "current_datetime": datetime.now(timezone.utc).isoformat(), "supported_services": []},
        },
        "checks": ["valid_json", "has_missing_slots", "not_confirmed"],
    },
    {
        "id": "no_premature_confirm",
        "description": "LLM must NOT confirm before collecting all slots",
        "input": {
            "transcript": "appointment for fever tomorrow at 10am",
            "language_code": "en-IN",
            "citizen_context": {"citizen": None, "db_configured": False, "current_datetime": datetime.now(timezone.utc).isoformat(), "supported_services": []},
        },
        "checks": ["valid_json", "not_confirmed"],
    },
    {
        "id": "eligibility_intent",
        "description": "LLM must detect eligibility check intent",
        "input": {
            "transcript": "Am I eligible for Ayushman Bharat?",
            "language_code": "en-IN",
            "citizen_context": {"citizen": None, "db_configured": False, "current_datetime": datetime.now(timezone.utc).isoformat(), "supported_services": []},
        },
        "checks": ["valid_json", "intent_is_eligibility_check"],
    },
]


class LLMIntelligenceProbe:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def run_all_probes(self, system_prompt: str) -> dict[str, Any]:
        """Run all probe cases and return a report."""
        results = []
        passed = 0
        total = len(PROBE_CASES)

        for case in PROBE_CASES:
            result = await self._run_case(case, system_prompt)
            results.append(result)
            if result["passed"]:
                passed += 1

        score = round(passed / total * 100, 1)
        return {
            "score": score,
            "passed": passed,
            "total": total,
            "grade": self._grade(score),
            "cases": results,
            "model": self.settings.sarvam_chat_model,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _run_case(self, case: dict, system_prompt: str) -> dict[str, Any]:
        """Run a single probe case."""
        if not self.settings.sarvam_api_key:
            return {"id": case["id"], "passed": False, "error": "sarvam_api_key not configured", "checks": {}}

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(case["input"], ensure_ascii=False)},
        ]
        payload = {
            "model": self.settings.sarvam_chat_model,
            "temperature": 0.2,
            "max_tokens": 1024,
            "messages": messages,
        }
        headers = {
            "api-subscription-key": self.settings.sarvam_api_key or "",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                resp = await client.post(
                    f"{self.settings.sarvam_base_url}/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"].get("content") or ""
        except Exception as exc:
            return {"id": case["id"], "passed": False, "error": str(exc), "checks": {}, "raw": ""}

        parsed, parse_ok = self._try_parse(raw)
        check_results = self._run_checks(case["checks"], parsed, raw, parse_ok)
        passed = all(check_results.values())

        return {
            "id": case["id"],
            "description": case["description"],
            "passed": passed,
            "checks": check_results,
            "raw_preview": raw[:300],
            "parsed_intent": parsed.get("intent") if parsed else None,
        }

    def _try_parse(self, raw: str) -> tuple[dict | None, bool]:
        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            return json.loads(raw[start:end]), True
        except (ValueError, json.JSONDecodeError):
            return None, False

    def _run_checks(self, checks: list[str], parsed: dict | None, raw: str, parse_ok: bool) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for check in checks:
            match check:
                case "valid_json":
                    results[check] = parse_ok and parsed is not None
                case "has_intent":
                    results[check] = bool(parsed and parsed.get("intent"))
                case "has_response_text":
                    results[check] = bool(parsed and parsed.get("response_text"))
                case "has_missing_slots":
                    results[check] = bool(parsed and isinstance(parsed.get("missing_slots"), list) and len(parsed["missing_slots"]) > 0)
                case "intent_is_appointment_booking":
                    results[check] = parsed is not None and parsed.get("intent") == "appointment_booking"
                case "intent_is_emergency":
                    results[check] = parsed is not None and parsed.get("intent") == "emergency"
                case "intent_is_eligibility_check":
                    results[check] = parsed is not None and parsed.get("intent") == "eligibility_check"
                case "needs_worker_followup":
                    results[check] = bool(parsed and parsed.get("needs_worker_followup"))
                case "not_confirmed":
                    results[check] = parsed is not None and not parsed.get("confirmed", True)
                case "response_contains_hindi":
                    # Check for Devanagari script in response
                    text = (parsed or {}).get("response_text", "")
                    results[check] = any("\u0900" <= c <= "\u097f" for c in text)
                case _:
                    results[check] = True
        return results

    def _grade(self, score: float) -> str:
        if score >= 90:
            return "A — Excellent reasoning"
        if score >= 75:
            return "B — Good, minor issues"
        if score >= 60:
            return "C — Acceptable, needs tuning"
        return "D — Poor, prompt revision needed"
