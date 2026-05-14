from fastapi import APIRouter, HTTPException

from .. import db
from ..schemas import CitizenUpsert
from ..services.repository import get_citizen_by_phone, upsert_citizen

router = APIRouter(prefix="/api/citizens", tags=["citizens"])


@router.get("/by-phone/{phone_number}")
async def read_by_phone(phone_number: str):
    if not db.is_configured():
        return {"db_configured": False, "citizen": None}
    citizen = await get_citizen_by_phone(phone_number)
    if not citizen:
        raise HTTPException(status_code=404, detail="Citizen not found")
    return {"db_configured": True, "citizen": citizen}


@router.post("")
async def upsert(payload: CitizenUpsert):
    if not db.is_configured():
        return {"db_configured": False, "citizen": payload.model_dump()}
    citizen = await upsert_citizen(payload)
    return {"db_configured": True, "citizen": citizen}
