# 🚀 Vercel Deployment Guide — Citizen Health AI

## Architecture

```
Frontend (Next.js)  ──►  Backend (FastAPI)  ──►  Supabase + Sarvam AI
  Vercel Project 1          Vercel Project 2
  citizen-health-ui         citizen-health-api
```

---

## Backend — FastAPI on Vercel

### Prerequisites
- Vercel CLI: `npm i -g vercel`
- Python 3.11 runtime (automatically selected by `vercel.json`)

### Deploy Steps

```bash
cd backend

# Login to Vercel
vercel login

# Deploy (first time — creates project)
vercel --prod

# Set environment variables (run each separately)
vercel env add SARVAM_API_KEY
vercel env add DATABASE_URL
vercel env add LIVEKIT_URL
vercel env add LIVEKIT_API_KEY
vercel env add LIVEKIT_API_SECRET
vercel env add SMTP_USER
vercel env add SMTP_PASSWORD
vercel env add ENVIRONMENT production
vercel env add FRONTEND_ORIGIN https://YOUR-FRONTEND.vercel.app

# Re-deploy after env vars
vercel --prod
```

### Environment Variables for Backend

| Variable | Value |
|----------|-------|
| `ENVIRONMENT` | `production` |
| `SARVAM_API_KEY` | Your Sarvam key |
| `DATABASE_URL` | Supabase transaction pooler URL (port 6543) |
| `LIVEKIT_URL` | `wss://your-livekit-cloud.livekit.cloud` |
| `LIVEKIT_API_KEY` | LiveKit API key |
| `LIVEKIT_API_SECRET` | LiveKit API secret |
| `SMTP_USER` | Gmail address |
| `SMTP_PASSWORD` | Gmail app password |
| `FRONTEND_ORIGIN` | `https://your-frontend.vercel.app` |

### vercel.json (already in backend/)
```json
{
  "builds": [{ "src": "api/index.py", "use": "@vercel/python" }],
  "routes": [{ "src": "/(.*)", "dest": "api/index.py" }]
}
```

---

## Frontend — Next.js on Vercel

### Deploy Steps

```bash
cd frontend

# Deploy (first time)
vercel --prod

# Set environment variables
vercel env add NEXT_PUBLIC_API_BASE_URL
# → Enter: https://YOUR-BACKEND.vercel.app

vercel env add NEXT_PUBLIC_LIVEKIT_URL
# → Enter: wss://your-livekit-cloud.livekit.cloud

# Re-deploy
vercel --prod
```

### Environment Variables for Frontend

| Variable | Value |
|----------|-------|
| `NEXT_PUBLIC_API_BASE_URL` | `https://your-backend.vercel.app` |
| `NEXT_PUBLIC_LIVEKIT_URL` | `wss://your-livekit-cloud.livekit.cloud` |

---

## Supabase Setup

### Enable pgvector

In Supabase Dashboard → SQL Editor, run:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Then run the migration:
```sql
-- Copy contents of supabase/migrations/002_rag_nhm_documents.sql
```

Or use Supabase CLI:
```bash
supabase db push
```

---

## URLs After Deployment

| Service | URL |
|---------|-----|
| Frontend | `https://citizen-health-ui.vercel.app` |
| Backend API | `https://citizen-health-api.vercel.app` |
| Health Check | `https://citizen-health-api.vercel.app/health` |
| OpenAPI Docs | `https://citizen-health-api.vercel.app/docs` |
| Analytics | `https://citizen-health-ui.vercel.app/analytics` |
| LLM Probe | `https://citizen-health-ui.vercel.app/debug` |

---

## Local Development

```bash
# Backend
cd backend
.venv/Scripts/activate   # Windows
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm run dev  # http://localhost:3000

# Run tests
cd backend
python -m pytest tests/ -v
```

---

## Features Enabled

| Feature | Endpoint | Description |
|---------|----------|-------------|
| Voice Turn | `POST /api/voice/turn` | STT → LLM+RAG → TTS |
| Text Turn | `POST /api/text/turn` | Text → LLM+MCP → Response |
| Session Start | `POST /api/session/start` | Multilingual intro |
| Triage | `POST /api/triage` | Symptom severity classifier |
| Analytics | `GET /api/analytics/summary` | Interaction statistics |
| LLM Probe | `GET /api/debug/llm-check` | Intelligence validation |
| RAG Search | `POST /api/debug/rag/search` | Knowledge retrieval test |
| RAG Ingest | `POST /api/debug/rag/add` | Add knowledge documents |
