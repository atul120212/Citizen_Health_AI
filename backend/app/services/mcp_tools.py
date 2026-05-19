"""
MCP-style Tool Executor for Citizen Health AI.

The LLM decides which tool(s) to call by including a `tool_call` key in its JSON
response.  This module executes the requested tool and returns a structured result
that is fed back to the LLM for a final natural-language reply.

Supported tools:
  - book_appointment
  - check_eligibility
  - get_hospital_navigation
  - set_maternal_reminder
  - search_nhm_programmes
  - get_nearest_phc
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from .. import db
from .repository import (
    create_followup_appointment,
    create_maternal_reminder,
    get_nearest_departments,
    get_programmes,
    set_ayushman_precheck,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {
        "name": "book_appointment",
        "description": "Book a PHC appointment for a citizen. Requires all slot fields to be collected.",
        "parameters": {
            "type": "object",
            "properties": {
                "citizen_id":         {"type": "string"},
                "reason":             {"type": "string"},
                "appointment_date":   {"type": "string", "format": "date"},
                "appointment_time":   {"type": "string"},
                "patient_name":       {"type": "string"},
                "patient_email":      {"type": "string"},
            },
            "required": ["citizen_id", "reason", "appointment_date", "appointment_time"],
        },
    },
    {
        "name": "check_eligibility",
        "description": "Check Ayushman Bharat / CMCHIS eligibility for a citizen.",
        "parameters": {
            "type": "object",
            "properties": {
                "citizen_id": {"type": "string"},
                "abha_id":    {"type": "string"},
            },
            "required": ["citizen_id"],
        },
    },
    {
        "name": "get_hospital_navigation",
        "description": "Return the relevant hospital department / counter for a service.",
        "parameters": {
            "type": "object",
            "properties": {
                "service_query": {"type": "string"},
            },
            "required": ["service_query"],
        },
    },
    {
        "name": "set_maternal_reminder",
        "description": "Set a maternal health reminder for a pregnant citizen.",
        "parameters": {
            "type": "object",
            "properties": {
                "citizen_id":    {"type": "string"},
                "reminder_type": {"type": "string", "enum": ["anc", "vaccination", "supplements", "delivery"]},
            },
            "required": ["citizen_id", "reminder_type"],
        },
    },
    {
        "name": "search_nhm_programmes",
        "description": "Search NHM programme FAQs for a topic.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
    },
]

# Human-readable tool descriptions injected into the system prompt
TOOLS_DESCRIPTION = """
Available MCP Tools (include `tool_call` in your JSON response to invoke one):
  - book_appointment(citizen_id, reason, appointment_date, appointment_time, patient_name?, patient_email?)
  - check_eligibility(citizen_id, abha_id?)
  - get_hospital_navigation(service_query)
  - set_maternal_reminder(citizen_id, reminder_type)
  - search_nhm_programmes(query)

If a tool call is needed, add: "tool_call": {"name": "<tool_name>", "args": {...}}
"""


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

class MCPExecutor:
    """Execute MCP tool calls and return structured results."""

    async def execute(
        self,
        tool_name: str,
        args: dict[str, Any],
        citizen: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Dispatch to the correct tool handler."""
        handlers = {
            "book_appointment":       self._book_appointment,
            "check_eligibility":      self._check_eligibility,
            "get_hospital_navigation": self._get_hospital_navigation,
            "set_maternal_reminder":  self._set_maternal_reminder,
            "search_nhm_programmes":  self._search_nhm_programmes,
        }
        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}
        try:
            return await handler(args, citizen)
        except Exception as exc:
            logger.error("Tool %s failed: %s", tool_name, exc)
            return {"error": str(exc)}

    async def _book_appointment(self, args: dict, citizen: dict | None) -> dict:
        cid = args.get("citizen_id") or (citizen["id"] if citizen else None)
        if not cid:
            return {"error": "citizen_id required"}
        if not db.is_configured():
            return {
                "status": "demo",
                "message": "Appointment recorded (demo mode — DB not connected).",
                "date": args.get("appointment_date"),
                "time": args.get("appointment_time"),
                "reason": args.get("reason"),
            }
        appt = await create_followup_appointment(
            citizen_id=cid,
            reason=args.get("reason", "General consultation"),
            appointment_date=datetime.fromisoformat(args["appointment_date"]).replace(tzinfo=timezone.utc)
            if args.get("appointment_date") and args["appointment_date"] != "null" else None,
            appointment_time=args.get("appointment_time"),
        )
        return {"status": "booked", "appointment_id": appt["id"] if appt else None}

    async def _check_eligibility(self, args: dict, citizen: dict | None) -> dict:
        cid = args.get("citizen_id") or (citizen["id"] if citizen else None)
        if not cid:
            return {"error": "citizen_id required"}
        eligible = bool(citizen and (citizen.get("abha_id") or citizen.get("ayushman_status")))
        if db.is_configured():
            await set_ayushman_precheck(cid, eligible)
        schemes = []
        if eligible:
            schemes = ["Ayushman Bharat PM-JAY", "CMCHIS (Tamil Nadu)"]
        return {
            "eligible": eligible,
            "schemes": schemes,
            "note": "This is a pre-check. Final approval at nearest PHC.",
        }

    async def _get_hospital_navigation(self, args: dict, citizen: dict | None) -> dict:
        departments = await get_nearest_departments(args.get("service_query"))
        if not departments:
            return {
                "departments": [],
                "message": "Registration counter is on the ground floor. Ask the help desk.",
            }
        return {"departments": departments}

    async def _set_maternal_reminder(self, args: dict, citizen: dict | None) -> dict:
        cid = args.get("citizen_id") or (citizen["id"] if citizen else None)
        if not cid:
            return {"error": "citizen_id required"}
        if not db.is_configured():
            return {"status": "demo", "reminder_type": args.get("reminder_type")}
        reminder = await create_maternal_reminder(cid, args.get("reminder_type", "anc"))
        return {"status": "set", "reminder_id": reminder["id"] if reminder else None}

    async def _search_nhm_programmes(self, args: dict, citizen: dict | None) -> dict:
        programmes = await get_programmes()
        query = (args.get("query") or "").lower()
        results = [
            p for p in programmes
            if query in (p.get("programme_name") or "").lower()
            or query in (p.get("question") or "").lower()
        ][:5]
        return {"results": results}
