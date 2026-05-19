"""
Outreach Service — Proactive Health Management
Handles scanning for missing logs and triggering outbound interventions.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any
from .. import db

class OutreachService:
    async def get_pending_interventions(self) -> List[Dict[str, Any]]:
        """Finds patients who missed meds or vitals for > 48 hours."""
        if not db.is_configured():
            return []
            
        # 1. Check for missed vitals in NCD patients
        # We look for citizens who had a vitals log before but not in the last 2 days
        vitals_missed = await db.fetch_all(
            """
            SELECT c.id, c.full_name, c.phone_number, MAX(v.created_at) as last_log
            FROM citizens c
            JOIN patient_vitals_log v ON v.citizen_id = c.id
            GROUP BY c.id, c.full_name, c.phone_number
            HAVING MAX(v.created_at) < NOW() - INTERVAL '2 days'
            """
        )
        
        # 2. Check for medication adherence drops
        med_missed = await db.fetch_all(
            """
            SELECT c.id, c.full_name, c.phone_number, m.medication_name
            FROM citizens c
            JOIN medication_schedules m ON m.citizen_id = c.id
            WHERE m.is_taken = false 
              AND m.created_at > NOW() - INTERVAL '24 hours'
            """
        )
        
        interventions = []
        for row in vitals_missed:
            interventions.append({
                "type": "vitals_reminder",
                "patient_name": row["full_name"],
                "reason": "Missed BP/Sugar log for 48h",
                "priority": "medium"
            })
            
        for row in med_missed:
            interventions.append({
                "type": "med_adherence",
                "patient_name": row["full_name"],
                "reason": f"Missed dose: {row['medication_name']}",
                "priority": "high"
            })
            
        return interventions

    async def trigger_outbound_alert(self, patient_id: str, alert_type: str):
        """Simulates triggering an outbound call via LiveKit or SMS."""
        print(f"TRIGGERING PROACTIVE ALERT: {alert_type} for patient {patient_id}")
        return {"status": "dispatched"}
