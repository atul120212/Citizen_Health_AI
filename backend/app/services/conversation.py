"""
ConversationService — Production voice-only agent with full identity-verification flow.

State machine:
  NEW SESSION
      │
      ▼
  WAKE_DETECTED  → agent plays multilingual intro + asks for mobile/ABHA ID
      │
      ▼
  VERIFYING      → user speaks their ID → STT → verify against DB
      │
      ├─ found  → VERIFIED   → personalized greeting → free conversation
      └─ not found → GUEST   → guest mode, limited features
      
  CONVERSATION   → RAG-augmented LLM + MCP tool calls
      │
      ▼
  SESSION_END    → post-call summary spoken + stored
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from .. import db
from ..schemas import SessionStartResponse, VoiceTurnResponse
from .email_service import send_appointment_confirmation
from .mcp_tools import MCPExecutor
from .rag_service import RAGService
from .repository import (
    create_followup_appointment,
    create_interaction,
    create_maternal_reminder,
    get_citizen_by_phone,
    get_nearest_departments,
    set_ayushman_precheck,
    upsert_citizen,
    log_patient_vital,
    update_medication_adherence,
)
from .sarvam import SarvamService
from .triage_service import TriageService

from .session_store import SessionStore

session_store = SessionStore("citizen")

# ─────────────────────────────────────────────────────────────
# Multilingual intro lines (before verification)
# ─────────────────────────────────────────────────────────────

_INTRO_TEXTS: dict[str, str] = {
    "ta-IN": "வணக்கம்! நான் Aarogya. இன்று நான் உங்களுக்கு எப்படி உதவலாம்?",
    "kn-IN": "ನಮಸ್ಕಾರ! ನಾನು Aarogya. ಇಂದು ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?",
    "hi-IN": "नमस्ते! मैं Aarogya हूँ। आज मैं आपकी कैसे मदद कर सकता हूँ?",
    "bho-IN": "प्रणाम! हम Aarogya हईं। आज हम राउर कइसे मदद कर सकीं?",
    "en-IN": "Namaste! I'm Aarogya. How may I help you today?",
}

_VERIFIED_GREETING: dict[str, str] = {
    "ta-IN": "நலம்! {name}, எப்படி இருக்கீங்க? இன்று நான் உங்களுக்கு எப்படி உதவலாம்?",
    "kn-IN": "ಸ್ವಾಗತ! {name}, ನೀವು ಹೇಗಿದ್ದೀರಿ? ಇಂದು ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?",
    "hi-IN": "स्वागत है {name}! आप कैसे हैं? आज मैं आपकी कैसे मदद कर सकता हूँ?",
    "bho-IN": "स्वागत बा {name}! रउवा कइसन बानी? आज हम राउर कइसे मदद कर सकीं?",
    "en-IN": "Welcome back, {name}! How are you doing? How can I help you today?",
}

_GUEST_GREETING: dict[str, str] = {
    "ta-IN": "உங்கள் ID கணினியில் இல்லை. Guest ஆக தொடர்கிறோம். என்ன உதவி வேண்டும்?",
    "kn-IN": "ನಿಮ್ಮ ID ದಾಖಲೆಯಲ್ಲಿ ಇಲ್ಲ. Guest ಆಗಿ ಮುಂದುವರಿಯೋಣ. ನಿಮಗೆ ಏನು ಬೇಕು?",
    "hi-IN": "आपकी ID हमारे रिकॉर्ड में नहीं है। Guest के रूप में आगे बढ़ते हैं। मैं क्या मदद कर सकता हूँ?",
    "bho-IN": "राउर ID हमरा रिकॉर्ड में नइखे। Guest के रूप में आगे बढ़त बानी। हम का मदद कर सकीं?",
    "en-IN": "Your ID wasn't found in our records. We'll continue as a guest. How can I help you?",
}

_SESSION_END_TEXTS: dict[str, str] = {
    "ta-IN": "நன்றி! உங்கள் நலனில் கவனமாக இருங்கள். மீண்டும் தேவைப்பட்டால் அழைக்கவும். வணக்கம்!",
    "kn-IN": "ಧನ್ಯವಾದ! ನಿಮ್ಮ ಆರೋಗ್ಯವನ್ನು ಕಾಪಾಡಿಕೊಳ್ಳಿ. ಮತ್ತೆ ಸಂಪರ್ಕಿಸಿ. ನಮಸ್ಕಾರ!",
    "hi-IN": "धन्यवाद! अपना ख्याल रखें। जरूरत पड़ने पर दोबारा संपर्क करें। नमस्ते!",
    "bho-IN": "धन्यवाद! आपन खयाल रखीं। जरूरत पड़े पर फिर से संपर्क करीं। प्रणाम!",
    "en-IN": "Thank you! Take good care of yourself. Call again if you need help. Goodbye!",
}


# ─────────────────────────────────────────────────────────────
# Citizen identity resolution helpers
# ─────────────────────────────────────────────────────────────

def _extract_digits(text: str) -> str:
    """Extract only digit characters from a transcript."""
    return "".join(c for c in text if c.isdigit())


def _is_low_quality_transcript(transcript: str) -> bool:
    """Detect STT echo/hallucination (e.g. repeated 'சரி' / 'okay') or noise."""
    text = transcript.strip()
    if not text:
        return True
    words = text.split()
    if len(words) >= 3:
        from collections import Counter

        top_count = Counter(words).most_common(1)[0][1]
        if top_count / len(words) >= 0.65:
            return True
    compact = "".join(text.split())
    if len(compact) > 80 and len(set(compact)) <= 5:
        return True
    return False


async def _resolve_citizen(identifier: str) -> dict[str, Any] | None:
    """Try phone number first, then ABHA ID."""
    if not db.is_configured():
        return None
    digits = _extract_digits(identifier)
    if not digits:
        return None
    # 10-digit mobile number
    if len(digits) == 10:
        citizen = await get_citizen_by_phone(digits)
        if citizen:
            return citizen
    # ABHA IDs can be 12 digits (formatted as 91-XXXX-XXXX-XXXX)
    citizen = await db.fetch_one(
        "SELECT c.*, l.district_name, l.phc_name FROM citizens c LEFT JOIN locations l ON l.id = c.location_id WHERE REGEXP_REPLACE(c.abha_id, '[^0-9]', '', 'g') = %s",
        (digits,),
    )
    return citizen


# ─────────────────────────────────────────────────────────────
# ConversationService
# ─────────────────────────────────────────────────────────────

class ConversationService:
    def __init__(self) -> None:
        self.sarvam = SarvamService()
        self.rag = RAGService()
        self.mcp = MCPExecutor()
        self.triage_svc = TriageService()

    # ──────────────────────────────────────────────────────────
    # Session intro (wake-word detected)
    # ──────────────────────────────────────────────────────────

    async def start_session(
        self,
        phone_number: str | None,
        language_code: str,
    ) -> SessionStartResponse:
        language_code = self._normalise_language(language_code)
        session_id = str(uuid.uuid4())

        intro_text = _INTRO_TEXTS.get(language_code, _INTRO_TEXTS["en-IN"])

        # Session metadata — tracks verification state
        initial_meta = {
            "verification_state": "pending",  # pending | verified | guest | verified_worker
            "language_code": language_code,
            "citizen": None,
            "call_summary": None,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "turns": 0,
        }

        # If a phone_number is already provided (e.g. from kiosk), pre-verify
        if phone_number and db.is_configured():
            citizen = await get_citizen_by_phone(phone_number)
            if citizen:
                lang = self._normalise_language(citizen.get("preferred_language", "en") + "-IN")
                language_code = lang
                greeting = _VERIFIED_GREETING.get(lang, _VERIFIED_GREETING["en-IN"]).format(
                    name=citizen["full_name"] or "there"
                )
                intro_text = greeting
                initial_meta.update({
                    "verification_state": "verified",
                    "citizen": citizen,
                    "language_code": lang,
                })

        await session_store.init_session(session_id, initial_meta, intro_text)

        audio_base64 = await self.sarvam.text_to_speech(intro_text, language_code)

        return SessionStartResponse(
            session_id=session_id,
            intro_text=intro_text,
            audio_base64=audio_base64,
            audio_mime_type="audio/wav",
        )

    # ──────────────────────────────────────────────────────────
    # Audio turn (STT → text turn)
    # ──────────────────────────────────────────────────────────

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
        # Sync language from STT into session meta (auto-detect from voice)
        if session_id:
            meta = await session_store.get_meta(session_id)
            if not meta.get("language_code"):
                await session_store.set_meta(session_id, {"language_code": language_code})

        return await self.handle_text_turn(
            transcript=transcript,
            language_code=language_code,
            phone_number=phone_number,
            language_probability=stt.get("language_probability"),
            session_id=session_id,
        )

    # ──────────────────────────────────────────────────────────
    # Text turn (core logic with verification state machine)
    # ──────────────────────────────────────────────────────────

    async def handle_text_turn(
        self,
        transcript: str,
        language_code: str,
        phone_number: str | None = None,
        language_probability: float | None = None,
        session_id: str | None = None,
    ) -> VoiceTurnResponse:
        language_code = self._normalise_language(language_code)
        meta = await session_store.get_meta(session_id)
        verification_state = meta.get("verification_state", "verified")
        citizen = meta.get("citizen")

        # ── Empty / garbage transcript guard (silent STT, echo loops) ───────
        if not transcript or not transcript.strip() or _is_low_quality_transcript(transcript):
            silence_prompts: dict[str, str] = {
                "ta-IN": "மன்னிக்கவும், சரியாக கேட்கவில்லை. மீண்டும் சொல்லுங்கள்.",
                "kn-IN": "ಕ್ಷಮಿಸಿ, ಸರಿಯಾಗಿ ಕೇಳಿಸಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಹೇಳಿ.",
                "hi-IN": "माफ करें, सुनाई नहीं दिया। कृपया फिर से बोलें।",
                "bho-IN": "माफ करीं, सुनाई ना देलस। कृप्या फिर से बोलीं।",
                "en-IN": "Sorry, I didn't hear that. Could you please repeat?",
            }
            msg = silence_prompts.get(language_code, silence_prompts["en-IN"])
            audio_b64 = await self.sarvam.text_to_speech(msg, language_code)
            return VoiceTurnResponse(
                transcript="",
                language_code=language_code,
                language_probability=language_probability,
                intent="fallback",
                response_text=msg,
                audio_base64=audio_b64,
                citizen_id=citizen["id"] if citizen else None,
                interaction_id=None,
                actions=[],
                db_configured=db.is_configured(),
            )

        # ── VERIFICATION PHASE ────────────────────────────────
        # Deprecated: The LLM now handles asking for identity naturally when needed.
        # if verification_state == "pending":
        #     return await self._handle_verification(...)

        # ── HEALTH WORKER PHASE ───────────────────────────────
        if verification_state == "verified_worker":
            worker = meta.get("worker", {})
            from .health_worker_service import HealthWorkerService
            hw_svc = HealthWorkerService()
            result = await hw_svc.handle_turn(transcript, language_code, session_id, worker.get("role", "asha"))
            
            return VoiceTurnResponse(
                transcript=transcript,
                language_code=language_code,
                language_probability=language_probability,
                intent=result.get("intent", "general_query"),
                response_text=result.get("response_text", ""),
                audio_base64=result.get("audio_base64"),
                citizen_id=None,
                interaction_id=None,
                actions=[result],
                db_configured=db.is_configured(),
            )

        # ── VERIFIED / GUEST PHASE ────────────────────────────
        # Only attempt auto-verify from transcript digits if NOT currently filling appointment slots
        # (prevents phone numbers given for appointment booking being treated as IDs)
        active_intent = meta.get("active_intent")
        if citizen is None and db.is_configured() and active_intent != "appointment_booking":
            # Try auto-verifying if the user mentioned a mobile number (10 digits) or ABHA ID (12-14 digits)
            digits = _extract_digits(transcript)
            if digits and (len(digits) == 10 or len(digits) >= 12):
                from .repository import get_health_worker_by_phone
                worker = None
                if len(digits) == 10:
                    worker = await get_health_worker_by_phone(digits)
                
                if worker:
                    verification_state = "verified_worker"
                    if session_id:
                        await session_store.set_meta(session_id, {
                            "verification_state": "verified_worker",
                            "worker": worker
                        })
                else:
                    found_citizen = await _resolve_citizen(digits)
                    if found_citizen:
                        citizen = found_citizen
                        verification_state = "verified"
                        if session_id:
                            await session_store.set_meta(session_id, {
                                "verification_state": "verified",
                                "citizen": citizen
                            })
            
            # Fallback to kiosk-passed phone number if not verified by transcript
            if citizen is None and phone_number:
                citizen = await get_citizen_by_phone(phone_number)
        elif citizen is None and phone_number and db.is_configured():
            citizen = await get_citizen_by_phone(phone_number)

        context: dict[str, Any] = {
            "citizen": citizen,
            "verification_state": verification_state,
            "db_configured": db.is_configured(),
            "current_datetime": datetime.now(timezone.utc).isoformat(),
            "supported_services": [
                "hospital_navigation",
                "eligibility_check",
                "appointment_booking",
                "maternal_health_reminder",
                "nhm_programme_query",
            ],
        }

        history = await session_store.get_history(session_id)
        active_intent = meta.get("active_intent")
        slot_state: dict[str, Any] = dict(meta.get("slot_state") or {})
        context["active_intent"] = active_intent
        context["slot_state"] = slot_state

        # RAG augmentation
        rag_chunks = await self.rag.retrieve(transcript, language_code)
        rag_context = self.rag.format_context(rag_chunks) if rag_chunks else None

        # Live Web Search Fallback for local navigation / phone number requests
        # Skip search if: user is sharing a phone/ID OR currently in appointment slot-fill
        has_id_format = any(c.isdigit() for c in transcript) and len([c for c in transcript if c.isdigit()]) >= 10
        is_appointment_filling = active_intent == "appointment_booking"
        is_search_intent = (not has_id_format) and (not is_appointment_filling) and any(w in transcript.lower() for w in [
            "helpline", "contact", "address",
            "hospital", "phc", "clinic", "where is", "route", "direction",
            "how to reach", "get the number", "find hospital",
        ])
        if is_search_intent:
            from .search_service import search_health_web
            # Build search query based on user's query
            search_query = transcript
            if "hospital" not in search_query.lower() and "phc" not in search_query.lower() and "clinic" not in search_query.lower():
                search_query += " hospital phone number contact helpline"
            
            web_results = await search_health_web(search_query)
            if web_results:
                if rag_context:
                    rag_context += "\n\n" + web_results
                else:
                    rag_context = web_results

        turn = await self.sarvam.classify_and_reply(
            transcript,
            language_code,
            context,
            history=history,
            rag_context=rag_context,
            active_intent=active_intent,
            slot_state=slot_state,
        )

        # MCP tool execution
        booking_completed = False
        if turn.get("tool_call"):
            tc = turn["tool_call"]
            
            # --- Triage Interception for Appointments ---
            if tc.get("name") == "book_appointment" and turn.get("appointment_reason"):
                triage_res = await self.triage_svc.triage([turn["appointment_reason"]], language_code)
                if triage_res["severity"] in ["emergency", "high"]:
                    # Intercept: redirect to emergency advice instead of booking
                    turn["intent"] = "emergency"
                    turn["response_text"] = triage_res["advice"]
                    turn["needs_worker_followup"] = True
                    # Prevent the actual tool call
                    turn["tool_call"] = None
            
            if turn.get("tool_call"): # re-check after possible interception
                tool_result = await self.mcp.execute(tc.get("name", ""), tc.get("args", {}), citizen)
                if tc.get("name") == "book_appointment":
                    booking_completed = True
                tool_context = dict(context)
                tool_context["tool_result"] = tool_result
                turn = await self.sarvam.classify_and_reply(
                    transcript,
                    language_code,
                    tool_context,
                    history=history,
                    rag_context=rag_context,
                    active_intent=active_intent,
                    slot_state=slot_state,
                )

        # Handle inline identity verification
        if turn["intent"] == "verify_identity":
            extracted_id = turn.get("identifier") or _extract_digits(transcript)
            worker = None
            if extracted_id and len(extracted_id) >= 10:
                from .repository import get_health_worker_by_phone
                worker = await get_health_worker_by_phone(extracted_id)
                if not worker:
                    citizen = await _resolve_citizen(extracted_id)
            
            if worker:
                if session_id:
                    await session_store.set_meta(session_id, {"verification_state": "verified_worker", "worker": worker})
                turn["response_text"] += f" Welcome back, {worker.get('name') or 'Worker'}."
            elif citizen:
                if session_id:
                    await session_store.set_meta(session_id, {"verification_state": "verified", "citizen": citizen})
                turn["response_text"] = _VERIFIED_GREETING.get(language_code, _VERIFIED_GREETING["en-IN"]).format(name=citizen.get("full_name") or "there") + " " + turn["response_text"]
            else:
                if session_id:
                    await session_store.set_meta(session_id, {"verification_state": "guest"})
                turn["response_text"] = "I couldn't find your ID. " + turn["response_text"]

        # Handle session end
        if turn["intent"] == "session_end":
            summary = turn.get("call_summary") or _SESSION_END_TEXTS.get(language_code, _SESSION_END_TEXTS["en-IN"])
            if session_id:
                await session_store.set_meta(session_id, {"call_summary": summary})
            turn["response_text"] = summary

        actions = await self._apply_actions(turn, citizen, transcript=transcript, language_code=language_code)

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

        await session_store.append_turn(session_id, transcript, response_text)
        if session_id:
            meta_updates: dict[str, Any] = {"turns": meta.get("turns", 0) + 1}
            if turn["intent"] == "session_end" or booking_completed:
                meta_updates["active_intent"] = None
                meta_updates["slot_state"] = {}
            else:
                meta_updates["active_intent"] = turn["intent"]
                new_slots = dict(slot_state)
                for key in (
                    "appointment_reason",
                    "appointment_date",
                    "appointment_time",
                    "patient_email",
                    "patient_name",
                ):
                    if turn.get(key):
                        new_slots[key] = turn[key]
                if turn["intent"] == "appointment_booking":
                    meta_updates["slot_state"] = new_slots
                elif turn["intent"] != meta.get("active_intent"):
                    meta_updates["slot_state"] = {}
            await session_store.set_meta(session_id, meta_updates)

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

    # ──────────────────────────────────────────────────────────
    # Verification phase handler
    # ──────────────────────────────────────────────────────────

    async def _handle_verification(
        self,
        transcript: str,
        language_code: str,
        language_probability: float | None,
        session_id: str | None,
        meta: dict[str, Any],
    ) -> VoiceTurnResponse:
        """
        Called when verification_state == "pending".
        Tries to extract a phone/ABHA identifier from the transcript.
        """
        citizen: dict[str, Any] | None = None
        response_text: str
        intent: str
        actions: list[dict] = []

        # Use LLM to extract the identifier from natural speech
        context: dict[str, Any] = {
            "citizen": None,
            "verification_state": "pending",
            "db_configured": db.is_configured(),
            "current_datetime": datetime.now(timezone.utc).isoformat(),
            "supported_services": [],
        }
        history = await session_store.get_history(session_id)
        turn = await self.sarvam.classify_and_reply(transcript, language_code, context, history=history)

        extracted_id = turn.get("identifier") or _extract_digits(transcript)

        worker: dict[str, Any] | None = None
        if extracted_id and len(extracted_id) >= 10:
            from .repository import get_health_worker_by_phone
            worker = await get_health_worker_by_phone(extracted_id)
            if not worker:
                citizen = await _resolve_citizen(extracted_id)

        if worker:
            language_code = self._normalise_language(language_code)
            response_text = {
                "ta-IN": f"வணக்கம்! {worker.get('name') or 'Health Worker'}. நீங்கள் {worker.get('role') or 'Health Worker'} ஆக இணைக்கப்பட்டுள்ளீர்கள்.",
                "kn-IN": f"ನಮಸ್ಕಾರ! {worker.get('name') or 'Health Worker'}. ನೀವು {worker.get('role') or 'Health Worker'} ಆಗಿ ಸಂಪರ್ಕಗೊಂಡಿದ್ದೀರಿ.",
                "hi-IN": f"नमस्ते! {worker.get('name') or 'Health Worker'}। आप {worker.get('role') or 'Health Worker'} के रूप में जुड़े हैं।",
                "bho-IN": f"प्रणाम! {worker.get('name') or 'Health Worker'}। रउवा {worker.get('role') or 'Health Worker'} के रूप में जुड़ल बानी।",
                "en-IN": f"Welcome back, {worker.get('name') or 'Health Worker'}! You are connected as a {worker.get('role') or 'Health Worker'}.",
            }.get(language_code, f"Welcome back, {worker.get('name') or 'Health Worker'}! You are connected as a {worker.get('role') or 'Health Worker'}.")
            
            intent = "verify_identity"
            if session_id:
                await session_store.set_meta(session_id, {
                    "verification_state": "verified_worker",
                    "worker": worker,
                    "language_code": language_code,
                })
                from .health_worker_service import HealthWorkerService
                await HealthWorkerService().start_session(language_code, worker.get("role", "asha"), session_id=session_id)
                
            actions.append({
                "type": "worker_verified",
                "worker_id": worker["id"],
                "worker_name": worker.get("name"),
                "role": worker.get("role"),
            })
        elif citizen:
            # Citizen verified successfully
            citizen_lang = self._normalise_language(
                citizen.get("preferred_language", language_code[:2]) + "-IN"
            )
            language_code = citizen_lang
            response_text = _VERIFIED_GREETING.get(citizen_lang, _VERIFIED_GREETING["en-IN"]).format(
                name=citizen.get("full_name") or "there"
            )
            intent = "verify_identity"
            if session_id:
                await session_store.set_meta(session_id, {
                    "verification_state": "verified",
                    "citizen": citizen,
                    "language_code": language_code,
                })
            actions.append({
                "type": "citizen_verified",
                "citizen_id": citizen["id"],
                "citizen_name": citizen.get("full_name"),
                "phc": citizen.get("phc_name"),
                "ayushman_eligible": bool(citizen.get("abha_id") or citizen.get("ayushman_status")),
            })
        elif extracted_id and len(extracted_id) >= 8:
            # Had digits but not found — offer guest mode
            response_text = _GUEST_GREETING.get(language_code, _GUEST_GREETING["en-IN"])
            intent = "verification_failed"
            if session_id:
                await session_store.set_meta(session_id, {"verification_state": "guest"})
            actions.append({"type": "guest_mode"})
        else:
            # No digits detected — ask again
            ask_again: dict[str, str] = {
                "ta-IN": "மன்னிக்கவும், சரியாக கேட்கவில்லை. உங்கள் 10 இலக்க mobile number சொல்லுங்கள்.",
                "kn-IN": "ಕ್ಷಮಿಸಿ, ಸರಿಯಾಗಿ ಕೇಳಿಸಲಿಲ್ಲ. ನಿಮ್ಮ 10 ಅಂಕಿ mobile number ಹೇಳಿ.",
                "hi-IN": "माफ करें, सुनाई नहीं दिया। अपना 10 अंकों का mobile number बताएं।",
                "bho-IN": "माफ करीं, सुनाई ना देलस। आपन 10 अंक के मोबाइल नंबर बताईं।",
                "en-IN": "Sorry, I didn't catch that. Please say your 10-digit mobile number.",
            }
            response_text = ask_again.get(language_code, ask_again["en-IN"])
            intent = "verify_identity"

        # Log the verification attempt
        if db.is_configured():
            await create_interaction(
                citizen_id=citizen["id"] if citizen else None,
                transcript=transcript,
                intent=intent,
                audio_url=None,
                needs_worker_followup=False,
                interaction_type="voice_call",
            )

        audio_base64 = await self.sarvam.text_to_speech(response_text, language_code)
        await session_store.append_turn(session_id, transcript, response_text)

        return VoiceTurnResponse(
            transcript=transcript,
            language_code=language_code,
            language_probability=language_probability,
            intent=intent,
            response_text=response_text,
            audio_base64=audio_base64,
            citizen_id=citizen["id"] if citizen else None,
            interaction_id=None,
            actions=actions,
            db_configured=db.is_configured(),
        )

    # ──────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────

    async def _apply_actions(
        self,
        turn: dict[str, Any],
        citizen: dict[str, Any] | None,
        transcript: str = "",
        language_code: str = "en-IN",
    ) -> list[dict[str, Any]]:
        intent = turn["intent"]
        actions: list[dict[str, Any]] = []

        if intent == "appointment_booking" and turn.get("confirmed") and not turn.get("missing_slots"):
            appt_date_str = turn.get("appointment_date")
            appt_time_str = turn.get("appointment_time")
            reason        = turn.get("appointment_reason") or "General consultation"
            patient_name  = turn.get("patient_name") or (citizen["full_name"] if citizen else "Patient")
            patient_email = turn.get("patient_email")
            phc_name      = citizen.get("phc_name", "Your PHC") if citizen else "Your PHC"

            appt_dt: datetime | None = None
            if appt_date_str:
                try:
                    appt_dt = datetime.fromisoformat(appt_date_str).replace(tzinfo=timezone.utc)
                except ValueError:
                    appt_dt = None

            if db.is_configured() and citizen:
                appointment = await create_followup_appointment(
                    citizen_id=citizen["id"],
                    reason=reason,
                    appointment_date=appt_dt,
                    appointment_time=appt_time_str,
                )
                if appointment:
                    actions.append({
                        "type": "appointment_created",
                        "appointment_id": appointment["id"],
                        "date": appt_date_str,
                        "time": appt_time_str,
                        "reason": reason,
                    })
            else:
                actions.append({
                    "type": "appointment_created",
                    "appointment_id": None,
                    "date": appt_date_str,
                    "time": appt_time_str,
                    "reason": reason,
                    "demo": True,
                })

            if patient_email:
                email_ok = await send_appointment_confirmation(
                    to_email=patient_email,
                    patient_name=patient_name,
                    reason=reason,
                    date=appt_date_str or "TBD",
                    time=appt_time_str or "TBD",
                    phc=phc_name,
                    language_code=language_code,
                )
                if email_ok:
                    actions.append({"type": "email_sent", "to": patient_email})
                else:
                    actions.append({"type": "email_failed", "to": patient_email})

        if intent == "maternal_health_reminder" and db.is_configured() and citizen:
            reminder = await create_maternal_reminder(
                citizen_id=citizen["id"],
                reminder_type=turn.get("maternal_reminder_type") or "anc",
            )
            if reminder:
                actions.append({"type": "maternal_reminder_created", "reminder_id": reminder["id"]})

        if intent == "eligibility_check" and db.is_configured() and citizen:
            eligible = bool(citizen.get("abha_id") or citizen.get("ayushman_status"))
            updated = await set_ayushman_precheck(citizen["id"], eligible)
            actions.append({
                "type": "eligibility_precheck",
                "eligible": eligible,
                "citizen_id": updated["id"] if updated else citizen["id"],
            })

        if intent == "hospital_navigation":
            # Use service_query from slot_state, appointment_reason, or raw transcript
            nav_query = (
                (turn.get("slot_state") or {}).get("service_query")
                or turn.get("appointment_reason")
                or transcript
            )
            departments = await get_nearest_departments(nav_query)
            actions.append({"type": "department_matches", "departments": departments})

        if intent == "register_citizen" and db.is_configured():
            slot_state = turn.get("slot_state") or {}
            # Use name from ABHA flow or previous patient name
            reg_name = slot_state.get("abha_name") or turn.get("patient_name")
            # Use phone from verification or extracted identifier
            reg_phone = turn.get("identifier")
            if not reg_phone and citizen:
                reg_phone = citizen.get("phone_number")
            
            # Simulated ABHA ID generation if they completed the steps
            abha_id = None
            if slot_state.get("abha_aadhaar") and slot_state.get("abha_name"):
                import random
                abha_id = f"91-{random.randint(1000,9999)}-{random.randint(1000,9999)}-{random.randint(1000,9999)}"
            
            if reg_phone:
                from ..schemas import CitizenUpsert
                from .repository import upsert_citizen
                new_cit = await upsert_citizen(CitizenUpsert(
                    phone_number=reg_phone,
                    full_name=reg_name,
                    abha_id=abha_id,
                    preferred_language=language_code[:2]
                ))
                if new_cit:
                    actions.append({
                        "type": "citizen_registered",
                        "phone": reg_phone,
                        "abha_id": abha_id,
                        "name": reg_name
                    })

        if intent == "vitals_tracking" and db.is_configured() and citizen:
            slot_state = turn.get("slot_state") or {}
            v_type = slot_state.get("vital_type")
            v_val_str = slot_state.get("vital_value")
            
            # Simple numeric extraction
            v_val = None
            if v_val_str:
                import re
                nums = re.findall(r"\d+\.?\d*", v_val_str)
                if nums:
                    v_val = float(nums[0]) # Just take the first number for now
            
            if v_type and v_val is not None:
                vital = await log_patient_vital(
                    citizen_id=citizen["id"],
                    vital_type=v_type,
                    value=v_val,
                    unit=slot_state.get("vital_unit")
                )
                if vital:
                    actions.append({"type": "vital_logged", "vital_type": v_type, "value": v_val})

        if intent == "med_adherence" and db.is_configured() and citizen:
            slot_state = turn.get("slot_state") or {}
            med_name = slot_state.get("medication_name")
            if med_name:
                adherence = await update_medication_adherence(
                    citizen_id=citizen["id"],
                    med_name=med_name
                )
                if adherence:
                    actions.append({"type": "adherence_logged", "medication_name": med_name})

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
        suffix = ""  # default: no suffix
        if intent == "appointment_booking" and any(a["type"] == "appointment_created" for a in actions):
            email_sent = any(a["type"] == "email_sent" for a in actions)
            email_failed = any(a["type"] == "email_failed" for a in actions)
            if email_sent:
                suffix = {
                    "ta-IN": " உங்கள் confirmation email வெற்றிகரமாக அனுப்பப்பட்டது.",
                    "kn-IN": " ನಿಮ್ಮ confirmation email ಯಶಸ್ವಿಯಾಗಿ ಕಳುಹಿಸಲಾಗಿದೆ.",
                    "hi-IN": " आपका confirmation email सफलतापूर्वक भेज दिया गया है।",
                    "bho-IN": " राउर confirmation email सफलतापूर्वक भेज दिहल गइल बा।",
                }.get(language_code, " Your confirmation email has been sent successfully.")
            elif email_failed:
                suffix = {
                    "ta-IN": " Email அனுப்ப முடியவில்லை, ஆனால் appointment பதிவு செய்யப்பட்டது.",
                    "kn-IN": " Email ಕಳುಹಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ, ಆದರೆ appointment ನೋಂದಾಯಿಸಲಾಗಿದೆ.",
                    "hi-IN": " Email नहीं भेजा जा सका, लेकिन appointment दर्ज हो गई है।",
                    "bho-IN": " Email ना भेजल जा सकल, बाकिर राउर appointment दर्ज हो गइल बा।",
                }.get(language_code, " Email could not be sent, but your appointment has been booked.")
            else:
                suffix = {
                    "ta-IN": " உங்கள் கோரிக்கை அருகிலுள்ள health worker-க்கு அனுப்பப்பட்டது.",
                    "kn-IN": " ನಿಮ್ಮ ವಿನಂತಿ ಸಮೀಪದ health worker ಗೆ ಕಳುಹಿಸಲಾಗಿದೆ.",
                    "hi-IN": " आपका अनुरोध नजदीकी health worker को भेज दिया गया।",
                    "bho-IN": " राउर अनुरोध नजदीकी health worker के भेज दिहल गइल बा।",
                }.get(language_code, " Your request has been sent to the nearest health worker.")
        if intent == "register_citizen" and any(a["type"] == "citizen_registered" for a in actions):
            suffix = {
                "ta-IN": " உங்கள் விவரங்கள் வெற்றிகரமாக பதிவு செய்யப்பட்டன.",
                "kn-IN": " ನಿಮ್ಮ ವಿವರಗಳನ್ನು ಯಶಸ್ವಿಯಾಗಿ ನೋಂದಾಯಿಸಲಾಗಿದೆ.",
                "hi-IN": " आपके विवरण सफलतापूर्वक पंजीकृत कर लिए गए हैं।",
                "bho-IN": " राउर विवरण सफलतापूर्वक पंजीकृत कर लिहल गइल बा।",
            }.get(language_code, " Your details have been registered successfully.")
        return response + suffix

    _INDIAN_LANGS = {"te", "ml", "gu", "mr", "bn", "pa", "or", "as", "ur"}


    def _normalise_language(self, language_code: str) -> str:
        code = language_code.lower().replace("_", "-")
        if code.startswith("ta"):
            return "ta-IN"
        if code.startswith("kn"):
            return "kn-IN"
        if code.startswith("hi"):
            return "hi-IN"
        if code.startswith("en"):
            return "en-IN"
        if code.startswith("bho"):
            return "bho-IN"
        prefix = code.split("-")[0]
        if prefix in self._INDIAN_LANGS:
            return f"{prefix}-IN"
        return "en-IN"

    # ──────────────────────────────────────────────────────────
    # Session summary (called by frontend on end)
    # ──────────────────────────────────────────────────────────

    async def get_session_summary(self, session_id: str) -> dict[str, Any]:
        meta = await session_store.get_meta(session_id)
        history = await session_store.get_history(session_id)
        return {
            "session_id": session_id,
            "citizen": meta.get("citizen"),
            "verification_state": meta.get("verification_state", "pending"),
            "language_code": meta.get("language_code"),
            "turns": meta.get("turns", 0),
            "call_summary": meta.get("call_summary"),
            "started_at": meta.get("started_at"),
            "history_length": len(history),
        }
