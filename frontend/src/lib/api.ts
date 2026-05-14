export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

export type TurnResponse = {
  transcript: string;
  language_code: string;
  language_probability: number | null;
  intent: string;
  response_text: string;
  audio_base64: string | null;
  audio_mime_type: string;
  citizen_id: string | null;
  interaction_id: string | null;
  actions: Array<Record<string, unknown>>;
  db_configured: boolean;
};

export type SessionStartResponse = {
  session_id: string;
  intro_text: string;
  audio_base64: string | null;
  audio_mime_type: string;
};

export async function startSession(input: {
  phone_number?: string;
  language_code?: string;
}): Promise<SessionStartResponse> {
  const response = await fetch(`${API_BASE_URL}/api/session/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input)
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function postTextTurn(input: {
  text: string;
  phone_number?: string;
  language_code?: string;
  session_id?: string;
}) {
  const response = await fetch(`${API_BASE_URL}/api/text/turn`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input)
  });
  if (!response.ok) throw new Error(await response.text());
  return (await response.json()) as TurnResponse;
}

export async function postVoiceTurn(audio: Blob, phoneNumber?: string, sessionId?: string) {
  const formData = new FormData();
  formData.append("audio", audio, "citizen-turn.webm");
  if (phoneNumber) formData.append("phone_number", phoneNumber);
  if (sessionId) formData.append("session_id", sessionId);

  const response = await fetch(`${API_BASE_URL}/api/voice/turn`, {
    method: "POST",
    body: formData
  });
  if (!response.ok) throw new Error(await response.text());
  return (await response.json()) as TurnResponse;
}

export async function createCitizen(input: {
  phone_number: string;
  full_name?: string;
  preferred_language: string;
  district_name?: string;
  phc_name?: string;
}) {
  const response = await fetch(`${API_BASE_URL}/api/citizens`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input)
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function createLiveKitToken(
  roomName: string,
  participantName: string,
  metadata?: object
) {
  const response = await fetch(`${API_BASE_URL}/api/livekit/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ room_name: roomName, participant_name: participantName, metadata })
  });
  if (!response.ok) throw new Error(await response.text());
  return (await response.json()) as { token: string; url: string; room_name: string };
}
