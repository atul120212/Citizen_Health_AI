from fastapi import APIRouter

from .. import db
from ..services.repository import get_programmes

router = APIRouter(prefix="/api/programmes", tags=["programmes"])


@router.get("")
async def list_programmes():
    if not db.is_configured():
        return {
            "db_configured": False,
            "programmes": [
                {
                    "programme_name": "NHM",
                    "language_code": "en-IN",
                    "question": "What can I ask?",
                    "answer": "Ask about PHC services, maternal health, immunisation, and appointment help.",
                }
            ],
        }
    return {"db_configured": True, "programmes": await get_programmes()}
