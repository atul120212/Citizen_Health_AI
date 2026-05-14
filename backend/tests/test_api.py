import os
import unittest

os.environ["DATABASE_URL"] = ""
os.environ["SARVAM_API_KEY"] = ""
os.environ["LIVEKIT_URL"] = ""
os.environ["LIVEKIT_API_KEY"] = ""
os.environ["LIVEKIT_API_SECRET"] = ""

from app.main import health
from app.routers.citizens import upsert
from app.routers.livekit import token
from app.routers.voice import text_turn, voice_turn
from app.schemas import CitizenUpsert, LiveKitTokenRequest, TextTurnRequest


class DummyUpload:
    filename = "turn.webm"
    content_type = "audio/webm"

    async def read(self) -> bytes:
        return b"fake-audio"


# ---------------------------------------------------------------------------
# Health & configuration
# ---------------------------------------------------------------------------

class HealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_reports_demo_mode(self) -> None:
        payload = await health()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["db_configured"])
        self.assertFalse(payload["sarvam_configured"])
        self.assertFalse(payload["livekit_configured"])

    async def test_health_shape(self) -> None:
        payload = await health()
        for key in ("ok", "db_configured", "sarvam_configured", "livekit_configured"):
            self.assertIn(key, payload)


# ---------------------------------------------------------------------------
# Intent detection — English
# ---------------------------------------------------------------------------

class EnglishIntentTests(unittest.IsolatedAsyncioTestCase):
    async def _turn(self, text: str):
        return await text_turn(
            TextTurnRequest(text=text, phone_number="9000001001", language_code="en-IN")
        )

    async def test_appointment_booking(self) -> None:
        r = await self._turn("Book a doctor appointment tomorrow morning")
        self.assertEqual(r.intent, "appointment_booking")
        self.assertIn("health concern", r.response_text)

    async def test_hospital_navigation_counter(self) -> None:
        r = await self._turn("Where is the registration counter?")
        self.assertEqual(r.intent, "hospital_navigation")

    async def test_hospital_navigation_room(self) -> None:
        r = await self._turn("Which room is the pharmacy?")
        self.assertEqual(r.intent, "hospital_navigation")

    async def test_maternal_health_reminder_anc(self) -> None:
        r = await self._turn("Set my pregnant mother ANC reminder")
        self.assertEqual(r.intent, "maternal_health_reminder")

    async def test_maternal_health_reminder_vaccine(self) -> None:
        r = await self._turn("I need a vaccine reminder for my baby")
        self.assertEqual(r.intent, "maternal_health_reminder")

    async def test_eligibility_check_ayushman(self) -> None:
        r = await self._turn("Am I eligible for Ayushman Bharat?")
        self.assertEqual(r.intent, "eligibility_check")

    async def test_eligibility_check_cmchis(self) -> None:
        r = await self._turn("Check CMCHIS insurance eligibility for me")
        self.assertEqual(r.intent, "eligibility_check")

    async def test_emergency_chest_pain(self) -> None:
        r = await self._turn("I have severe chest pain right now")
        self.assertEqual(r.intent, "emergency")

    async def test_emergency_bleeding(self) -> None:
        r = await self._turn("There is heavy bleeding, what do I do?")
        self.assertEqual(r.intent, "emergency")

    async def test_nhm_programme_query(self) -> None:
        r = await self._turn("Tell me about NHM programmes available here")
        self.assertEqual(r.intent, "nhm_programme_query")

    async def test_doctor_slot_keyword(self) -> None:
        r = await self._turn("I want a doctor slot for next week")
        self.assertEqual(r.intent, "appointment_booking")

    async def test_response_text_not_empty(self) -> None:
        r = await self._turn("Book a doctor appointment")
        self.assertTrue(r.response_text.strip())

    async def test_language_code_normalised(self) -> None:
        r = await self._turn("Book a doctor appointment")
        self.assertEqual(r.language_code, "en-IN")

    async def test_db_configured_false_in_demo(self) -> None:
        r = await self._turn("Book a doctor appointment")
        self.assertFalse(r.db_configured)

    async def test_actions_empty_without_db(self) -> None:
        r = await self._turn("Book a doctor appointment")
        self.assertEqual(r.actions, [])

    async def test_audio_base64_none_without_sarvam(self) -> None:
        r = await self._turn("Book a doctor appointment")
        self.assertIsNone(r.audio_base64)


# ---------------------------------------------------------------------------
# Intent detection — Tamil keywords
# ---------------------------------------------------------------------------

class TamilIntentTests(unittest.IsolatedAsyncioTestCase):
    async def _turn(self, text: str):
        return await text_turn(
            TextTurnRequest(text=text, phone_number="9000001002", language_code="ta-IN")
        )

    async def test_appointment_booking_tamil(self) -> None:
        r = await self._turn("மருத்துவர் appointment வேண்டும்")
        self.assertEqual(r.intent, "appointment_booking")

    async def test_hospital_navigation_tamil(self) -> None:
        r = await self._turn("எங்கே registration counter இருக்கிறது?")
        self.assertEqual(r.intent, "hospital_navigation")

    async def test_maternal_health_reminder_tamil(self) -> None:
        r = await self._turn("கர்ப்ப reminder வேண்டும்")
        self.assertEqual(r.intent, "maternal_health_reminder")

    async def test_response_prefixed_with_tamil(self) -> None:
        r = await self._turn("மருத்துவர் appointment வேண்டும்")
        self.assertIn("உங்களுக்கு", r.response_text)

    async def test_language_code_normalised_ta(self) -> None:
        r = await self._turn("appointment வேண்டும்")
        self.assertEqual(r.language_code, "ta-IN")


# ---------------------------------------------------------------------------
# Intent detection — Kannada keywords
# ---------------------------------------------------------------------------

class KannadaIntentTests(unittest.IsolatedAsyncioTestCase):
    async def _turn(self, text: str):
        return await text_turn(
            TextTurnRequest(text=text, phone_number="9000001003", language_code="kn-IN")
        )

    async def test_appointment_booking_kannada(self) -> None:
        r = await self._turn("ವೈದ್ಯ appointment ಬೇಕು")
        self.assertEqual(r.intent, "appointment_booking")

    async def test_hospital_navigation_kannada(self) -> None:
        r = await self._turn("registration counter ಎಲ್ಲಿ ಇದೆ?")
        self.assertEqual(r.intent, "hospital_navigation")

    async def test_maternal_health_reminder_kannada(self) -> None:
        r = await self._turn("ಗರ್ಭಿಣಿ reminder ಬೇಕು")
        self.assertEqual(r.intent, "maternal_health_reminder")

    async def test_response_prefixed_with_kannada(self) -> None:
        r = await self._turn("ವೈದ್ಯ appointment ಬೇಕು")
        self.assertIn("ನಾನು ಸಹಾಯ", r.response_text)

    async def test_language_code_normalised_kn(self) -> None:
        r = await self._turn("appointment ಬೇಕು")
        self.assertEqual(r.language_code, "kn-IN")


# ---------------------------------------------------------------------------
# Language code normalisation
# ---------------------------------------------------------------------------

class LanguageNormalisationTests(unittest.IsolatedAsyncioTestCase):
    async def test_ta_dash_in_accepted(self) -> None:
        r = await text_turn(TextTurnRequest(text="book appointment", language_code="ta-IN"))
        self.assertEqual(r.language_code, "ta-IN")

    async def test_ta_underscore_normalised(self) -> None:
        r = await text_turn(TextTurnRequest(text="book appointment", language_code="ta_IN"))
        self.assertEqual(r.language_code, "ta-IN")

    async def test_kn_normalised(self) -> None:
        r = await text_turn(TextTurnRequest(text="book appointment", language_code="kn_IN"))
        self.assertEqual(r.language_code, "kn-IN")

    async def test_unknown_language_defaults_to_en(self) -> None:
        r = await text_turn(TextTurnRequest(text="book appointment", language_code="fr-FR"))
        self.assertEqual(r.language_code, "en-IN")


# ---------------------------------------------------------------------------
# Voice turn (demo STT path)
# ---------------------------------------------------------------------------

class VoiceTurnTests(unittest.IsolatedAsyncioTestCase):
    async def test_voice_turn_appointment_fallback(self) -> None:
        r = await voice_turn(audio=DummyUpload(), phone_number="9000001001")
        self.assertEqual(r.intent, "appointment_booking")
        self.assertIsNone(r.audio_base64)

    async def test_voice_turn_no_phone_number(self) -> None:
        r = await voice_turn(audio=DummyUpload(), phone_number=None)
        self.assertIsNotNone(r.intent)
        self.assertIsNotNone(r.transcript)

    async def test_voice_turn_response_text_set(self) -> None:
        r = await voice_turn(audio=DummyUpload(), phone_number="9000001001")
        self.assertTrue(r.response_text.strip())

    async def test_voice_turn_db_false_in_demo(self) -> None:
        r = await voice_turn(audio=DummyUpload(), phone_number="9000001001")
        self.assertFalse(r.db_configured)


# ---------------------------------------------------------------------------
# LiveKit token endpoint
# ---------------------------------------------------------------------------

class LiveKitTokenTests(unittest.IsolatedAsyncioTestCase):
    async def test_token_requires_credentials(self) -> None:
        with self.assertRaises(Exception) as ctx:
            await token(LiveKitTokenRequest(room_name="test-room", participant_name="9000001001"))
        self.assertEqual(getattr(ctx.exception, "status_code", None), 503)

    async def test_token_error_message_informative(self) -> None:
        with self.assertRaises(Exception) as ctx:
            await token(LiveKitTokenRequest(room_name="test-room", participant_name="9000001001"))
        detail = getattr(ctx.exception, "detail", "")
        self.assertIn("LiveKit", detail)


# ---------------------------------------------------------------------------
# Citizen upsert
# ---------------------------------------------------------------------------

class CitizenUpsertTests(unittest.IsolatedAsyncioTestCase):
    async def test_demo_payload_without_database(self) -> None:
        r = await upsert(CitizenUpsert(
            phone_number="9000001001",
            full_name="Meena Ravi",
            preferred_language="ta",
        ))
        self.assertFalse(r["db_configured"])
        self.assertEqual(r["citizen"]["phone_number"], "9000001001")

    async def test_upsert_preserves_full_name(self) -> None:
        r = await upsert(CitizenUpsert(
            phone_number="9000001001",
            full_name="Meena Ravi",
            preferred_language="ta",
        ))
        self.assertEqual(r["citizen"]["full_name"], "Meena Ravi")

    async def test_upsert_preserves_district(self) -> None:
        r = await upsert(CitizenUpsert(
            phone_number="9000001001",
            full_name="Meena Ravi",
            preferred_language="ta",
            district_name="Chennai",
        ))
        self.assertEqual(r["citizen"]["district_name"], "Chennai")

    async def test_upsert_kannada_language(self) -> None:
        r = await upsert(CitizenUpsert(
            phone_number="9000002001",
            full_name="Ravi Kumar",
            preferred_language="kn",
        ))
        self.assertEqual(r["citizen"]["preferred_language"], "kn")


# ---------------------------------------------------------------------------
# Response content quality checks
# ---------------------------------------------------------------------------

class ResponseQualityTests(unittest.IsolatedAsyncioTestCase):
    async def test_emergency_response_urgent(self) -> None:
        r = await text_turn(TextTurnRequest(
            text="I have chest pain and can't breathe",
            language_code="en-IN",
        ))
        self.assertEqual(r.intent, "emergency")
        # Should direct to emergency services
        lower = r.response_text.lower()
        self.assertTrue(
            "emergency" in lower or "urgent" in lower or "nearest" in lower,
            msg=f"Expected emergency language in: {r.response_text}",
        )

    async def test_eligibility_response_asks_for_id(self) -> None:
        r = await text_turn(TextTurnRequest(
            text="Check Ayushman eligibility",
            language_code="en-IN",
        ))
        self.assertEqual(r.intent, "eligibility_check")
        lower = r.response_text.lower()
        self.assertTrue(
            "abha" in lower or "phone" in lower or "check" in lower or "pre-check" in lower,
            msg=f"Expected eligibility prompt in: {r.response_text}",
        )

    async def test_appointment_response_asks_reason(self) -> None:
        r = await text_turn(TextTurnRequest(
            text="Book a doctor appointment",
            language_code="en-IN",
        ))
        self.assertEqual(r.intent, "appointment_booking")
        self.assertIn("health concern", r.response_text.lower())

    async def test_nhm_response_non_empty(self) -> None:
        r = await text_turn(TextTurnRequest(
            text="Tell me about NHM programmes",
            language_code="en-IN",
        ))
        self.assertEqual(r.intent, "nhm_programme_query")
        self.assertTrue(r.response_text.strip())


if __name__ == "__main__":
    unittest.main()
