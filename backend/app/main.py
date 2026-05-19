import asyncio
import sys
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Load .env variables into os.environ
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from . import db
from .config import get_settings
from .routers import analytics, appointments, citizens, debug, health_worker, livekit, programmes, surveillance, triage, voice


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.init_db()
    yield
    await db.close_db()


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)

_cors_origins = [
    settings.frontend_origin,
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://172.31.8.102:3000",
    "http://172.31.8.102:3001",
    "http://172.31.8.102:3002",
    # Vercel preview deployments (wildcard handled via allow_origin_regex below)
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(_cors_origins)),  # deduplicate, preserve order
    allow_origin_regex=r"https://.*\.vercel\.app",     # all vercel previews
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(voice.router)
app.include_router(citizens.router)
app.include_router(appointments.router)
app.include_router(programmes.router)
app.include_router(livekit.router)
app.include_router(debug.router)
app.include_router(triage.router)
app.include_router(analytics.router)
app.include_router(health_worker.router)
app.include_router(surveillance.router)


@app.get("/health")
@app.get("/api/health")
@app.head("/api/health")
async def health():
    return {
        "ok": True,
        "version": "0.2.0",
        "db_configured": db.is_configured(),
        "sarvam_configured": bool(settings.sarvam_api_key),
        "livekit_configured": bool(settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret),
        "features": ["rag", "mcp_tools", "triage", "llm_probe", "analytics", "health_worker_ai", "surveillance_ai"],
    }
