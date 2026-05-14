# Citizen Health AI — Module 1

A multilingual AI-powered voice assistant for Indian public healthcare. Citizens can speak naturally in **English, Tamil, Kannada, Hindi, or Hinglish** to book doctor appointments, check Ayushman Bharat / CMCHIS eligibility, navigate PHC facilities, and receive maternal health reminders — all via a Gemini Live-style voice interface backed by Sarvam AI and LiveKit.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Environment Variables](#environment-variables)
  - [Backend Setup](#backend-setup)
  - [Frontend Setup](#frontend-setup)
  - [LiveKit Worker Setup](#livekit-worker-setup)
- [API Reference](#api-reference)
- [Appointment Booking Flow](#appointment-booking-flow)
- [Language Support](#language-support)
- [Email Notifications](#email-notifications)
- [Database Schema](#database-schema)
- [Running Tests](#running-tests)
- [Configuration Reference](#configuration-reference)
- [Demo Mode](#demo-mode)

---

## Features

| Capability | Description |
|---|---|
| **Voice Sessions** | Tap to start — agent introduces itself, then listens hands-free via VAD |
| **Appointment Booking** | Conversational slot-filling: reason, date/time (resolves "tomorrow"), name, email |
| **Confirmation Email** | Multilingual appointment confirmation email sent after user confirms |
| **Eligibility Check** | Ayushman Bharat & CMCHIS pre-check via ABHA ID or phone number |
| **Hospital Navigation** | PHC counter/floor directions for registration, lab, pharmacy, maternal health |
| **Maternal Health Reminders** | ANC visit, supplement, vaccination, and delivery follow-up reminders |
| **NHM Programme Queries** | Answers on National Health Mission programmes and PHC services |
| **Multilingual** | English, Tamil, Kannada, Hindi, Hinglish — auto-detected from speech |
| **Context-aware** | Full conversation history threaded into every LLM call |
| **LiveKit Realtime** | WebRTC mic streaming via LiveKit with VAD auto-turn detection |
| **Gemini Live UI** | Full-screen dark immersive interface with animated voice orb |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        BROWSER (Next.js 15)                      │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  VoiceConsole (React)                                       │  │
│  │  • Gemini Live–style dark UI with animated orb             │  │
│  │  • VAD via AudioContext AnalyserNode (RMS threshold)       │  │
│  │  • MediaRecorder → WebM/Opus chunks → /api/voice/turn      │  │
│  │  • LiveKit SDK → WebRTC mic track to LiveKit Cloud         │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────┬──────────────────────────┬───────────────────┘
                   │ HTTP / REST               │ WebRTC
                   ▼                           ▼
┌──────────────────────────────┐   ┌──────────────────────────────┐
│    FastAPI Backend (Python)  │   │   LiveKit Cloud / Room       │
│                              │   │                              │
│  POST /api/session/start     │   │  ← mic audio track           │
│  POST /api/voice/turn        │◄──┤                              │
│  POST /api/text/turn         │   │  LiveKit Worker (Python)     │
│  POST /api/citizens          │   │  • Deepgram STT              │
│  GET  /api/appointments      │   │  • GPT-4o-mini LLM           │
│  GET  /health                │   │  • Cartesia TTS              │
│                              │   │  • calls /api/text/turn      │
│  ┌──────────────────────┐    │   └──────────────────────────────┘
│  │  ConversationService │    │
│  │  • In-memory sessions│    │
│  │  • 30-min TTL        │    │
│  └──────────┬───────────┘    │
│             │                │
│  ┌──────────▼───────────┐    │
│  │    SarvamService     │    │
│  │  • STT: saaras:v3   │    │
│  │  • LLM: sarvam-30b  │    │
│  │  • TTS: bulbul:v3   │    │
│  └──────────────────────┘    │
│                              │
│  ┌──────────────────────┐    │
│  │  Supabase (Postgres) │    │
│  │  psycopg3 async pool │    │
│  └──────────────────────┘    │
│                              │
│  ┌──────────────────────┐    │
│  │  Email Service       │    │
│  │  smtplib (async)     │    │
│  └──────────────────────┘    │
└──────────────────────────────┘
```

---

## Tech Stack

### Backend
| Layer | Technology |
|---|---|
| API framework | FastAPI 0.115 + Uvicorn |
| AI — Speech-to-Text | Sarvam AI `saaras:v3` |
| AI — LLM | Sarvam AI `sarvam-30b` (reasoning model, max_tokens 2048) |
| AI — Text-to-Speech | Sarvam AI `bulbul:v3` (Shubh speaker) |
| Database | Supabase (PostgreSQL) via psycopg3 async pool |
| Email | Python stdlib `smtplib` via `asyncio.to_thread` |
| Validation | Pydantic v2 |

### Frontend
| Layer | Technology |
|---|---|
| Framework | Next.js 15 App Router (TypeScript) |
| Realtime | LiveKit Client SDK + Components |
| Icons | Lucide React |
| Styling | Pure CSS (dark theme, CSS custom properties) |

### LiveKit Worker
| Layer | Technology |
|---|---|
| Runtime | LiveKit Agents SDK |
| STT | Deepgram `nova-3` |
| LLM | OpenAI `gpt-4o-mini` |
| TTS | Cartesia `sonic-2` |
| VAD | Silero VAD + Multilingual turn detection |

---

## Project Structure

```
Citizen_Health_AI_Module/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI app, CORS, router wiring
│   │   ├── config.py             # Pydantic Settings (env vars)
│   │   ├── db.py                 # psycopg3 async pool, row normalisation
│   │   ├── schemas.py            # Pydantic request/response models
│   │   ├── prompts/
│   │   │   └── citizen_assistant_system.txt   # System prompt (multilingual)
│   │   ├── routers/
│   │   │   ├── voice.py          # /api/session/start, /voice/turn, /text/turn
│   │   │   ├── citizens.py       # /api/citizens CRUD
│   │   │   ├── appointments.py   # /api/appointments
│   │   │   ├── programmes.py     # /api/programmes
│   │   │   └── livekit.py        # /api/livekit/token
│   │   └── services/
│   │       ├── conversation.py   # Session store, turn orchestration, slot filling
│   │       ├── sarvam.py         # STT / LLM / TTS calls + fallback logic
│   │       ├── repository.py     # DB queries (citizens, appointments, reminders)
│   │       └── email_service.py  # Async SMTP confirmation emails
│   ├── tests/
│   │   └── test_api.py           # 46 async unit tests (demo-mode, no DB/API keys needed)
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx          # Root page
│   │   │   ├── layout.tsx        # Root layout
│   │   │   └── globals.css       # Full dark theme, Gemini Live UI styles
│   │   ├── components/
│   │   │   └── VoiceConsole.tsx  # Main UI component (orb, VAD, chat, settings)
│   │   └── lib/
│   │       └── api.ts            # Typed API client functions
│   ├── next.config.mjs
│   └── package.json
│
├── livekit_worker/
│   └── agent.py                  # LiveKit agent (STT + LLM + TTS + tool call)
│
├── .env.example                  # All required environment variables
└── README.md
```

---

## Getting Started

### Prerequisites

- **Python 3.12+**
- **Node.js 20+**
- **Sarvam AI API key** — [console.sarvam.ai](https://console.sarvam.ai)
- **LiveKit Cloud account** — [livekit.io](https://livekit.io) (free tier works)
- **Supabase project** — [supabase.com](https://supabase.com) (optional — runs in demo mode without it)
- **Gmail App Password** (optional) — for appointment confirmation emails

---

### Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

```env
# App
APP_NAME="Citizen Health AI"
ENVIRONMENT="local"
API_BASE_URL="http://localhost:8000"
FRONTEND_ORIGIN="http://localhost:3001"

# Database (Supabase — optional, runs in demo mode without it)
DATABASE_URL="postgresql://postgres.<ref>:<password>@<host>:6543/postgres"

# Sarvam AI (required for real STT / LLM / TTS)
SARVAM_API_KEY="sk_..."
SARVAM_BASE_URL="https://api.sarvam.ai"
SARVAM_STT_MODEL="saaras:v3"
SARVAM_CHAT_MODEL="sarvam-30b"
SARVAM_TTS_MODEL="bulbul:v3"
SARVAM_TTS_SPEAKER="shubh"

# LiveKit (required for realtime WebRTC)
LIVEKIT_URL="wss://<your-project>.livekit.cloud"
LIVEKIT_API_KEY="API..."
LIVEKIT_API_SECRET="..."
LIVEKIT_AGENT_NAME="citizen-health-ai"

# Email (optional — falls back to console log without credentials)
SMTP_HOST="smtp.gmail.com"
SMTP_PORT=587
SMTP_USER="your-email@gmail.com"
SMTP_PASSWORD="your-16-char-app-password"
SMTP_FROM="Citizen Health AI <your-email@gmail.com>"

# Frontend
NEXT_PUBLIC_API_BASE_URL="http://localhost:8000"
NEXT_PUBLIC_LIVEKIT_URL="wss://<your-project>.livekit.cloud"
```

> **Gmail App Password:** Google Account → Security → 2-Step Verification → App Passwords → generate one for "Mail".

---

### Backend Setup

```bash
cd backend

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start the API server (hot-reload)
uvicorn app.main:app --reload --port 8000
```

API available at `http://localhost:8000` · Interactive docs at `http://localhost:8000/docs`

---

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server
npm run dev
```

Open **`http://localhost:3001`** in your browser.

> **Note:** Microphone access requires a secure context. Use `http://localhost:3001` (localhost is exempt from secure-context rules) or serve over HTTPS. The app shows a warning banner on insecure origins.

---

### LiveKit Worker Setup

The LiveKit worker provides an alternative realtime path using Deepgram + GPT-4o-mini + Cartesia instead of Sarvam.

```bash
cd livekit_worker

# Install dependencies
pip install livekit-agents livekit-plugins-silero python-dotenv httpx

# Connect to your LiveKit Cloud project
python agent.py start
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Service health — reports DB / Sarvam / LiveKit status |
| `POST` | `/api/session/start` | Start a conversation session, returns session ID + intro TTS audio |
| `POST` | `/api/voice/turn` | Submit a voice recording (multipart/form-data) |
| `POST` | `/api/text/turn` | Submit a text message |
| `POST` | `/api/citizens` | Create or update a citizen profile |
| `GET` | `/api/appointments` | List appointments |
| `POST` | `/api/livekit/token` | Generate a LiveKit room join token |

### `POST /api/session/start`

```json
// Request
{ "phone_number": "9000001001", "language_code": "ta-IN" }

// Response
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "intro_text": "வணக்கம்! நான் சிட்டிசன் ஹெல்த் AI...",
  "audio_base64": "<base64-encoded WAV>",
  "audio_mime_type": "audio/wav"
}
```

### `POST /api/text/turn`

```json
// Request
{
  "text": "I want to book an appointment",
  "phone_number": "9000001001",
  "language_code": "en-IN",
  "session_id": "550e8400-..."
}

// Response
{
  "transcript": "I want to book an appointment",
  "language_code": "en-IN",
  "intent": "appointment_booking",
  "response_text": "What health concern should I mention for the visit?",
  "audio_base64": "<base64-encoded WAV>",
  "audio_mime_type": "audio/wav",
  "actions": [],
  "citizen_id": null,
  "interaction_id": null,
  "db_configured": false
}
```

### `POST /api/voice/turn`

```
Content-Type: multipart/form-data

audio        <audio file — WebM/Opus, WAV, MP4>
phone_number 9000001001   (optional)
session_id   550e8400-... (optional)
```

Returns the same shape as `/api/text/turn`.

---

## Appointment Booking Flow

The agent collects all required details conversationally — one question at a time:

```
Agent : "What health issue should I mention for the appointment?"
User  : "I have fever and body aches"

Agent : "What date and time would you prefer?"
User  : "Tomorrow at 10 AM"
          ↳ resolved to next calendar date at 10:00

Agent : "What is your full name?"
          ↳ skipped if already present in citizen profile

User  : "Meena Ravi"

Agent : "What's your email address for the confirmation mail?"
User  : "meena@gmail.com"

Agent : "To confirm: appointment for fever on 15 May at 10:00 for Meena Ravi.
         Shall I book it?"
User  : "Yes"   (or हाँ / ஆமாம் / ಹೌದು)

Agent : "Done! A confirmation email has been sent to meena@gmail.com."
          ↳ appointment written to DB
          ↳ confirmation email dispatched
```

**Relative date expressions the agent understands:**

| User says | Resolved to |
|---|---|
| "tomorrow" | today + 1 day |
| "day after tomorrow" | today + 2 days |
| "next Monday" | the coming Monday |
| "this Friday at 3 PM" | coming Friday at 15:00 |
| "morning" | 09:00 |
| "afternoon" | 14:00 |
| "evening" | 17:00 |

---

## Language Support

| Language | BCP-47 | Voice Input | LLM Response | TTS Audio | Auto-detect |
|---|---|:---:|:---:|:---:|:---:|
| Tamil | `ta-IN` | ✅ | ✅ | ✅ | ✅ |
| Kannada | `kn-IN` | ✅ | ✅ | ✅ | ✅ |
| Hindi | `hi-IN` | ✅ | ✅ | ✅ | ✅ |
| Hinglish | `hi-IN` | ✅ | ✅ | ✅ | ✅ |
| English | `en-IN` | ✅ | ✅ | ✅ | ✅ |

**Auto-detection:** Sarvam `saaras:v3` STT returns the detected language code from the audio. That code is forwarded to the LLM, which responds in the same language. For Hinglish, the LLM mirrors the user's Hindi-English mix. For a completely unknown language (e.g., French), the system defaults to English.

---

## Email Notifications

Appointment confirmation emails are sent in the citizen's language automatically when a booking is confirmed.

**Demo mode** (no SMTP credentials set): The full email body is printed to the backend log so you can verify content locally without a mail server.

**Production mode**: Set `SMTP_USER` and `SMTP_PASSWORD` in `.env`. Tested with:
- Gmail (requires a 16-character App Password, not your regular password)
- Any standard STARTTLS SMTP server (Office 365, SendGrid SMTP relay, etc.)

**Sample email (English):**

```
Subject: Your Appointment Confirmation — Citizen Health AI

Hello Meena Ravi,

Your appointment has been successfully booked.

  Reason : Fever and body aches
  Date   : 2026-05-15
  Time   : 10:00
  PHC    : T Nagar Urban Primary Health Centre

To make any changes, please contact your PHC.

Thank you,
Citizen Health AI
```

Emails are also sent in Tamil, Kannada, and Hindi matching the citizen's session language.

---

## Database Schema

The app runs in **demo mode without any database** — keyword-based fallback responses, in-memory sessions, no persistence.

When `DATABASE_URL` is configured (Supabase PostgreSQL), the following tables are used:

| Table | Purpose |
|---|---|
| `citizens` | Phone number, ABHA ID, name, preferred language, location FK |
| `locations` | District, PHC name, village/taluka |
| `health_workers` | ASHA / PHC Nurse records linked to locations |
| `health_interactions` | Every voice/text turn with intent, transcript, and status |
| `appointments` | Booked appointments with date, reason, and assigned worker |
| `maternal_reminders` | ANC / vaccine / supplement / delivery reminder records |
| `nhm_programme_faqs` | Multilingual Q&A content for NHM programmes |
| `hospital_departments` | PHC department, counter, and floor information |

> Use the Supabase **transaction pooler** on port **6543** (not the direct connection on 5432). The psycopg3 pool is configured with `prepare_threshold=None` to be compatible with the pooler.

---

## Running Tests

All 46 tests run in **demo mode** — no API keys, database, or network access required.

```bash
cd backend
source .venv/bin/activate
python -m pytest tests/ -v
```

| Suite | Tests | Coverage |
|---|---|---|
| `HealthTests` | 2 | `/health` endpoint shape and demo flags |
| `EnglishIntentTests` | 16 | All intents in English, normalisation, audio/DB flags |
| `TamilIntentTests` | 5 | Intent detection and language normalisation in Tamil |
| `KannadaIntentTests` | 5 | Intent detection and language normalisation in Kannada |
| `LanguageNormalisationTests` | 4 | BCP-47 code normalisation edge cases |
| `VoiceTurnTests` | 4 | Voice upload endpoint with synthetic audio blobs |
| `LiveKitTokenTests` | 2 | Token endpoint error handling without credentials |
| `CitizenUpsertTests` | 4 | Citizen profile upsert logic |
| `ResponseQualityTests` | 4 | Response content assertions per intent |
| **Total** | **46** | |

---

## Configuration Reference

| Variable | Default | Required | Description |
|---|---|---|---|
| `DATABASE_URL` | — | No | Supabase PostgreSQL URL (use port 6543) |
| `SARVAM_API_KEY` | — | For voice | Sarvam AI API key |
| `SARVAM_CHAT_MODEL` | `sarvam-30b` | — | LLM model (reasoning, needs max_tokens ≥ 2048) |
| `SARVAM_STT_MODEL` | `saaras:v3` | — | Speech-to-text model |
| `SARVAM_TTS_MODEL` | `bulbul:v3` | — | Text-to-speech model |
| `SARVAM_TTS_SPEAKER` | `shubh` | — | TTS speaker voice |
| `LIVEKIT_URL` | — | For WebRTC | LiveKit Cloud WSS URL |
| `LIVEKIT_API_KEY` | — | For WebRTC | LiveKit API key |
| `LIVEKIT_API_SECRET` | — | For WebRTC | LiveKit API secret |
| `SMTP_HOST` | `smtp.gmail.com` | No | SMTP server hostname |
| `SMTP_PORT` | `587` | No | SMTP port (STARTTLS) |
| `SMTP_USER` | — | For email | SMTP login / Gmail address |
| `SMTP_PASSWORD` | — | For email | SMTP password or Gmail App Password |
| `SMTP_FROM` | — | For email | Displayed "From" address |
| `FRONTEND_ORIGIN` | `http://localhost:3001` | — | CORS allowed origin |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | — | Backend URL used by the browser |

---

## Demo Mode

The app degrades gracefully when external services are not configured:

| Service missing | Behaviour |
|---|---|
| No `DATABASE_URL` | All intents work via keyword fallback; no data is persisted |
| No `SARVAM_API_KEY` | Keyword-based responses; no TTS audio returned |
| No LiveKit credentials | `/api/livekit/token` returns an error; Sarvam voice sessions still work |
| No SMTP credentials | Confirmation email body is logged to stdout |

This means the **entire application can be run and all 46 tests passed with zero external API keys**.

---

## License

MIT
