"""
LiveKit realtime agent — routes every citizen turn through the FastAPI backend
(Sarvam LLM + session state) for accurate intents and multilingual replies.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    RunContext,
    TurnHandlingOptions,
    function_tool,
    inference,
    room_io,
)
from livekit.plugins import silero, sarvam
from livekit.plugins.turn_detector.multilingual import MultilingualModel

# Load backend .env then worker-local overrides
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), ".env.local"))

BACKEND_URL = os.getenv("API_BASE_URL", os.getenv("BACKEND_URL", "http://localhost:8000")).rstrip("/")
AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "citizen-health-ai")


def _parse_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


async def _collect_session_meta(ctx: agents.JobContext, timeout_s: float = 12.0) -> dict[str, Any]:
    """Merge dispatch metadata with the joining participant's token metadata."""
    meta: dict[str, Any] = {}
    job = getattr(ctx, "job", None)
    if job is not None:
        meta.update(_parse_metadata(getattr(job, "metadata", None)))

    await ctx.connect()

    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        for participant in ctx.room.remote_participants.values():
            meta.update(_parse_metadata(participant.metadata))
            if meta.get("session_id"):
                return meta
        await asyncio.sleep(0.2)

    for participant in ctx.room.remote_participants.values():
        meta.update(_parse_metadata(participant.metadata))
    return meta


class CitizenHealthAgent(Agent):
    def __init__(
        self,
        *,
        session_id: str | None = None,
        phone_number: str | None = None,
        language_code: str = "en-IN",
    ) -> None:
        self.session_id = session_id
        self.phone_number = phone_number
        self.language_code = language_code
        lang_hint = (
            "Tamil" if language_code.startswith("ta")
            else "Kannada" if language_code.startswith("kn")
            else "Hindi" if language_code.startswith("hi")
            else "English"
        )
        super().__init__(
            instructions=(
                f"You are Aarogya, Citizen Health AI for {lang_hint}-speaking citizens. "
                "For every user request you MUST call citizen_health_turn exactly once. "
                "Speak ONLY the tool's response_text verbatim — do not add or change medical advice. "
                "Keep replies short and voice-friendly."
            )
        )

    @function_tool()
    async def citizen_health_turn(
        self,
        context: RunContext,
        question: str,
        phone_number: str | None = None,
        language_code: str | None = None,
    ) -> str:
        """Route speech through the Module 1 FastAPI backend (Sarvam + session state).

        Args:
            question: The user's latest spoken request (full sentence).
            phone_number: Optional 10-digit mobile if the user gave it.
            language_code: BCP-47 code such as en-IN, ta-IN, hi-IN, kn-IN.
        """
        payload = {
            "text": question.strip(),
            "phone_number": phone_number or self.phone_number,
            "language_code": language_code or self.language_code,
            "session_id": self.session_id,
        }

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(f"{BACKEND_URL}/api/voice/text-turn", json=payload)
            response.raise_for_status()
            data = response.json()

        # Return plain text so the agent speaks the backend reply exactly
        return data.get("response_text") or "I'm sorry, I couldn't process that. Please try again."


server = AgentServer()


@server.rtc_session(agent_name=AGENT_NAME)
async def citizen_health_ai(ctx: agents.JobContext):
    meta = await _collect_session_meta(ctx)

    session_id = meta.get("session_id")
    phone_number = meta.get("phone_number")
    language_code = meta.get("language_code") or "en-IN"

    stt_lang = "hi" if language_code.startswith("hi") or language_code.startswith("bho") else "ta" if language_code.startswith("ta") else "kn" if language_code.startswith("kn") else "en"

    session = AgentSession(
        stt=sarvam.STT(language=language_code, model="saaras:v3"),
        llm=sarvam.LLM(model="sarvam-30b"),
        tts=sarvam.TTS(target_language_code=language_code, speaker="shubh", model="bulbul:v3"),
        vad=silero.VAD.load(),
        turn_handling=TurnHandlingOptions(turn_detection=MultilingualModel()),
    )

    agent = CitizenHealthAgent(
        session_id=session_id,
        phone_number=phone_number,
        language_code=language_code,
    )

    await session.start(
        room=ctx.room,
        agent=agent,
        room_options=room_io.RoomOptions(),
    )

    # Use backend session intro when available; otherwise a short local greeting
    if session_id:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(f"{BACKEND_URL}/api/session/{session_id}/summary")
                if r.status_code == 200:
                    history_len = r.json().get("history_length", 0)
                    if history_len and history_len > 0:
                        await session.generate_reply(
                            instructions="Greet the user briefly and ask how you can help with their health request today."
                        )
                        return
        except httpx.HTTPError:
            pass

    greeting = {
        "ta-IN": "வணக்கம்! நான் Aarogya. உங்கள் mobile number அல்லது ABHA ID சொல்லுங்கள்.",
        "kn-IN": "ನಮಸ್ಕಾರ! ನಾನು Aarogya. ನಿಮ್ಮ mobile number ಅಥವಾ ABHA ID ಹೇಳಿ.",
        "hi-IN": "नमस्ते! मैं Aarogya हूँ। अपना mobile number या ABHA ID बताएं।",
        "en-IN": "Hello! I'm Aarogya. Please say your mobile number or ABHA ID to verify.",
    }.get(language_code, "Hello! I'm Aarogya. How can I help you today?")

    await session.generate_reply(instructions=f"Say exactly: {greeting}")


if __name__ == "__main__":
    agents.cli.run_app(server)
