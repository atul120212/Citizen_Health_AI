"""HTTP smoke test for all major API routes.

Usage:
  python scripts/smoke_test.py              # in-process ASGI (default)
  python scripts/smoke_test.py http://127.0.0.1:8000
"""
from __future__ import annotations

import asyncio
import importlib.util
import io
import sys
from pathlib import Path

import httpx

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

MODE = sys.argv[1] if len(sys.argv) > 1 else "asgi"

# ASGI mode uses demo fallbacks (same as pytest) for deterministic checks
if MODE == "asgi":
    import os

    os.environ.setdefault("DATABASE_URL", "")
    os.environ.setdefault("SARVAM_API_KEY", "")
    os.environ.setdefault("LIVEKIT_URL", "")
    os.environ.setdefault("LIVEKIT_API_KEY", "")
    os.environ.setdefault("LIVEKIT_API_SECRET", "")
BASE = "http://test" if MODE == "asgi" else MODE
TIMEOUT = 90.0

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"  [{status}] {name}{suffix}")


async def _prepare_guest_session(c: httpx.AsyncClient, sid: str, *, in_process: bool) -> None:
    if in_process:
        from app.services.conversation import set_meta

        set_meta(sid, {"verification_state": "guest", "language_code": "en-IN"})
        return
    # Live server: complete verification via API (unknown phone -> guest)
    await c.post(
        "/api/voice/text-turn",
        json={"text": "9000000099", "session_id": sid, "language_code": "en-IN"},
    )


async def run_checks(c: httpx.AsyncClient, silent_wav: bytes, *, in_process: bool = False) -> None:
    r = await c.get("/health")
    health = r.json() if r.status_code == 200 else {}
    check("GET /health", r.status_code == 200 and health.get("ok"), str(health.get("version", r.status_code)))
    print(f"       db_configured={health.get('db_configured')}, sarvam_configured={health.get('sarvam_configured')}")

    r = await c.post("/api/session/start", json={"language_code": "en-IN"})
    sid = r.json().get("session_id") if r.status_code == 200 else None
    check("POST /api/session/start", r.status_code == 200 and bool(sid))

    if sid:
        r = await c.post(f"/api/session/{sid}/summary")
        check("POST /api/session/{id}/summary", r.status_code == 200)
        await _prepare_guest_session(c, sid, in_process=in_process)

    r = await c.post(
        "/api/voice/text-turn",
        json={"text": "Book a doctor appointment", "session_id": sid, "language_code": "en-IN"},
    )
    d1 = r.json() if r.status_code == 200 else {}
    ok1 = r.status_code == 200 and d1.get("intent") == "appointment_booking"
    if not ok1 and r.status_code == 200 and d1.get("intent") and d1.get("response_text"):
        ok1 = True  # Sarvam LLM path: accept any valid turn when fully configured
    check("POST /api/voice/text-turn", ok1, d1.get("intent", str(r.status_code)))

    r = await c.post(
        "/api/voice/text-turn",
        json={"text": "Health concern is fever", "session_id": sid, "language_code": "en-IN"},
    )
    d2 = r.json() if r.status_code == 200 else {}
    ok2 = r.status_code == 200 and d2.get("intent") == "appointment_booking"
    if not ok2 and in_process:
        ok2 = False  # strict in demo mode
    elif not ok2 and r.status_code == 200 and d2.get("response_text"):
        ok2 = d2.get("intent") != "nhm_programme_query"  # must not reset context
    check(
        "POST /api/voice/text-turn (follow-up)",
        ok2,
        d2.get("intent", "") if r.status_code == 200 else str(r.status_code),
    )

    r = await c.post(
        "/api/voice/turn",
        data={"session_id": sid or ""},
        files={"audio": ("t.wav", io.BytesIO(silent_wav), "audio/wav")},
    )
    check("POST /api/voice/turn", r.status_code == 200 and "intent" in r.json())

    r = await c.post("/api/triage", json={"symptoms": ["chest pain"], "language_code": "en-IN"})
    check("POST /api/triage", r.status_code == 200 and r.json().get("severity") == "emergency")

    r = await c.get("/api/analytics/summary")
    check("GET /api/analytics/summary", r.status_code == 200 and "total_interactions" in r.json())

    for path in ("/api/surveillance/dashboard", "/api/surveillance/alerts", "/api/surveillance/trends"):
        r = await c.get(path)
        check(f"GET {path}", r.status_code == 200)

    r = await c.post("/api/health-worker/session/start", json={"language_code": "en-IN", "worker_role": "asha"})
    hw_sid = r.json().get("session_id") if r.status_code == 200 else None
    check("POST /api/health-worker/session/start", r.status_code == 200 and bool(hw_sid))

    try:
        r = await c.post(
            "/api/health-worker/turn",
            json={
                "text": "ANC visit for pregnant woman in village",
                "session_id": hw_sid,
                "language_code": "en-IN",
            },
        )
        check("POST /api/health-worker/turn", r.status_code == 200 and bool(r.json().get("response_text")))
    except httpx.HTTPError as e:
        check("POST /api/health-worker/turn", False, str(e))

    r = await c.get("/api/debug/llm-check")
    check("GET /api/debug/llm-check", r.status_code in (200, 503))

    r = await c.post("/api/debug/rag/search", json={"query": "Ayushman Bharat", "language_code": "en-IN"})
    check("POST /api/debug/rag/search", r.status_code == 200 and "chunks" in r.json())

    r = await c.get("/api/citizens/by-phone/9000000001")
    check("GET /api/citizens/by-phone/{phone}", r.status_code in (200, 404))

    r = await c.get("/api/programmes")
    check("GET /api/programmes", r.status_code in (200, 503))

    r = await c.get("/api/livekit/health")
    check("GET /api/livekit/health", r.status_code == 200 and "configured" in r.json())

    r = await c.post(
        "/api/livekit/token",
        json={
            "room_name": "smoke-room",
            "participant_name": "smoke-user",
            "metadata": {"session_id": "smoke-sess", "language_code": "en-IN"},
        },
    )
    ok_lk = r.status_code == 200 and bool(r.json().get("token")) and bool(r.json().get("url"))
    check("POST /api/livekit/token", ok_lk or r.status_code == 503, r.json().get("agent_name", str(r.status_code)))

    r = await c.options(
        "/health",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    check("OPTIONS /health (CORS)", r.status_code in (200, 204))

    try:
        spec = importlib.util.spec_from_file_location("vercel_idx", _BACKEND / "api" / "index.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        check("api/index.py imports app", hasattr(mod, "app") and bool(mod.app.title))
    except Exception as e:
        check("api/index.py imports app", False, str(e))


async def main_async() -> int:
    print(f"\nCitizen Health AI smoke test @ {BASE} ({MODE})\n")
    silent_wav = (
        b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
        b"D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    )

    if MODE == "asgi":
        from httpx import ASGITransport
        from app.main import app

        transport = ASGITransport(app=app)
    else:
        transport = None

    async with httpx.AsyncClient(transport=transport, base_url=BASE, timeout=TIMEOUT) as c:
        await run_checks(c, silent_wav, in_process=(MODE == "asgi"))

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{'=' * 50}")
    print(f"Result: {passed}/{total} checks passed")
    if passed < total:
        print("\nFailed:")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name}: {detail}")
    print()
    return 0 if passed == total else 1


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
