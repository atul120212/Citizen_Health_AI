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
from livekit.plugins import silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

load_dotenv("../.env")
load_dotenv(".env.local")

BACKEND_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "citizen-health-ai")


class CitizenHealthAgent(Agent):
    def __init__(self, phone_number: str | None = None, language_code: str = "ta-IN") -> None:
        self.phone_number = phone_number
        self.language_code = language_code
        lang_hint = "Tamil" if language_code.startswith("ta") else "Kannada" if language_code.startswith("kn") else "English"
        super().__init__(
            instructions=(
                f"You are Citizen Health AI. Help {lang_hint}-speaking citizens with hospital navigation, "
                "Ayushman Bharat or CMCHIS eligibility pre-checks, appointment booking, maternal health "
                "reminders, and NHM programme questions. Keep responses short and voice-friendly. "
                "For all citizen health questions, call the citizen_health_turn tool and speak its result."
            )
        )

    @function_tool()
    async def citizen_health_turn(
        self,
        context: RunContext,
        question: str,
        phone_number: str | None = None,
        language_code: str | None = None,
    ) -> dict[str, Any]:
        """Route a citizen health question through the Module 1 FastAPI backend.

        Args:
            question: The user's latest transcribed request.
            phone_number: Optional citizen phone number if the user provides it.
            language_code: Optional BCP-47 language code such as ta-IN or kn-IN.
        """
        resolved_phone = phone_number or self.phone_number
        resolved_lang = language_code or self.language_code

        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                f"{BACKEND_URL}/api/text/turn",
                json={
                    "text": question,
                    "phone_number": resolved_phone,
                    "language_code": resolved_lang,
                },
            )
            response.raise_for_status()
            payload = response.json()
            return {
                "intent": payload["intent"],
                "response_text": payload["response_text"],
                "actions": payload.get("actions", []),
            }


server = AgentServer()


@server.rtc_session(agent_name=AGENT_NAME)
async def citizen_health_ai(ctx: agents.JobContext):
    # Extract citizen metadata from the first remote participant's token metadata
    phone_number: str | None = None
    language_code: str = "ta-IN"

    await ctx.connect()
    for participant in ctx.room.remote_participants.values():
        raw_meta = participant.metadata
        if raw_meta:
            try:
                meta = json.loads(raw_meta)
                phone_number = meta.get("phone_number") or phone_number
                language_code = meta.get("language_code") or language_code
            except (json.JSONDecodeError, AttributeError):
                pass
        break

    stt_lang = "ta" if language_code.startswith("ta") else "kn" if language_code.startswith("kn") else "en"

    session = AgentSession(
        stt=inference.STT(
            model=os.getenv("LIVEKIT_STT_MODEL", "deepgram/nova-3"),
            language=stt_lang,
        ),
        llm=inference.LLM(model=os.getenv("LIVEKIT_LLM_MODEL", "openai/gpt-4o-mini")),
        tts=inference.TTS(model=os.getenv("LIVEKIT_TTS_MODEL", "cartesia/sonic-2")),
        vad=silero.VAD.load(),
        turn_handling=TurnHandlingOptions(turn_detection=MultilingualModel()),
    )

    await session.start(
        room=ctx.room,
        agent=CitizenHealthAgent(phone_number=phone_number, language_code=language_code),
        room_options=room_io.RoomOptions(),
    )

    greeting_lang = "ta-IN" if language_code.startswith("ta") else "kn-IN" if language_code.startswith("kn") else "en-IN"
    if greeting_lang == "ta-IN":
        greeting = "வணக்கம்! நான் சிட்டிசன் ஹெல்த் AI. உங்களுக்கு என்ன உதவி தேவை?"
    elif greeting_lang == "kn-IN":
        greeting = "ನಮಸ್ಕಾರ! ನಾನು ಸಿಟಿಜನ್ ಹೆಲ್ತ್ AI. ನಿಮಗೆ ಏನು ಸಹಾಯ ಬೇಕು?"
    else:
        greeting = "Hello! I am Citizen Health AI. How can I help you today?"

    await session.generate_reply(instructions=greeting)


if __name__ == "__main__":
    agents.cli.run_app(server)
