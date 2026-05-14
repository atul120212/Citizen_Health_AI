# API

Base URL: `http://localhost:8000`

## Health

```http
GET /health
```

Returns service configuration flags.

## Voice Turn

```http
POST /api/voice/turn
Content-Type: multipart/form-data
```

Fields:

- `audio`: audio file, usually `audio/webm`.
- `phone_number`: optional citizen phone number used to attach DB actions.

Response:

```json
{
  "transcript": "Book a doctor appointment",
  "language_code": "ta-IN",
  "language_probability": null,
  "intent": "appointment_booking",
  "response_text": "...",
  "audio_base64": "...",
  "audio_mime_type": "audio/wav",
  "citizen_id": "...",
  "interaction_id": "...",
  "actions": [],
  "db_configured": true
}
```

## Text Turn

```http
POST /api/text/turn
Content-Type: application/json
```

```json
{
  "text": "Am I eligible for Ayushman Bharat?",
  "phone_number": "9000000001",
  "language_code": "ta-IN"
}
```

## Citizen Upsert

```http
POST /api/citizens
Content-Type: application/json
```

```json
{
  "phone_number": "9000000001",
  "full_name": "Meena Ravi",
  "preferred_language": "ta",
  "district_name": "Chennai",
  "phc_name": "T Nagar Urban PHC"
}
```

## LiveKit Token

```http
POST /api/livekit/token
Content-Type: application/json
```

```json
{
  "room_name": "citizen-health-demo",
  "participant_name": "9000000001",
  "metadata": {
    "phone_number": "9000000001",
    "language_code": "ta-IN"
  }
}
```
