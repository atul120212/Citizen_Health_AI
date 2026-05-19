"""
Disease Surveillance AI Router — /api/surveillance/*

Provides:
  GET /api/surveillance/dashboard  — full dashboard for District Health Officer
  GET /api/surveillance/alerts     — active outbreak alerts
  GET /api/surveillance/trends     — weekly disease trend data
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends

from .. import db
from ..auth import verify_admin

router = APIRouter(prefix="/api/surveillance", tags=["surveillance"], dependencies=[Depends(verify_admin)])

# ── Disease keywords for intent-based surveillance ────────────────────────────
DISEASE_KEYWORDS: dict[str, list[str]] = {
    "Fever / ILI":      ["fever", "ஜுரம்", "ಜ್ವರ", "बुखार", "temperature", "flu", "influenza"],
    "Diarrhoea":        ["diarrhea", "diarrhoea", "வயிற்றுப்போக்கு", "ಅತಿಸಾರ", "दस्त", "loose motion", "ors"],
    "Dengue":           ["dengue", "டெங்கு", "ಡೆಂಗ್ಯೂ", "platelet", "dengue fever"],
    "Malaria":          ["malaria", "மலேரியா", "ಮಲೇರಿಯಾ", "मलेरिया", "mosquito", "rdts"],
    "Tuberculosis":     ["tb", "tuberculosis", "dots", "cough", "இருமல்", "ಕೆಮ್ಮು", "खांसी", "sputum"],
    "Anaemia":          ["anaemia", "anemia", "hemoglobin", "ஹீமோகுளோபின்", "iron", "pale"],
    "Maternal":         ["maternal", "pregnancy", "anc", "கர்ப்பம்", "ಗರ್ಭ", "गर्भ", "eclampsia"],
    "Child Health":     ["child", "vaccination", "immunization", "growth", "malnutrition", "muac"],
    "Hypertension":     ["bp", "blood pressure", "hypertension", "இரத்த அழுத்தம்", "ಬಿಪಿ", "रक्तचाप"],
    "Diabetes":         ["diabetes", "sugar", "insulin", "metformin", "hba1c", "fasting"],
}

DISTRICTS = [
    "Chennai", "Coimbatore", "Madurai", "Tiruchirappalli", "Salem",
    "Bengaluru Urban", "Mysuru", "Hubli-Dharwad", "Mangaluru", "Belagavi",
]

RISK_THRESHOLDS = {"Fever / ILI": 15, "Diarrhoea": 8, "Dengue": 5, "Malaria": 3, "Tuberculosis": 4}


def _z_score(current: int, baseline: float, std: float) -> float:
    if std < 0.1:
        return 0.0
    return (current - baseline) / std


def _alert_level(z: float) -> str:
    if z >= 3.0: return "critical"
    if z >= 2.0: return "high"
    if z >= 1.5: return "medium"
    return "low"


def _generate_demo_data() -> dict[str, Any]:
    """Synthetic but realistic surveillance data for demo / when DB is empty."""
    rng = random.Random(42)
    now = datetime.now(timezone.utc)

    # Weekly trend for 8 weeks
    weeks = []
    for w in range(7, -1, -1):
        week_start = (now - timedelta(weeks=w)).strftime("%b %d")
        week_data: dict[str, Any] = {"week": week_start}
        for disease in list(DISEASE_KEYWORDS.keys())[:5]:
            base = rng.randint(8, 30)
            spike = 1.0 if w > 1 else rng.uniform(1.0, 3.5)
            week_data[disease] = int(base * spike)
        weeks.append(week_data)

    # Active alerts (2-3 weeks old patterns)
    alerts = []
    alert_diseases = [
        ("Dengue", "Chennai", 3.4, 28, "critical"),
        ("Fever / ILI", "Coimbatore", 2.3, 142, "high"),
        ("Diarrhoea", "Madurai", 2.1, 67, "high"),
        ("Malaria", "Mysuru", 1.7, 19, "medium"),
        ("Tuberculosis", "Belagavi", 1.6, 31, "medium"),
    ]
    for disease, district, z, count, level in alert_diseases:
        alerts.append({
            "id": f"ALT-{disease[:3].upper()}-{district[:3].upper()}",
            "disease": disease,
            "district": district,
            "alert_level": level,
            "z_score": round(z, 2),
            "case_count": count,
            "trend_pct": round((z - 1) * 60),
            "detected_at": (now - timedelta(days=rng.randint(1, 5))).isoformat(),
            "description": f"{count} cases in past 7 days — {round((z - 1) * 60)}% above seasonal baseline.",
            "recommended_action": _recommend(disease, level),
        })

    # District risk map
    district_risk = []
    for d in DISTRICTS:
        risk = rng.choice(["low", "low", "medium", "medium", "high", "critical"])
        district_risk.append({"district": d, "risk": risk, "active_alerts": rng.randint(0, 4)})

    return {
        "summary": {
            "total_alerts": len(alerts),
            "critical_alerts": sum(1 for a in alerts if a["alert_level"] == "critical"),
            "high_alerts": sum(1 for a in alerts if a["alert_level"] == "high"),
            "districts_monitored": len(DISTRICTS),
            "data_sources": 3,
            "last_updated": now.isoformat(),
        },
        "alerts": alerts,
        "weekly_trends": weeks,
        "district_risk": district_risk,
        "demo": True,
    }


def _recommend(disease: str, level: str) -> str:
    base = {
        "Dengue": "Deploy rapid response team. Intensify fogging and larval surveillance. Alert district entomologist.",
        "Fever / ILI": "Strengthen ILI surveillance at PHCs. Issue health advisory. Monitor for influenza clusters.",
        "Diarrhoea": "Inspect water sources for contamination. Distribute ORS. Alert water supply department.",
        "Malaria": "Distribute insecticide-treated nets. Conduct mass blood surveys in hotspot villages.",
        "Tuberculosis": "Activate contact tracing. Verify DOTS adherence. Alert district TB officer.",
    }.get(disease, "Increase surveillance and activate rapid response protocol.")
    if level == "critical":
        return "IMMEDIATE ACTION REQUIRED. " + base
    return base


async def _get_live_data() -> dict[str, Any] | None:
    """Pull real patterns from health_interactions when DB is available."""
    if not db.is_configured():
        return None

    now = datetime.now(timezone.utc)
    cutoff_7d = (now - timedelta(days=7)).isoformat()
    cutoff_28d = (now - timedelta(days=28)).isoformat()

    recent = await db.fetch_all(
        "SELECT transcript_text, intent_detected, created_at FROM health_interactions WHERE created_at > %s",
        (cutoff_7d,),
    )
    baseline_rows = await db.fetch_all(
        "SELECT transcript_text, intent_detected FROM health_interactions WHERE created_at > %s AND created_at <= %s",
        (cutoff_28d, cutoff_7d),
    )
    if not recent:
        return None

    # Count disease mentions
    def count_mentions(rows: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {d: 0 for d in DISEASE_KEYWORDS}
        for row in rows:
            text = (row.get("transcript_text") or "").lower()
            for disease, keywords in DISEASE_KEYWORDS.items():
                if any(kw in text for kw in keywords):
                    counts[disease] += 1
        return counts

    recent_counts = count_mentions(recent)
    baseline_counts = count_mentions(baseline_rows)
    days_baseline = max((len(baseline_rows) / max(len(recent), 1)) * 7, 1)

    alerts = []
    for disease, current in recent_counts.items():
        if current == 0:
            continue
        baseline_weekly = baseline_counts.get(disease, 0) / (days_baseline / 7) if days_baseline else 0
        std = max(math.sqrt(baseline_weekly), 1.0)
        z = _z_score(current, baseline_weekly, std)
        level = _alert_level(z)
        if level in ("medium", "high", "critical"):
            alerts.append({
                "id": f"ALT-{disease[:3].upper()}-LIVE",
                "disease": disease,
                "district": "State-wide (live)",
                "alert_level": level,
                "z_score": round(z, 2),
                "case_count": current,
                "trend_pct": round((current - baseline_weekly) / max(baseline_weekly, 1) * 100),
                "detected_at": now.isoformat(),
                "description": f"{current} interactions in past 7 days ({round(z, 1)}σ above baseline).",
                "recommended_action": _recommend(disease, level),
            })

    return {
        "summary": {
            "total_alerts": len(alerts),
            "critical_alerts": sum(1 for a in alerts if a["alert_level"] == "critical"),
            "high_alerts": sum(1 for a in alerts if a["alert_level"] == "high"),
            "districts_monitored": 10,
            "data_sources": 1,
            "last_updated": now.isoformat(),
        },
        "alerts": sorted(alerts, key=lambda a: a["z_score"], reverse=True),
        "demo": False,
    }


@router.get("/dashboard")
async def dashboard():
    live = await _get_live_data()
    demo = _generate_demo_data()
    if live and live["alerts"]:
        demo.update({"summary": live["summary"], "alerts": live["alerts"], "demo": False})
    return demo


@router.get("/alerts")
async def active_alerts():
    data = await dashboard()
    return {"alerts": data["alerts"], "demo": data.get("demo", True)}


@router.get("/trends")
async def trends():
    data = _generate_demo_data()
    return {"weekly_trends": data["weekly_trends"], "diseases": list(DISEASE_KEYWORDS.keys())[:6]}
@router.get("/hotspots")
async def hotspots(disease: str | None = None):
    """Returns geospatial coordinates for disease occurrences for heatmap visualization."""
    if not db.is_configured():
        # Fallback to random demo hotspots if DB not connected
        rng = random.Random(42)
        demo_spots = []
        for _ in range(50):
            # Centered roughly around South India for demo
            lat = 13.0827 + rng.uniform(-5.0, 5.0)
            lon = 80.2707 + rng.uniform(-5.0, 5.0)
            demo_spots.append({
                "lat": lat,
                "lng": lon,
                "disease": rng.choice(list(DISEASE_KEYWORDS.keys())[:5]),
                "intensity": rng.uniform(0.3, 1.0)
            })
        return {"hotspots": demo_spots, "demo": True}

    # Query real interactions with location data
    # We join health_interactions -> citizens -> locations
    query_sql = """
        SELECT 
            l.geo_coordinates::json->'coordinates' as coords,
            hi.transcript_text,
            hi.intent_detected,
            hi.created_at
        FROM health_interactions hi
        JOIN citizens c ON c.id = hi.citizen_id
        JOIN locations l ON l.id = c.location_id
        WHERE l.geo_coordinates IS NOT NULL
        ORDER BY hi.created_at DESC
        LIMIT 500
    """
    rows = await db.fetch_all(query_sql)
    
    real_spots = []
    for row in rows:
        coords = row.get("coords") # [lon, lat]
        if not coords or len(coords) < 2: continue
        
        text = (row.get("transcript_text") or "").lower()
        matched_disease = None
        for d, keywords in DISEASE_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                matched_disease = d
                break
        
        if matched_disease:
            real_spots.append({
                "lat": coords[1],
                "lng": coords[0],
                "disease": matched_disease,
                "intensity": 0.8
            })

    return {"hotspots": real_spots, "demo": False}
