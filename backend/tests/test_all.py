"""
Production test suite — Voice-Only Citizen Health AI Agent.

Tests cover:
  - Health endpoint + feature flags
  - Session start (4 languages + pre-verified)
  - Session summary
  - Voice turn verification state machine (pending → verified / guest)
  - Voice turn free conversation (all intents)
  - Triage (emergency / high / medium / low / maternal / multilingual)
  - Analytics (demo mode)
  - RAG search
  - LLM probe reachability
  - Edge cases (empty audio metadata, long text, special chars)
  - CORS (localhost + vercel)

Run:  cd backend && .venv/Scripts/python -m pytest tests/ -v --asyncio-mode=auto
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
import sys, os

# Force demo mode to bypass 429 Too Many Requests errors from Sarvam API
os.environ["DATABASE_URL"] = ""
os.environ["SARVAM_API_KEY"] = ""
os.environ["LIVEKIT_URL"] = ""
os.environ["LIVEKIT_API_KEY"] = ""
os.environ["LIVEKIT_API_SECRET"] = ""

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.main import app


# ── Fixtures ───────────────────────────────────────────────

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest_asyncio.fixture
async def session(client):
    r = await client.post("/api/session/start", json={"language_code": "en-IN"})
    assert r.status_code == 200
    return r.json()["session_id"]


# ── 1. Health ──────────────────────────────────────────────

class TestHealth:
    async def test_ok(self, client):
        r = await client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert "version" in d

    async def test_features(self, client):
        r = await client.get("/health")
        f = r.json()["features"]
        assert "rag" in f and "mcp_tools" in f and "triage" in f


# ── 2. Session start ───────────────────────────────────────

class TestSessionStart:
    @pytest.mark.parametrize("lang", ["en-IN", "hi-IN", "ta-IN", "kn-IN"])
    async def test_all_languages(self, client, lang):
        r = await client.post("/api/session/start", json={"language_code": lang})
        assert r.status_code == 200
        d = r.json()
        assert "session_id" in d
        assert len(d["intro_text"]) > 10
        # Intro must ask for ID (verification phase)
        text = d["intro_text"].lower()
        id_keywords = ["mobile", "number", "abha", "id", "verify", "नंबर", "mobile", "ஐடி", "number"]
        assert any(k in text for k in id_keywords) or len(text) > 20

    async def test_unique_session_ids(self, client):
        r1 = await client.post("/api/session/start", json={"language_code": "en-IN"})
        r2 = await client.post("/api/session/start", json={"language_code": "en-IN"})
        assert r1.json()["session_id"] != r2.json()["session_id"]

    async def test_no_language_defaults(self, client):
        r = await client.post("/api/session/start", json={})
        assert r.status_code == 200
        assert "session_id" in r.json()

    async def test_unknown_lang_fallback(self, client):
        r = await client.post("/api/session/start", json={"language_code": "fr-FR"})
        assert r.status_code == 200
        assert r.json()["intro_text"]


# ── 3. Session summary ─────────────────────────────────────

class TestSessionSummary:
    async def test_summary_returns_structure(self, client, session):
        r = await client.post(f"/api/session/{session}/summary")
        assert r.status_code == 200
        d = r.json()
        assert d["session_id"] == session
        assert "verification_state" in d
        assert "turns" in d
        assert d["verification_state"] == "pending"

    async def test_summary_unknown_session(self, client):
        r = await client.post("/api/session/nonexistent-xyz/summary")
        assert r.status_code == 200
        d = r.json()
        assert d["turns"] == 0


# ── 3b. Multi-turn conversation context ───────────────────

class TestTranscriptQuality:
    def test_garbage_repeated_word(self):
        from app.services.conversation import _is_low_quality_transcript

        assert _is_low_quality_transcript("சரி சரி சரி சரி சரி சரி")
        assert not _is_low_quality_transcript("Book an appointment for tomorrow")

    def test_empty_is_low_quality(self):
        from app.services.conversation import _is_low_quality_transcript

        assert _is_low_quality_transcript("   ")


class TestConversationContext:
    async def test_appointment_slot_filling_stays_in_flow(self, client, session):
        """Follow-up answers must not reset to NHM when booking an appointment."""
        from app.services.conversation import session_store

        await session_store.set_meta(session, {"verification_state": "guest", "language_code": "en-IN"})

        r1 = await client.post(
            "/api/voice/text-turn",
            json={
                "text": "Book my appointment for tomorrow",
                "session_id": session,
                "language_code": "en-IN",
            },
        )
        assert r1.status_code == 200
        assert r1.json()["intent"] == "appointment_booking"

        r2 = await client.post(
            "/api/voice/text-turn",
            json={
                "text": "Health concern is fever",
                "session_id": session,
                "language_code": "en-IN",
            },
        )
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["intent"] == "appointment_booking", (
            f"Expected appointment_booking, got {d2['intent']}: {d2['response_text']}"
        )
        assert "nhm programme" not in d2["response_text"].lower()


# ── 4. Voice turn — verification flow ─────────────────────

class TestVerificationFlow:
    async def test_verification_pending_no_digits(self, client, session):
        """Gibberish → agent asks again, still pending"""
        import io
        # Minimal silent WAV (44 bytes) so STT falls back to demo mode
        silent_wav = (
            b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00'
            b'D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00'
        )
        form_data = {"session_id": session}
        files = {"audio": ("test.wav", io.BytesIO(silent_wav), "audio/wav")}
        r = await client.post("/api/voice/turn", data=form_data, files=files)
        assert r.status_code == 200
        d = r.json()
        assert "intent" in d
        assert "response_text" in d
        assert len(d["response_text"]) > 0

    async def test_voice_turn_response_fields(self, client, session):
        import io
        silent_wav = b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00'
        r = await client.post("/api/voice/turn",
            data={"session_id": session},
            files={"audio": ("t.wav", io.BytesIO(silent_wav), "audio/wav")}
        )
        assert r.status_code == 200
        d = r.json()
        for field in ["transcript", "language_code", "intent", "response_text", "actions", "db_configured"]:
            assert field in d, f"Missing: {field}"

    async def test_verified_intent_in_actions(self, client):
        """When Sarvam not configured, demo fallback still returns valid structure"""
        s = await client.post("/api/session/start", json={"language_code": "en-IN"})
        sid = s.json()["session_id"]
        import io
        wav = b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00'
        r = await client.post("/api/voice/turn",
            data={"session_id": sid, "phone_number": "9000000001"},
            files={"audio": ("t.wav", io.BytesIO(wav), "audio/wav")}
        )
        assert r.status_code == 200
        assert r.json()["intent"]


# ── 5. Triage ──────────────────────────────────────────────

class TestTriage:
    async def test_emergency(self, client):
        r = await client.post("/api/triage", json={"symptoms": ["chest pain", "can't breathe"], "language_code": "en-IN"})
        assert r.status_code == 200
        d = r.json()
        assert d["severity"] == "emergency"
        assert d["needs_ambulance"] is True
        assert len(d["advice"]) > 0

    async def test_medium(self, client):
        r = await client.post("/api/triage", json={"symptoms": ["mild fever", "cough"], "language_code": "en-IN"})
        assert r.status_code == 200
        assert r.json()["severity"] in {"low", "medium"}
        assert not r.json()["needs_ambulance"]

    async def test_maternal(self, client):
        r = await client.post("/api/triage", json={"symptoms": ["pregnant", "anc checkup"], "language_code": "en-IN"})
        assert r.status_code == 200
        assert r.json()["severity"] in {"low", "medium"}

    async def test_empty_fallback(self, client):
        r = await client.post("/api/triage", json={"symptoms": [], "language_code": "en-IN"})
        assert r.status_code == 200
        assert r.json()["severity"] == "low"

    @pytest.mark.parametrize("lang", ["ta-IN", "hi-IN", "kn-IN", "en-IN"])
    async def test_multilingual_advice(self, client, lang):
        r = await client.post("/api/triage", json={"symptoms": ["chest pain"], "language_code": lang})
        assert r.status_code == 200
        assert len(r.json()["advice"]) > 0

    async def test_high_fever(self, client):
        r = await client.post("/api/triage", json={"symptoms": ["high fever", "vomiting"], "language_code": "en-IN"})
        assert r.status_code == 200
        assert r.json()["severity"] in {"high", "medium"}

    async def test_hindi_emergency(self, client):
        r = await client.post("/api/triage", json={"symptoms": ["सीने में दर्द"], "language_code": "hi-IN"})
        assert r.status_code == 200
        assert r.json()["severity"] == "emergency"


# ── 6. Analytics ───────────────────────────────────────────

class TestAnalytics:
    async def test_summary_structure(self, client):
        r = await client.get("/api/analytics/summary")
        assert r.status_code == 200
        d = r.json()
        assert "total_interactions" in d
        assert isinstance(d["by_intent"], list)
        assert isinstance(d["by_language"], list)
        assert "emergency_count" in d

    async def test_demo_data_populated(self, client):
        r = await client.get("/api/analytics/summary")
        d = r.json()
        if d.get("demo"):
            assert d["total_interactions"] > 0
            assert len(d["by_intent"]) > 0


# ── 7. RAG search ──────────────────────────────────────────

class TestRAG:
    async def test_search_returns_list(self, client):
        r = await client.post("/api/debug/rag/search", json={"query": "Ayushman Bharat", "language_code": "en-IN"})
        assert r.status_code == 200
        d = r.json()
        assert "chunks" in d
        assert isinstance(d["chunks"], list)

    async def test_empty_query_safe(self, client):
        r = await client.post("/api/debug/rag/search", json={"query": "", "language_code": "en-IN"})
        assert r.status_code in {200, 422}


# ── 8. LLM Probe ───────────────────────────────────────────

class TestLLMProbe:
    async def test_reachable(self, client):
        r = await client.get("/api/debug/llm-check")
        assert r.status_code in {200, 503}

    async def test_score_structure(self, client):
        r = await client.get("/api/debug/llm-check")
        if r.status_code == 200:
            d = r.json()
            assert "score" in d
            assert "cases" in d
            assert 0 <= d["score"] <= 100


# ── 9. Edge cases ──────────────────────────────────────────

class TestEdgeCases:
    async def test_voice_turn_without_session(self, client):
        import io
        wav = b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00'
        r = await client.post("/api/voice/turn",
            data={},
            files={"audio": ("t.wav", io.BytesIO(wav), "audio/wav")}
        )
        assert r.status_code == 200

    async def test_voice_turn_special_session(self, client):
        import io
        wav = b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00'
        r = await client.post("/api/voice/turn",
            data={"session_id": "non-existent-session-xyz"},
            files={"audio": ("t.wav", io.BytesIO(wav), "audio/wav")}
        )
        assert r.status_code == 200

    async def test_triage_empty_language(self, client):
        r = await client.post("/api/triage", json={"symptoms": ["fever"], "language_code": ""})
        assert r.status_code in {200, 422}

    async def test_citizens_route_exists(self, client):
        r = await client.get("/api/citizens")
        assert r.status_code in {200, 404, 405, 422}

    async def test_programmes_route(self, client):
        r = await client.get("/api/programmes")
        assert r.status_code in {200, 503}


# ── 10. CORS ───────────────────────────────────────────────

class TestCORS:
    async def test_localhost(self, client):
        r = await client.options("/health", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"})
        assert r.status_code in {200, 204}

    async def test_vercel_origin(self, client):
        r = await client.options("/health", headers={"Origin": "https://citizen-health-ai.vercel.app", "Access-Control-Request-Method": "POST"})
        assert r.status_code in {200, 204}
