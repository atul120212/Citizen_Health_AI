# Citizen Health AI v3.1: The Ultimate Technical & Operational Manifesto

This document is the definitive, single-source-of-truth for the Citizen Health AI platform. It consolidates the Master Atlas, Data Architecture, Intelligence Engine, and Frontend UX into a unified architectural framework.

---

# PART 1: THE MASTER ATLAS (Files & Flow)

## 1.1 The Recursive Repository Map
*   **`.env`**: Centralized secrets (Sarvam AI, LiveKit, Supabase).
*   **`backend/app/`**: The FastAPI core.
    *   `main.py`: Entry point and middleware.
    *   `routers/`: Domain-specific gateways (`voice`, `health_worker`, `surveillance`, `livekit`).
    *   `services/`: The business logic (`conversation`, `outreach`, `rag`, `triage`).
    *   `prompts/`: Persona definitions for Citizens and Workers.
*   **`frontend/src/`**: The Next.js 15 UI.
    *   `app/`: Routing for the Orb, Dashboard, and Map.
    *   `components/`: Reusable high-fidelity visual elements (`VoiceConsole`, `SurveillanceMap`, `WorkerLeaderboard`, `OutreachTaskList`).
*   **`supabase/migrations/`**: The evolution of the database from standard SQL to PostGIS and pgvector.

## 1.2 The End-to-End Master Flow
1.  **Proactive Trigger**: `OutreachService` scans the DB for missed vitals/meds -> Task appears in `OutreachTaskList`.
2.  **Voice Entry**: Citizen says "Namaste" -> Wake-word detection -> LiveKit session starts.
3.  **Intelligent Consultation**: User reports symptoms -> STT (Sarvam) -> Triage (High/Low) -> RAG (Clinical Protocols).
4.  **Action Persistence**: Agent books appointment or logs vitals -> Data saved to PostGIS/pgvector.
5.  **Human Handover**: If high-risk -> Notification to `TeleConsultQueue` -> Doctor joins WebRTC room.
6.  **Closure**: Doctor dictates prescription -> Extracted by AI -> Sent via SMS/ABHA.
7.  **Public Health**: Interaction location is mapped in real-time on the **Surveillance Heatmap**.

---

# PART 2: DATA & API MASTER (Schema & Specs)

## 2.1 The Relational, Geospatial & Vector Schema
*   **Geospatial (PostGIS)**: `locations` and `health_interactions` use `ST_Point` for district-level symptom clustering.
*   **Clinical Vector (pgvector)**: `nhm_documents` stores embedded clinical guidelines for RAG retrieval.
*   **NCD Tracking**: `patient_vitals_log` and `medication_schedules` track longitudinal patient health.
*   **Identity**: `citizens` and `health_workers` link all interactions to verified profiles and ABHA IDs.

## 2.2 Core API Reference
*   **`POST /api/voice/turn`**: The heart of the voice interaction.
*   **`GET /api/health-worker/outreach-tasks`**: Fetches proactive follow-up tasks.
*   **`GET /api/health-worker/live-requests`**: Monitors calls needing doctor intervention.
*   **`GET /api/surveillance/hotspots`**: Returns geospatial cluster data for the heatmap.

---

# PART 3: INTELLIGENCE & PROMPTS (Brain & Personas)

## 3.1 The Intelligent Personas
*   **Aarogya (Citizen Assistant)**: Village-focused, empathetic, and proactive. Leads with check-ins for chronic care patients.
*   **Sahayak (Worker Assistant)**: Data-accurate, clinical, and efficient. Specialized in protocol lookup and structured data extraction.

## 3.2 Conversational State Machine
The AI transitions through a Directed Acyclic Graph (DAG):
`WAKE_WORD` -> `IDENTITY_VERIFICATION` -> `PROACTIVE_CHECKIN` -> `HEALTH_TRIAGE` -> `ACTION_RESOLUTION` -> `SUMMARY`.

## 3.3 Clinical Triage Hierarchy
*   **Critical**: Immediate hospital referral (Chest pain, unconsciousness).
*   **Urgent**: 24h PHC referral (High fever, severe diarrhea).
*   **Community**: Manage at home via ASHA (Mild symptoms, protocol guidance).

---

# PART 4: FRONTEND & UX MASTER (Visuals & Resilience)

## 4.1 The "Rich Aesthetics" Design System
*   **The Health Orb**: A real-time reactive SVG component that pulses and glows based on the user's voice frequency and the AI's internal state.
*   **Surveillance Map**: A high-performance HTML5 Canvas renderer capable of displaying thousands of outbreak clusters without external dependencies.
*   **Worker Dashboard**: A glassmorphic clinical workspace designed for fast data entry and proactive task management.

## 4.2 The "Micro-Voice" Adaptive Protocol
Designed for rural connectivity (2G/3G):
*   **Latency Monitoring**: Real-time RTT checks to choose between LiveKit (WebRTC) and REST.
*   **Adaptive Buffering**: 1.5s silence buffer in low-bandwidth mode to ensure cohesive audio uploads.
*   **Error Resilience**: Local caching and retry logic for high-jitter environments.

---

# CONCLUSION: THE V3.1 VISION
Citizen Health AI v3.1 is not just a chatbot; it is a **Proactive Public Health Infrastructure**. It bridges the gap between a citizen's home in a remote village and the district's command center, ensuring that no symptom goes unmapped and no patient is forgotten.

*Manifesto Version 1.0 | Created for Citizen Health AI Platform*
