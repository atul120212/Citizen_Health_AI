# 🧠 Citizen Health AI — System Mind Map

## Business Problem We're Solving

> **7–8 crore citizens** in Tamil Nadu and Karnataka face fragmented healthcare access.
> PHC staff spend significant time answering **repetitive queries** about schemes, appointments, and navigation.
> There is **zero AI-assisted outreach** for remote/tribal PHC areas.
> Citizens can't speak English and don't know how to navigate the health system.

We solve this with an **AI voice agent** that speaks Tamil, Kannada, Hindi, and English — handling the 5 most common PHC interactions fully autonomously.

---

## The 5 Core Use-Cases (All Production-Required)

| # | Use-Case | Business Value |
|---|----------|---------------|
| 1 | **Hospital Navigation** | Staff no longer answer "where is OPD?" 40× a day |
| 2 | **Ayushman Bharat / CMCHIS Eligibility Check** | Instant pre-check without queue; scheme awareness |
| 3 | **Appointment Booking** | 24×7 booking, reduces no-shows, frees receptionist |
| 4 | **Maternal Health Reminders** | ANC adherence ↑, reduces maternal mortality risk |
| 5 | **NHM Programme Queries** | JSY, RKSK, immunisation FAQs answered instantly |

---

## Why RAG (Retrieval-Augmented Generation)?

### The Problem Without RAG
The base LLM (`sarvam-30b`) knows general Tamil but **does not know**:
- The specific Ayushman Bharat income cutoff (₹72,000/year for CMCHIS)
- The ANC visit schedule per NHM guidelines
- Which departments are on which floor of *your specific* PHC
- JSY eligibility documents required

Without RAG, the LLM would **hallucinate** scheme details or give outdated/wrong information — dangerous in a healthcare context.

### How RAG Works in This System

```
User Voice Query
      │
      ▼
   Sarvam STT → transcript
      │
      ▼
Sarvam /v1/embeddings → 1024-dim vector
      │
      ▼
pgvector cosine similarity search (nhm_documents table)
      │
      ▼
Top-3 matching knowledge chunks
      │
      ▼
Injected into LLM system prompt as [VERIFIED KNOWLEDGE]
      │
      ▼
Sarvam-30b generates response GROUNDED in real PHC data
```

### Where RAG Is Used
- **Every voice/text turn** — before the LLM call, RAG retrieves relevant NHM docs
- **Scheme eligibility queries** — Ayushman, CMCHIS, JSY details fetched from vector store
- **ANC/maternal health questions** — official NHM schedule injected as context
- **Hospital navigation** — PHC-specific department/floor data retrieved per location

### RAG Knowledge Base (nhm_documents)
| Category | Examples |
|----------|---------|
| `scheme` | PM-JAY eligibility, CMCHIS income criteria, JSY documents |
| `faq` | ANC visit schedule, immunisation dates, emergency contacts |
| `navigation` | PHC department map, floor guide, room numbers |
| `phc_service` | Open hours, specialist days, lab services |

---

## Why MCP (Model Context Protocol-style Tool Calling)?

### The Problem Without MCP
The LLM can *talk about* booking an appointment but cannot **actually book it** into the database.
Without structured tool-calling, you need:
- Complex regex parsing of free-text LLM output
- Separate intent classification pipeline
- Multiple brittle if-else chains

### How MCP Works in This System

The LLM outputs a **strict JSON** with an optional `tool_call` key:
```json
{
  "intent": "appointment_booking",
  "response_text": "I'll book that now...",
  "tool_call": {
    "name": "book_appointment",
    "args": {
      "citizen_id": "uuid-xxx",
      "reason": "fever",
      "date": "2026-05-16",
      "time": "10:00"
    }
  }
}
```

The `MCPExecutor` intercepts this, **executes the real DB operation**, and re-runs the LLM with the tool result so it gives a natural confirmation response.

### MCP Tools Available

| Tool | What It Does | When Triggered |
|------|-------------|----------------|
| `book_appointment` | Creates row in `health_appointments` table | User confirms appointment details |
| `check_eligibility` | Queries citizen's ABHA/ayushman_status | "Am I eligible for Ayushman?" |
| `get_hospital_navigation` | Fetches dept/floor from `hospital_departments` | "Where is OPD?" |
| `set_maternal_reminder` | Creates row in `maternal_health_reminders` | "Remind me for ANC" |
| `search_nhm_programmes` | Searches `nhm_programme_faqs` table | "Tell me about JSY" |

### Why Not Just Hardcode Intent → DB?
MCP lets the **LLM decide** which tool to call with which parameters, in natural language, across all supported languages. The same pipeline works for Tamil, Hindi, and Kannada without separate code paths.

---

## Why Triage Service?

### Business Requirement
Citizens with **emergency symptoms** (chest pain, difficulty breathing, heavy bleeding) must be **immediately identified** and told to call 108 — not queued for appointment booking.

### How It Works
```
User says symptoms
      │
      ▼
Keyword matching against red-flag list
(chest pain, can't breathe, stroke, heavy bleeding, seizure...)
      │
      ├── EMERGENCY → "Call 108 immediately" + needs_ambulance: true
      ├── HIGH      → "Go to Emergency OPD today"
      ├── MEDIUM    → "Book appointment within 2 days"
      └── LOW       → "General OPD, book appointment"
```

This runs **before** the full LLM call for known red-flag patterns — zero latency safety check.

---

## Why LLM Intelligence Probe?

### Business Requirement
Before deploying to real citizens, we must verify the LLM:
- Returns **valid JSON** (no markdown, no hallucinated keys)
- Detects **emergency** intent (not classifying "chest pain" as "appointment")
- Replies in **Hindi script** when Hindi is spoken
- Does **not prematurely confirm** appointments without all slots filled

### 6 Probe Cases
| Case | Tests |
|------|-------|
| `json_compliance` | Output is valid JSON with all required keys |
| `hindi_detection` | Hindi input → Hindi script output |
| `emergency_detection` | "Chest pain" → intent = emergency |
| `slot_collection` | Missing date → asks for date, no confirmation |
| `no_premature_confirm` | Does NOT set confirmed=true without all slots |
| `eligibility_intent` | "Ayushman Bharat?" → intent = eligibility_check |

---

## Why Sarvam AI (not OpenAI/Gemini)?

| Requirement | Sarvam | OpenAI/Gemini |
|-------------|--------|---------------|
| Tamil STT | ✅ Native | ❌ Poor accent support |
| Kannada TTS | ✅ Native | ⚠️ Limited |
| Hindi NLP | ✅ sarvam-30b trained on Indic data | ⚠️ English-biased |
| Cost for rural India | ✅ Local pricing | ❌ USD pricing |
| DPDP compliance | ✅ India-hosted | ❌ US servers |

---

## Identity Verification Flow

```
Wake Word Detected (Hello / Namaste / Namaskara / Vanakkam)
      │
      ▼
Session Created → Agent introduces itself as "Aarogya"
      │
      ▼
Agent asks: "Please say your 10-digit mobile number or ABHA ID"
      │
      ▼
User speaks ID → Sarvam STT → LLM extracts digits
      │
      ├── Digits match citizens table?
      │       YES → Personalized greeting with citizen name + PHC
      │             Language auto-set to citizen's preferred language
      │       NO  → Guest mode (still can answer general queries)
      │
      ▼
Free Conversation with RAG + MCP + Triage
      │
      ▼
Session End ("bye" / "thank you" / timeout)
      │
      ▼
Post-call summary card shown to user
```

---

## Data Flow (Single Voice Turn)

```
[Microphone] → WebM audio blob
                    │
                    ▼
         POST /api/voice/turn (FormData)
                    │
                    ▼
         Sarvam STT (/v1/speech:recognize)
                    │
                    ▼
         Transcript + detected language
                    │
          ┌─────────┼──────────────────────┐
          ▼         ▼                      ▼
   Verification  RAG retrieve         Triage check
   state check   (pgvector)           (emergency?)
          │         │                      │
          └─────────┴──────────────────────┘
                    │
                    ▼
         Sarvam-30b LLM
         (System prompt + RAG context + history)
                    │
                    ▼
         JSON response parsed
                    │
          ┌─────────┼──────────┐
          ▼         ▼          ▼
    MCP tool   DB write    Email send
    execute    (psycopg3)  (SMTP)
          │
          ▼
    Tool result → LLM re-run → final response_text
                    │
                    ▼
         Sarvam TTS (/v1/text:synthesize)
                    │
                    ▼
         audio/wav base64
                    │
                    ▼
         Frontend plays audio → Records next turn
```

---

## Tech Stack Summary

| Layer | Technology | Why |
|-------|-----------|-----|
| **STT** | Sarvam `/v1/speech:recognize` | Best-in-class Tamil/Kannada ASR |
| **LLM** | `sarvam-m` / `sarvam-30b` | Indic language reasoning |
| **TTS** | Sarvam `/v1/text:synthesize` | Natural Indian language voices |
| **Embeddings** | Sarvam `text-embedding-007` (1024-dim) | For RAG vector search |
| **Vector DB** | pgvector on Supabase | Managed, no extra infra |
| **App DB** | PostgreSQL / Supabase | Citizens, appointments, interactions |
| **Backend** | FastAPI + asyncio | Async I/O for streaming audio |
| **Frontend** | Next.js 14 (App Router) | SSR + React for real-time UI |
| **Deployment** | Vercel (Backend + Frontend separately) | Serverless, auto-scale |
| **VAD** | Web Audio API (browser-side) | Local, zero-latency silence detection |
| **Wake Word** | Web Speech API | Lightweight, works offline |

---

## Database Schema (Core Tables)

```
locations          → PHC details, coordinates
citizens           → phone, ABHA ID, preferred language, location_id
health_workers     → ASHA workers, nurses
health_appointments → citizen_id, date, time, reason, status
maternal_health_reminders → citizen_id, type, due_date
health_interactions → citizen_id, intent, transcript, interaction_type
nhm_programme_faqs → scheme FAQs by language
hospital_departments → dept, floor, room, services
nhm_documents      → RAG knowledge base (pgvector)
```

---

## Production Safety Features

| Feature | Implementation |
|---------|---------------|
| **Emergency escalation** | Triage service → immediate 108 instruction |
| **No hallucination** | RAG grounds all scheme answers in real documents |
| **No premature confirm** | LLM probe validates slot-filling discipline |
| **Session TTL** | 30-minute session expiry, auto-cleanup |
| **Graceful degradation** | Works without DB (demo mode), without Sarvam (fallback responses) |
| **CORS security** | Vercel regex allowlist + explicit origins |
| **Data privacy** | No audio stored; only transcript + intent logged |
| **DPDP readiness** | India-hosted (Sarvam + Supabase) |
