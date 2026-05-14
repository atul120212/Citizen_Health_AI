from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .config import get_settings
from .routers import appointments, citizens, livekit, programmes, voice


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.init_db()
    yield
    await db.close_db()


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

_cors_origins = [
    settings.frontend_origin,
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    # Allow the VM's LAN IP on common dev ports so browser on same machine works
    "http://172.31.8.102:3000",
    "http://172.31.8.102:3001",
    "http://172.31.8.102:3002",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(_cors_origins)),  # deduplicate, preserve order
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(voice.router)
app.include_router(citizens.router)
app.include_router(appointments.router)
app.include_router(programmes.router)
app.include_router(livekit.router)


@app.get("/health")
async def health():
    return {
        "ok": True,
        "db_configured": db.is_configured(),
        "sarvam_configured": bool(settings.sarvam_api_key),
        "livekit_configured": bool(settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret),
    }
