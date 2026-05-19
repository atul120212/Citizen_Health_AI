from fastapi import APIRouter, HTTPException

from .. import db
from ..schemas import AppointmentCreate
from ..services.email_service import send_appointment_confirmation
from ..services.repository import create_appointment, get_citizen_by_phone

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


async def _get_citizen(citizen_id: str) -> dict | None:
    return await db.fetch_one(
        """
        SELECT c.full_name, c.preferred_language, l.phc_name
        FROM citizens c
        LEFT JOIN locations l ON l.id = c.location_id
        WHERE c.id = %s
        """,
        (citizen_id,),
    )


@router.post("")
async def create(payload: AppointmentCreate):
    if not db.is_configured():
        return {"db_configured": False, "appointment": payload.model_dump(mode="json")}
    appointment = await create_appointment(payload)
    if not appointment:
        raise HTTPException(status_code=400, detail="Could not create appointment")

    if payload.email:
        citizen = await _get_citizen(payload.citizen_id)
        patient_name = (citizen or {}).get("full_name") or "Patient"
        phc_name = (citizen or {}).get("phc_name") or "Your PHC"
        lang = payload.language_code or (citizen or {}).get("preferred_language") or "en-IN"
        appt_dt = payload.appointment_date
        await send_appointment_confirmation(
            to_email=payload.email,
            patient_name=patient_name,
            reason=payload.reason,
            date=appt_dt.strftime("%Y-%m-%d"),
            time=appt_dt.strftime("%H:%M"),
            phc=phc_name,
            language_code=lang,
        )

    return {"db_configured": True, "appointment": appointment}
