from fastapi import APIRouter, HTTPException

from .. import db
from ..schemas import AppointmentCreate
from ..services.repository import create_appointment

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


@router.post("")
async def create(payload: AppointmentCreate):
    if not db.is_configured():
        return {"db_configured": False, "appointment": payload.model_dump(mode="json")}
    appointment = await create_appointment(payload)
    if not appointment:
        raise HTTPException(status_code=400, detail="Could not create appointment")
    return {"db_configured": True, "appointment": appointment}
