# Citizen Health AI — System Hardening & Deployment Guide

Following the comprehensive project analysis, the following issues have been resolved to ensure production-grade stability on Vercel.

## ✅ Key Fixes Implemented

1. **Serverless Persistence**: Migrated session state from in-memory dictionaries to a PostgreSQL-backed `SessionStore`. This ensures that voice sessions are not lost when Vercel's serverless functions recycle or cold-start.
2. **Missing Database Tables**: Created Migration `003_system_fixes.sql` which adds the `chat_sessions` table and the missing `health_worker_records` table.
3. **Production Logging**: Replaced file-based logging (which fails on Vercel's read-only filesystem) with standard Python `logging`.
4. **Endpoint Security**: Secured admin endpoints (`/api/analytics`, `/api/surveillance`, `/api/debug`, `/api/health-worker`) with a `verify_admin` API key dependency.
5. **RAG Reliability**: Implemented a keyword-based text search fallback in the RAG service to ensure knowledge retrieval works even if the embedding API is transiently unavailable.
6. **SQL Bug Fixes**: Corrected the department search SQL logic to handle empty queries correctly.
7. **Bhojpuri Support**: Standardized `bho-IN` across schemas, normalization, and LiveKit STT mapping.

## 🚀 Final Steps for Deployment

To complete the setup, please perform the following two steps:

### 1. Apply Database Migration
Execute the SQL content from `supabase/migrations/003_system_fixes.sql` in your Supabase SQL Editor. This will create the necessary tables for sessions and records.

### 2. Update Environment Variables
Add the following variable to your `.env` (and your Vercel Dashboard Environment Variables):

```bash
ADMIN_API_KEY=your_secure_random_key_here
```

Your admin dashboard (Analytics, Surveillance, Debug) will now require this key to be passed in the `x-admin-key` header.

## 🏗️ Architecture Note: LiveKit Consistency
The LiveKit worker in `livekit_worker/agent.py` acts as a **High-Performance Real-time Gateway**. It uses Deepgram and Cartesia for sub-second latency while routing all medical logic through the **Module 1 Backend (Sarvam)**. This "Choice" provides the best user experience by combining lightning-fast response times with consistent clinical intelligence.
