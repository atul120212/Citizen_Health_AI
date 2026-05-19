"""
Analytics router — interaction statistics dashboard data.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import db
from ..auth import verify_admin

router = APIRouter(prefix="/api/analytics", tags=["analytics"], dependencies=[Depends(verify_admin)])


@router.get("/summary")
async def analytics_summary():
    """Return aggregate interaction stats for the dashboard."""
    if not db.is_configured():
        return _demo_analytics()

    total = await db.fetch_one("SELECT COUNT(*) AS cnt FROM health_interactions")
    by_intent = await db.fetch_all(
        "SELECT intent_detected AS intent, COUNT(*) AS count FROM health_interactions GROUP BY intent_detected ORDER BY count DESC"
    )
    by_lang = await db.fetch_all(
        """
        SELECT c.preferred_language AS language, COUNT(hi.id) AS count
        FROM health_interactions hi
        LEFT JOIN citizens c ON c.id = hi.citizen_id
        GROUP BY c.preferred_language
        ORDER BY count DESC
        """
    )
    emergency_count = await db.fetch_one(
        "SELECT COUNT(*) AS cnt FROM health_interactions WHERE intent_detected = 'emergency'"
    )
    followup_needed = await db.fetch_one(
        "SELECT COUNT(*) AS cnt FROM health_interactions WHERE status = 'needs_worker_followup'"
    )
    recent = await db.fetch_all(
        """
        SELECT hi.id, hi.intent_detected, hi.transcript_text, hi.created_at, c.full_name
        FROM health_interactions hi
        LEFT JOIN citizens c ON c.id = hi.citizen_id
        ORDER BY hi.created_at DESC
        LIMIT 10
        """
    )
    return {
        "total_interactions": total["cnt"] if total else 0,
        "emergency_count": emergency_count["cnt"] if emergency_count else 0,
        "followup_needed": followup_needed["cnt"] if followup_needed else 0,
        "by_intent": by_intent or [],
        "by_language": by_lang or [],
        "recent_interactions": recent or [],
    }


def _demo_analytics():
    """Return realistic demo data when DB is not configured."""
    return {
        "total_interactions": 142,
        "emergency_count": 8,
        "followup_needed": 23,
        "by_intent": [
            {"intent": "appointment_booking", "count": 54},
            {"intent": "hospital_navigation", "count": 38},
            {"intent": "eligibility_check", "count": 21},
            {"intent": "maternal_health_reminder", "count": 17},
            {"intent": "nhm_programme_query", "count": 4},
            {"intent": "emergency", "count": 8},
        ],
        "by_language": [
            {"language": "ta", "count": 62},
            {"language": "hi", "count": 45},
            {"language": "en", "count": 23},
            {"language": "kn", "count": 12},
        ],
        "recent_interactions": [],
        "demo": True,
    }
