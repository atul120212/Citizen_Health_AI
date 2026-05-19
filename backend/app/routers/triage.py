"""
Triage router — AI-powered symptom severity classification.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..services.triage_service import TriageService

router = APIRouter(prefix="/api/triage", tags=["triage"])
_triage = TriageService()


class TriageRequest(BaseModel):
    symptoms: list[str]
    language_code: str = "en-IN"


@router.post("")
async def triage_symptoms(req: TriageRequest):
    """
    Classify symptom severity and recommend the appropriate PHC department.

    Returns:
      - severity: low | medium | high | emergency
      - department: recommended PHC department
      - advice: voice-friendly multilingual guidance
      - needs_ambulance: bool
      - red_flags: list of high-severity symptoms detected
    """
    result = await _triage.triage(req.symptoms, req.language_code)
    return result
