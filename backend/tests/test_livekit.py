"""LiveKit token and configuration tests."""
import json
import os
import unittest

from app.config import get_settings
from app.services.livekit_tokens import create_livekit_token


class LiveKitTokenTests(unittest.TestCase):
    def setUp(self) -> None:
        get_settings.cache_clear()

    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_token_includes_agent_dispatch(self) -> None:
        os.environ["LIVEKIT_URL"] = "wss://test.livekit.cloud"
        os.environ["LIVEKIT_API_KEY"] = "test-api-key-32-chars-minimum-xx"
        os.environ["LIVEKIT_API_SECRET"] = "test-api-secret-32-chars-minimum-xx"
        os.environ["LIVEKIT_AGENT_NAME"] = "citizen-health-ai"
        get_settings.cache_clear()
        meta = {"session_id": "sess-abc", "language_code": "en-IN"}
        jwt, url = create_livekit_token("room-1", "user-1", meta)
        self.assertTrue(jwt)
        self.assertEqual(url, os.environ["LIVEKIT_URL"])

        payload_b64 = jwt.split(".")[1]
        padding = "=" * (-len(payload_b64) % 4)
        payload = json.loads(__import__("base64").urlsafe_b64decode(payload_b64 + padding))
        room_cfg = payload.get("roomConfig") or payload.get("room_config") or {}
        agents = room_cfg.get("agents") or []
        self.assertTrue(agents, "JWT must include RoomAgentDispatch for automatic agent join")
        self.assertEqual(agents[0].get("agentName") or agents[0].get("agent_name"), "citizen-health-ai")

    def test_missing_credentials_raises(self) -> None:
        os.environ["LIVEKIT_URL"] = ""
        os.environ["LIVEKIT_API_KEY"] = ""
        os.environ["LIVEKIT_API_SECRET"] = ""
        get_settings.cache_clear()
        with self.assertRaises(RuntimeError):
            create_livekit_token("r", "u", {})


if __name__ == "__main__":
    unittest.main()
