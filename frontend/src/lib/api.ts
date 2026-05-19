export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

// ── Types ──────────────────────────────────────────────────────────────────

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

export type SessionSummary = {
  session_id: string;
  citizen: Record<string, unknown> | null;
  verification_state: "pending" | "verified" | "guest";
  language_code: string | null;
  turns: number;
  call_summary: string | null;
  started_at: string | null;
  history_length: number;
};

// ── API Calls ──────────────────────────────────────────────────────────────

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

export async function postVoiceTurn(
  audio: Blob,
  phoneNumber?: string,
  sessionId?: string
): Promise<TurnResponse> {
  const formData = new FormData();
  formData.append("audio", audio, "citizen-turn.webm");
  if (phoneNumber) formData.append("phone_number", phoneNumber);
  if (sessionId)   formData.append("session_id", sessionId);

  const response = await fetch(`${API_BASE_URL}/api/voice/turn`, {
    method: "POST",
    body: formData
  });
  if (!response.ok) throw new Error(await response.text());
  return (await response.json()) as TurnResponse;
}

export async function fetchSessionSummary(sessionId: string): Promise<SessionSummary> {
  const response = await fetch(`${API_BASE_URL}/api/session/${sessionId}/summary`, {
    method: "POST"
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
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

export type LiveKitTokenResponse = {
  token: string;
  url: string;
  room_name: string;
  agent_name?: string | null;
};

export async function fetchLiveKitHealth(): Promise<{
  configured: boolean;
  url?: string;
  agent_name?: string;
}> {
  const response = await fetch(`${API_BASE_URL}/api/livekit/health`);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function createLiveKitToken(
  roomName: string,
  participantName: string,
  metadata?: Record<string, unknown>
): Promise<LiveKitTokenResponse> {
  const response = await fetch(`${API_BASE_URL}/api/livekit/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      room_name: roomName,
      participant_name: participantName,
      metadata: metadata ?? {},
    }),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}
