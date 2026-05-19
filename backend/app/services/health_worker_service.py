"""
Health Worker AI Service — Sahayak

Supports ASHA workers and PHC nurses with:
  1. Protocol lookup (NHM / HBNC / IDSP / IMNCI)
  2. Voice-based patient record update with structured extraction
  3. Referral guidance with NHM escalation criteria
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .. import db
from ..config import get_settings

# ── System prompt ──────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = Path(__file__).resolve().parents[1].joinpath(
    "prompts/health_worker_system.txt"
).read_text(encoding="utf-8")

from .session_store import SessionStore
session_store = SessionStore("health_worker")


# ── Multilingual greetings ─────────────────────────────────────────────────────
_GREETINGS: dict[str, str] = {
    "ta-IN": "வணக்கம்! நான் Sahayak, உங்கள் clinical AI உதவியாளர். Protocol lookup, patient record அல்லது referral guidance — எதில் உதவட்டும்?",
    "kn-IN": "ನಮಸ್ಕಾರ! ನಾನು Sahayak, ನಿಮ್ಮ clinical AI ಸಹಾಯಕ. Protocol lookup, patient record ಅಥವಾ referral guidance — ಯಾವುದರಲ್ಲಿ ಸಹಾಯ ಮಾಡಲಿ?",
    "hi-IN": "नमस्ते! मैं Sahayak हूँ, आपका clinical AI सहायक। Protocol lookup, patient record या referral guidance — किसमें मदद करूँ?",
    "bho-IN": "प्रणाम! हम Sahayak हईं, राउर clinical AI सहायक। Protocol lookup, patient record या referral guidance — का चीज में मदद करीं?",
    "en-IN": "Hello! I'm Sahayak, your clinical AI assistant. How can I help — protocol lookup, patient record update, or referral guidance?",
}


class HealthWorkerService:
    def __init__(self) -> None:
        self.settings = get_settings()

    # ── Session start ──────────────────────────────────────────────────────────
    async def start_session(self, language_code: str = "en-IN", worker_role: str = "asha", session_id: str | None = None) -> dict[str, Any]:
        session_id = session_id or str(uuid.uuid4())
        intro = _GREETINGS.get(language_code, _GREETINGS["en-IN"])
        initial_meta = {
            "language_code": language_code,
            "worker_role": worker_role,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "turns": 0,
            "records_updated": 0,
        }
        await session_store.init_session(session_id, initial_meta, intro)
        return {"session_id": session_id, "intro_text": intro}

    # ── Text turn ──────────────────────────────────────────────────────────────
    async def handle_turn(
        self,
        text: str,
        language_code: str = "en-IN",
        session_id: str | None = None,
        worker_role: str = "asha",
    ) -> dict[str, Any]:
        if not self.settings.sarvam_api_key:
            return self._fallback(text, language_code)

        history = await session_store.get_history(session_id)
        meta = await session_store.get_meta(session_id)

        context = {
            "worker_role": worker_role,
            "language_code": language_code,
            "current_datetime": datetime.now(timezone.utc).isoformat(),
        }
        user_content = json.dumps(
            {"text": text, "language_code": language_code, "context": context},
            ensure_ascii=False,
        )

        messages: list[dict[str, str]] = [{"role": "system", "content": _SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_content})

        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(
                f"{self.settings.sarvam_base_url}/v1/chat/completions",
                headers={
                    "api-subscription-key": self.settings.sarvam_api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.settings.sarvam_chat_model,
                    "temperature": 0.15,
                    "max_tokens": 2048,
                    "messages": messages,
                },
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"].get("content", "")

        turn = self._parse(raw, text, language_code)

        # Persist patient record to DB if extracted
        if turn.get("intent") == "patient_record_update" and turn.get("patient_record") and db.is_configured():
            await self._save_patient_record(turn["patient_record"], session_id)
            if session_id:
                await session_store.set_meta(session_id, {"records_updated": meta.get("records_updated", 0) + 1})

        # Simulate prescription distribution
        if turn.get("intent") == "voice_prescription" and turn.get("prescription"):
            # Mocking SMS/ABHA distribution logic
            # In a real app, we'd look up the patient's phone and send via MSG91/Twilio
            p_name = (turn.get("patient_record") or {}).get("patient_name") or "Patient"
            print(f"Digital Prescription distributed for {p_name}")

        # Update session history
        if session_id:
            await session_store.append_turn(session_id, text, turn["response_text"])
            await session_store.set_meta(session_id, {"turns": meta.get("turns", 0) + 1})

        # TTS
        audio_b64 = await self._tts(turn["response_text"], language_code)
        turn["audio_base64"] = audio_b64
        turn["audio_mime_type"] = "audio/wav"
        return turn

    # ── Audio turn (STT → text turn) ───────────────────────────────────────────
    async def handle_audio_turn(
        self,
        audio: bytes,
        filename: str,
        content_type: str,
        session_id: str | None = None,
        worker_role: str = "asha",
    ) -> dict[str, Any]:
        stt = await self._stt(audio, filename, content_type)
        transcript = stt.get("transcript") or stt.get("text") or ""
        language_code = _normalise_lang(stt.get("language_code") or stt.get("language") or "en-IN")
        result = await self.handle_turn(transcript, language_code, session_id, worker_role)
        result["transcript"] = transcript
        return result

    # ── Internal helpers ───────────────────────────────────────────────────────
    def _parse(self, content: str, text: str, language_code: str) -> dict[str, Any]:
        try:
            s = content.index("{")
            e = content.rindex("}") + 1
            parsed = json.loads(content[s:e])
        except (ValueError, json.JSONDecodeError):
            return self._fallback(text, language_code)
        return {
            "intent": parsed.get("intent", "general_query"),
            "response_text": parsed.get("response_text", ""),
            "patient_record": parsed.get("patient_record"),
            "referral_level": parsed.get("referral_level", "none"),
            "referral_reason": parsed.get("referral_reason"),
            "protocol_name": parsed.get("protocol_name"),
            "action_points": parsed.get("action_points") or [],
            "needs_supervisor": bool(parsed.get("needs_supervisor", False)),
            "prescription": parsed.get("prescription"),
        }

    def _fallback(self, text: str, language_code: str) -> dict[str, Any]:
        msgs = {
            "ta-IN": "நான் சரியாக புரிந்துகொள்ளவில்லை. மீண்டும் சொல்லுங்கள்.",
            "kn-IN": "ನನಗೆ ಸರಿಯಾಗಿ ಅರ್ಥವಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಹೇಳಿ.",
            "hi-IN": "मुझे सही से समझ नहीं आया। कृपया दोबारा कहें।",
            "bho-IN": "हमरा सही से समझ ना आइल। कृप्या दोबारा कहीं।",
            "en-IN": "I didn't quite understand. Could you please rephrase?",
        }
        return {
            "intent": "general_query",
            "response_text": msgs.get(language_code, msgs["en-IN"]),
            "patient_record": None,
            "referral_level": "none",
            "referral_reason": None,
            "protocol_name": None,
            "action_points": [],
            "needs_supervisor": False,
        }

    async def _stt(self, audio: bytes, filename: str, content_type: str) -> dict[str, Any]:
        if not self.settings.sarvam_api_key:
            return {"transcript": "", "language_code": "en-IN"}
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(
                f"{self.settings.sarvam_base_url}/speech-to-text",
                headers={"api-subscription-key": self.settings.sarvam_api_key},
                data={"model": self.settings.sarvam_stt_model, "mode": "transcribe"},
                files={"file": (filename, audio, content_type)},
            )
            if resp.status_code in (400, 422):
                return {"transcript": "", "language_code": "en-IN"}
            resp.raise_for_status()
            return resp.json()

    async def _tts(self, text: str, language_code: str) -> str | None:
        if not self.settings.sarvam_api_key:
            return None
        _supported = {"ta-IN", "kn-IN", "hi-IN", "en-IN", "te-IN", "ml-IN"}
        lang = language_code if language_code in _supported else "hi-IN"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.settings.sarvam_base_url}/text-to-speech",
                headers={"api-subscription-key": self.settings.sarvam_api_key, "Content-Type": "application/json"},
                json={
                    "text": text[:2400],
                    "target_language_code": lang,
                    "model": self.settings.sarvam_tts_model,
                    "speaker": self.settings.sarvam_tts_speaker,
                    "output_audio_codec": "wav",
                    "speech_sample_rate": 24000,
                    "pace": 0.95,
                },
            )
            if not resp.is_success:
                return None
            audios = resp.json().get("audios") or []
            return audios[0] if audios else None

    async def _save_patient_record(self, record: dict[str, Any], session_id: str | None) -> None:
        if not record or not db.is_configured():
            return
        vitals = record.get("vitals") or {}
        await db.execute(
            """
            INSERT INTO health_worker_records
              (patient_name, age, gender, phone_number, chief_complaint,
               bp_systolic, bp_diastolic, weight_kg, hemoglobin, gestational_age_weeks,
               symptoms, diagnosis, treatment_given, next_visit_date,
               referred, referral_to, notes, session_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (
                record.get("patient_name"),
                record.get("age"),
                record.get("gender"),
                record.get("phone_number"),
                record.get("chief_complaint"),
                vitals.get("bp_systolic"),
                vitals.get("bp_diastolic"),
                vitals.get("weight_kg"),
                vitals.get("hemoglobin"),
                record.get("gestational_age_weeks"),
                json.dumps(record.get("symptoms") or []),
                record.get("diagnosis"),
                record.get("treatment_given"),
                record.get("next_visit_date"),
                bool(record.get("referred", False)),
                record.get("referral_to"),
                record.get("notes"),
                session_id,
            ),
        )

    async def get_session_summary(self, session_id: str) -> dict[str, Any]:
        meta = await session_store.get_meta(session_id)
        history = await session_store.get_history(session_id)
        return {
            "session_id": session_id,
            "worker_role": meta.get("worker_role", "asha"),
            "language_code": meta.get("language_code"),
            "turns": meta.get("turns", 0),
            "records_updated": meta.get("records_updated", 0),
            "started_at": meta.get("started_at"),
            "history_length": len(history),
        }


def _normalise_lang(code: str) -> str:
    c = code.lower().replace("_", "-")
    if c.startswith("ta"): return "ta-IN"
    if c.startswith("kn"): return "kn-IN"
    if c.startswith("hi"): return "hi-IN"
    if c.startswith("bho"): return "bho-IN"
    return "en-IN"
