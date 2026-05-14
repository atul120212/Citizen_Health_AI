# Citizen Health AI - Module 1

Tamil/Kannada citizen voice assistant for hospital navigation, Ayushman Bharat / CMCHIS eligibility, appointment booking, maternal health reminders, and NHM programme queries.

This repo contains an end-to-end starter:

- `backend/` - FastAPI service with Supabase Postgres, Sarvam STT/LLM/TTS, and LiveKit token endpoints.
- `frontend/` - Next.js app with an IVR-style voice turn UI and a LiveKit room launcher.
- `livekit_worker/` - realtime voice-agent worker scaffold for LiveKit rooms.
- `supabase/` - schema migration and demo seed data.
- `docs/` - architecture and API notes.

## Voice Flow

1. Citizen speaks in Tamil or Kannada.
2. IVR path: browser records audio and calls `POST /api/voice/turn`.
3. Realtime path: frontend joins a LiveKit room, and the worker handles room audio.
4. Backend sends audio to Sarvam Saaras v3 speech-to-text with language auto-detection.
5. Sarvam-30B classifies intent and drafts the response in the citizen's language.
6. Backend performs Supabase reads/writes for eligibility, appointments, reminders, and interaction history.
7. Backend sends the final response to Sarvam Bulbul v3 text-to-speech and returns audio.

## Quick Start

### 1. Configure environment

```bash
cp .env.example .env
```

Set at least:

```bash
DATABASE_URL="postgres://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres"
SARVAM_API_KEY="sk_..."
LIVEKIT_URL="wss://<project>.livekit.cloud"
LIVEKIT_API_KEY="..."
LIVEKIT_API_SECRET="..."
NEXT_PUBLIC_API_BASE_URL="http://localhost:8000"
NEXT_PUBLIC_LIVEKIT_URL="wss://<project>.livekit.cloud"
```

Use Supabase's transaction pooler connection string on port `6543`. The backend disables prepared statements for Psycopg so it works with transaction pooling.

### 2. Apply database schema

Run the migration in Supabase SQL editor or via `psql`:

```bash
psql "$DATABASE_URL" -f supabase/migrations/0001_citizen_health_ai.sql
psql "$DATABASE_URL" -f supabase/seed.sql
```

### 3. Run backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 4. Run frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

### 5. Run LiveKit worker

```bash
cd livekit_worker
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python agent.py
```

The IVR endpoint is ready for demos immediately. The LiveKit worker is intentionally thin and calls the same backend orchestration so the clinical/business logic stays in one place.

## Useful API Endpoints

- `GET /health` - backend health check.
- `POST /api/voice/turn` - audio in, transcript/intent/audio out.
- `POST /api/text/turn` - text-only turn for debugging.
- `GET /api/citizens/by-phone/{phone}` - fetch or inspect citizen profile.
- `POST /api/appointments` - create appointment.
- `GET /api/programmes` - NHM programme FAQ records.
- `POST /api/livekit/token` - participant token for LiveKit rooms.

## Demo Fallbacks

If `SARVAM_API_KEY` is missing, the backend uses deterministic text responses and returns no generated audio. If `DATABASE_URL` is missing, API endpoints still start but database-backed writes are skipped with clear metadata. This keeps the UI easy to demo while external services are being wired.
