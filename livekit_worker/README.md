# LiveKit Worker

This worker registers a realtime agent named `citizen-health-ai` and joins LiveKit rooms when the frontend requests a token (automatic agent dispatch).

Every spoken turn is routed through **`POST /api/voice/text-turn`** on the FastAPI backend so intents, session state, and Sarvam replies stay accurate.

The IVR endpoint in `backend/` is the strict Sarvam path:

```text
browser audio -> FastAPI -> Sarvam Saaras STT -> Sarvam-30B -> Bulbul TTS
```

This worker is the realtime room path:

```text
LiveKit room audio -> LiveKit Agents turn handling -> backend /api/text/turn -> Sarvam-30B business logic
```

To make LiveKit realtime audio use Sarvam for every STT/TTS frame as well, implement custom LiveKit `STT` and `TTS` provider classes around `backend/app/services/sarvam.py` or run a streaming Sarvam gateway when Sarvam exposes a streaming endpoint in your environment.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python agent.py dev
```
