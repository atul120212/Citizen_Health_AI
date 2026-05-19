from datetime import datetime, timedelta, timezone
from typing import Any

from .. import db
from ..schemas import AppointmentCreate, CitizenUpsert


async def get_citizen_by_phone(phone_number: str) -> dict[str, Any] | None:
    return await db.fetch_one(
        """
        SELECT c.*, l.district_name, l.phc_name, l.village_taluka
        FROM citizens c
        LEFT JOIN locations l ON l.id = c.location_id
        WHERE c.phone_number = %s
        """,
        (phone_number,),
    )


async def get_health_worker_by_phone(phone_number: str) -> dict[str, Any] | None:
    return await db.fetch_one(
        """
        SELECT hw.*, l.district_name, l.phc_name
        FROM health_workers hw
        LEFT JOIN locations l ON l.id = hw.location_id
        WHERE hw.phone_number = %s
        """,
        (phone_number,),
    )



async def upsert_citizen(payload: CitizenUpsert) -> dict[str, Any] | None:
    location_id = None
    if payload.district_name or payload.phc_name or payload.village_taluka:
        location = await db.fetch_one(
            """
            INSERT INTO locations (district_name, phc_name, village_taluka)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (payload.district_name, payload.phc_name, payload.village_taluka),
        )
        location_id = location["id"] if location else None

    return await db.fetch_one(
        """
        INSERT INTO citizens (abha_id, full_name, phone_number, preferred_language, location_id)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (phone_number)
        DO UPDATE SET
            abha_id = COALESCE(EXCLUDED.abha_id, citizens.abha_id),
            full_name = COALESCE(EXCLUDED.full_name, citizens.full_name),
            preferred_language = COALESCE(EXCLUDED.preferred_language, citizens.preferred_language),
            location_id = COALESCE(EXCLUDED.location_id, citizens.location_id)
        RETURNING *
        """,
        (payload.abha_id, payload.full_name, payload.phone_number, payload.preferred_language, location_id),
    )


async def get_nearest_departments(query: str | None = None) -> list[dict[str, Any]]:
    if not query or not query.strip():
        search = "%%"
        is_empty = True
    else:
        search = f"%{query.strip()}%"
        is_empty = False

    return await db.fetch_all(
        """
        SELECT hd.*, l.district_name, l.phc_name
        FROM hospital_departments hd
        LEFT JOIN locations l ON l.id = hd.location_id
        WHERE %s OR hd.department_name ILIKE %s OR hd.services ILIKE %s
        ORDER BY hd.department_name
        LIMIT 6
        """,
        (is_empty, search, search),
    )


async def create_interaction(
    citizen_id: str | None,
    transcript: str,
    intent: str,
    audio_url: str | None,
    needs_worker_followup: bool,
    interaction_type: str = "voice_call",
) -> dict[str, Any] | None:
    status = "needs_worker_followup" if needs_worker_followup else "completed"
    return await db.fetch_one(
        """
        INSERT INTO health_interactions
            (citizen_id, interaction_type, transcript_text, intent_detected, audio_url, status)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (citizen_id, interaction_type, transcript, intent, audio_url, status),
    )


async def create_appointment(payload: AppointmentCreate) -> dict[str, Any] | None:
    return await db.fetch_one(
        """
        INSERT INTO appointments (citizen_id, worker_id, appointment_date, reason, status)
        VALUES (%s, %s, %s, %s, 'scheduled')
        RETURNING *
        """,
        (payload.citizen_id, payload.worker_id, payload.appointment_date, payload.reason),
    )


async def create_followup_appointment(
    citizen_id: str,
    reason: str,
    appointment_date: datetime | None = None,
    appointment_time: str | None = None,
) -> dict[str, Any] | None:
    worker = await db.fetch_one(
        """
        SELECT hw.id
        FROM health_workers hw
        JOIN citizens c ON c.location_id = hw.location_id
        WHERE c.id = %s
        ORDER BY CASE hw.role WHEN 'PHC Nurse' THEN 1 WHEN 'ASHA' THEN 2 ELSE 3 END
        LIMIT 1
        """,
        (citizen_id,),
    )

    if appointment_date is None:
        appointment_date = datetime.now(timezone.utc) + timedelta(days=1)

    # If caller provided a time string like "10:30", merge it into the date
    if appointment_time:
        try:
            hour, minute = (int(x) for x in appointment_time.split(":")[:2])
            appointment_date = appointment_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except (ValueError, AttributeError):
            pass

    return await create_appointment(
        AppointmentCreate(
            citizen_id=citizen_id,
            worker_id=worker["id"] if worker else None,
            appointment_date=appointment_date,
            reason=reason,
        )
    )


async def get_programmes() -> list[dict[str, Any]]:
    return await db.fetch_all(
        """
        SELECT programme_name, language_code, question, answer
        FROM nhm_programme_faqs
        ORDER BY programme_name, language_code
        """
    )


async def get_maternal_reminders(citizen_id: str) -> list[dict[str, Any]]:
    return await db.fetch_all(
        """
        SELECT *
        FROM maternal_reminders
        WHERE citizen_id = %s
        ORDER BY due_date
        """,
        (citizen_id,),
    )


async def create_maternal_reminder(citizen_id: str, reminder_type: str) -> dict[str, Any] | None:
    due_date = datetime.now(timezone.utc) + timedelta(days=7)
    return await db.fetch_one(
        """
        INSERT INTO maternal_reminders (citizen_id, reminder_type, due_date, status)
        VALUES (%s, %s, %s, 'pending')
        RETURNING *
        """,
        (citizen_id, reminder_type, due_date),
    )


async def set_ayushman_precheck(citizen_id: str, is_eligible: bool) -> dict[str, Any] | None:
    return await db.fetch_one(
        """
        UPDATE citizens
        SET ayushman_status = %s
        WHERE id = %s
        RETURNING *
        """,
        (is_eligible, citizen_id),
    )


async def log_patient_vital(citizen_id: str, vital_type: str, value: float, unit: str | None = None) -> dict[str, Any] | None:
    return await db.fetch_one(
        """
        INSERT INTO patient_vitals_log (citizen_id, vital_type, value, unit)
        VALUES (%s, %s, %s, %s)
        RETURNING *
        """,
        (citizen_id, vital_type, value, unit),
    )


async def update_medication_adherence(citizen_id: str, med_name: str) -> dict[str, Any] | None:
    # First, try to find the medication. If not exists, create a dummy one for tracking.
    med = await db.fetch_one(
        "SELECT id FROM medication_schedules WHERE citizen_id = %s AND medication_name ILIKE %s",
        (citizen_id, med_name),
    )
    
    if not med:
        return await db.fetch_one(
            """
            INSERT INTO medication_schedules (citizen_id, medication_name, last_taken_at, adherence_count)
            VALUES (%s, %s, NOW(), 1)
            RETURNING *
            """,
            (citizen_id, med_name),
        )
    
    return await db.fetch_one(
        """
        UPDATE medication_schedules
        SET last_taken_at = NOW(),
            adherence_count = adherence_count + 1,
            updated_at = NOW()
        WHERE id = %s
        RETURNING *
        """,
        (med["id"],),
    )
