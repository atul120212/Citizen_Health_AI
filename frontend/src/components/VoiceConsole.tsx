"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Room, RoomEvent, Track } from "livekit-client";
import {
  Activity,
  Baby,
  Bot,
  CalendarClock,
  Hospital,
  Languages,
  Loader2,
  Mic,
  PhoneOff,
  Radio,
  Send,
  ShieldCheck,
  UserRound,
  Volume2
} from "lucide-react";

import {
  TurnResponse,
  createCitizen,
  createLiveKitToken,
  postTextTurn,
  postVoiceTurn,
  startSession
} from "@/lib/api";

type SpeechState = {
  hasSpeech: boolean;
  lastVoiceAt: number;
  startedAt: number;
  stopped: boolean;
  discard: boolean;
};

type ChatEntry = {
  role: "agent" | "user";
  text: string;
  intent?: string;
};

const quickPrompts = [
  { icon: Hospital, label: "PHC counter", text: "Where is the registration counter?" },
  { icon: ShieldCheck, label: "Eligibility", text: "Am I eligible for Ayushman Bharat or CMCHIS?" },
  { icon: CalendarClock, label: "Appointment", text: "Book a doctor appointment for tomorrow morning." },
  { icon: Baby, label: "ANC reminder", text: "Set my maternal health reminder for ANC visit." }
];

// Probe at call-time so the check runs inside a user-gesture context after
// the browser has fully initialised its codec registry.
function getSupportedMimeType(): string {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4",
  ];
  for (const type of candidates) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(type)) {
      return type;
    }
  }
  return ""; // empty string → browser picks its own default
}

// VAD tuning — fast silence detection for low latency
const SILENCE_MS = 650;
const MIN_SPEECH_MS = 250;
const MAX_TURN_MS = 14000;
const NO_SPEECH_ROLLOVER_MS = 30000;
const VOICE_THRESHOLD = 0.022;

export function VoiceConsole() {
  const [phoneNumber, setPhoneNumber] = useState("9000001001");
  const [fullName, setFullName] = useState("Meena Ravi");
  const [languageCode, setLanguageCode] = useState("ta-IN");
  const [district, setDistrict] = useState("Chennai");
  const [phcName, setPhcName] = useState("T Nagar Urban Primary Health Centre");
  const [text, setText] = useState("Book a doctor appointment for tomorrow morning.");

  const [status, setStatus] = useState("Ready");
  const [error, setError] = useState<string | null>(null);
  const [isLive, setIsLive] = useState(false);
  const [isProcessingTurn, setIsProcessingTurn] = useState(false);
  const [roomName, setRoomName] = useState<string | null>(null);
  const [agentState, setAgentState] = useState("Not connected");
  const [voiceLevel, setVoiceLevel] = useState(0);

  // Session and conversation history
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [chatHistory, setChatHistory] = useState<ChatEntry[]>([]);

  // Latest turn result (for result-grid display)
  const [turn, setTurn] = useState<TurnResponse | null>(null);

  const roomRef = useRef<Room | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const animationRef = useRef<number | null>(null);
  const levelAnimRef = useRef<number | null>(null);
  const speechStateRef = useRef<SpeechState>({
    hasSpeech: false,
    lastVoiceAt: 0,
    startedAt: 0,
    stopped: false,
    discard: false
  });
  const responseAudioRef = useRef<HTMLAudioElement | null>(null);
  const remoteAudioRef = useRef<HTMLDivElement | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  // Scroll chat to bottom whenever history grows
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatHistory]);

  const startLevelMeter = useCallback((analyser: AnalyserNode) => {
    analyserRef.current = analyser;
    const data = new Uint8Array(analyser.fftSize);
    const tick = () => {
      if (!analyserRef.current) return;
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (const v of data) {
        const c = (v - 128) / 128;
        sum += c * c;
      }
      const rms = Math.sqrt(sum / data.length);
      setVoiceLevel((prev) => prev * 0.6 + rms * 0.4);
      levelAnimRef.current = requestAnimationFrame(tick);
    };
    levelAnimRef.current = requestAnimationFrame(tick);
  }, []);

  const stopLevelMeter = useCallback(() => {
    analyserRef.current = null;
    if (levelAnimRef.current) {
      cancelAnimationFrame(levelAnimRef.current);
      levelAnimRef.current = null;
    }
    setVoiceLevel(0);
  }, []);

  function pushChat(entry: ChatEntry) {
    setChatHistory((prev) => [...prev, entry]);
  }

  async function saveCitizen() {
    setError(null);
    setStatus("Saving citizen");
    await createCitizen({
      phone_number: phoneNumber,
      full_name: fullName,
      preferred_language: languageCode.slice(0, 2),
      district_name: district,
      phc_name: phcName
    });
    setStatus(isLive ? "Listening" : "Citizen saved");
  }

  async function submitText(promptText = text) {
    setError(null);
    setStatus("Thinking");
    const result = await postTextTurn({
      text: promptText,
      phone_number: phoneNumber,
      language_code: languageCode,
      session_id: sessionId ?? undefined
    });
    setTurn(result);
    pushChat({ role: "user", text: promptText });
    pushChat({ role: "agent", text: result.response_text, intent: result.intent });
    await playBulbulAudio(result);
    setStatus(isLive ? "Listening" : "Ready");
  }

  async function startRealtime() {
    setError(null);

    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      throw new Error(
        "Microphone access is not available on this page. " +
          "Open the app via http://localhost:3001 (or serve over HTTPS) so the browser grants microphone permission."
      );
    }

    // ── 1. Start session → get intro audio ───────────────────────
    setStatus("Starting session");
    const session = await startSession({
      phone_number: phoneNumber,
      language_code: languageCode
    });
    setSessionId(session.session_id);
    pushChat({ role: "agent", text: session.intro_text });

    // ── 2. Connect to LiveKit ─────────────────────────────────────
    setStatus("Joining LiveKit");
    setAgentState("Connecting");
    const nextRoomName = `citizen-health-${Date.now()}`;
    const participantName = phoneNumber || `citizen-${Date.now()}`;
    const token = await createLiveKitToken(nextRoomName, participantName, {
      phone_number: phoneNumber,
      language_code: languageCode,
      full_name: fullName
    });

    const room = new Room({ adaptiveStream: true, dynacast: true });
    roomRef.current = room;
    setRoomName(token.room_name);

    room
      .on(RoomEvent.Connected, () => {
        setAgentState("LiveKit connected");
      })
      .on(RoomEvent.Reconnecting, () => {
        setAgentState("Reconnecting");
        setStatus("Reconnecting");
      })
      .on(RoomEvent.Reconnected, () => {
        setAgentState("LiveKit connected");
        setStatus("Listening");
      })
      .on(RoomEvent.Disconnected, () => {
        setAgentState("Disconnected");
        setIsLive(false);
        stopLevelMeter();
      })
      .on(RoomEvent.ParticipantConnected, (participant) => {
        setAgentState(`${participant.identity} joined`);
      })
      .on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind === Track.Kind.Audio && remoteAudioRef.current) {
          remoteAudioRef.current.appendChild(track.attach());
        }
      });

    await room.connect(token.url, token.token);

    // ── 3. Play intro audio ───────────────────────────────────────
    setStatus("Speaking");
    await playIntroAudio(session);

    // ── 4. Open mic and start VAD ─────────────────────────────────
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
    });
    micStreamRef.current = stream;

    const [audioTrack] = stream.getAudioTracks();
    await room.localParticipant.publishTrack(audioTrack, {
      name: "citizen-microphone",
      source: Track.Source.Microphone
    });

    setIsLive(true);
    setStatus("Listening");
    setAgentState("Mic streaming through LiveKit");
    startAutoTurnRecorder(stream, session.session_id);
  }

  async function playIntroAudio(session: { audio_base64: string | null; audio_mime_type: string }) {
    if (!session.audio_base64) return;
    responseAudioRef.current?.pause();
    const audio = new Audio(`data:${session.audio_mime_type};base64,${session.audio_base64}`);
    responseAudioRef.current = audio;
    await new Promise<void>((resolve) => {
      audio.onended = () => resolve();
      audio.onerror = () => resolve();
      audio.play().catch(() => resolve());
    });
  }

  async function stopRealtime() {
    stopCurrentRecorder(true);
    stopLevelMeter();
    responseAudioRef.current?.pause();
    responseAudioRef.current = null;
    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    micStreamRef.current = null;
    await roomRef.current?.disconnect();
    roomRef.current = null;
    setIsLive(false);
    setIsProcessingTurn(false);
    setStatus("Ready");
    setAgentState("Not connected");
    setRoomName(null);
    setSessionId(null);
    setChatHistory([]);
  }

  function startAutoTurnRecorder(stream: MediaStream, sid: string) {
    if (!roomRef.current) return;

    stopCurrentRecorder();
    chunksRef.current = [];
    speechStateRef.current = {
      hasSpeech: false,
      lastVoiceAt: 0,
      startedAt: performance.now(),
      stopped: false,
      discard: false
    };

    const mimeType = getSupportedMimeType();
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
    recorderRef.current = recorder;

    const audioContext = new AudioContext();
    const analyser = audioContext.createAnalyser();
    const source = audioContext.createMediaStreamSource(stream);
    source.connect(analyser);
    startLevelMeter(analyser);

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };

    recorder.onstop = async () => {
      cancelAnimationFrameIfNeeded();
      stopLevelMeter();
      source.disconnect();
      await audioContext.close();

      const state = speechStateRef.current;
      const blob = new Blob(chunksRef.current, { type: "audio/webm" });
      chunksRef.current = [];

      if (state.discard || !roomRef.current || !state.hasSpeech || blob.size < 900) {
        if (roomRef.current) window.setTimeout(() => startAutoTurnRecorder(stream, sid), 150);
        return;
      }

      await sendVoiceTurn(blob, sid);
      if (roomRef.current) window.setTimeout(() => startAutoTurnRecorder(stream, sid), 150);
    };

    recorder.start(200);
    monitorSpeechLevel(analyser);
  }

  function monitorSpeechLevel(analyser: AnalyserNode) {
    const data = new Uint8Array(analyser.fftSize);

    const tick = () => {
      const recorder = recorderRef.current;
      const state = speechStateRef.current;
      if (!recorder || recorder.state !== "recording" || state.stopped) return;

      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (const value of data) {
        const c = (value - 128) / 128;
        sum += c * c;
      }
      const rms = Math.sqrt(sum / data.length);
      const now = performance.now();

      if (rms > VOICE_THRESHOLD) {
        if (!state.hasSpeech) state.startedAt = now;
        state.hasSpeech = true;
        state.lastVoiceAt = now;
        setStatus("Listening");
      }

      const speechDuration = now - state.startedAt;
      const silenceDuration = now - state.lastVoiceAt;
      const shouldClose =
        (state.hasSpeech && speechDuration > MIN_SPEECH_MS && silenceDuration > SILENCE_MS) ||
        (state.hasSpeech && speechDuration > MAX_TURN_MS) ||
        (!state.hasSpeech && now - state.startedAt > NO_SPEECH_ROLLOVER_MS);

      if (shouldClose) {
        state.stopped = true;
        recorder.stop();
        return;
      }

      animationRef.current = window.requestAnimationFrame(tick);
    };

    animationRef.current = window.requestAnimationFrame(tick);
  }

  async function sendVoiceTurn(blob: Blob, sid: string) {
    setIsProcessingTurn(true);
    setStatus("Thinking");
    try {
      const result = await postVoiceTurn(blob, phoneNumber, sid);
      setTurn(result);
      if (result.transcript) {
        pushChat({ role: "user", text: result.transcript });
      }
      pushChat({ role: "agent", text: result.response_text, intent: result.intent });
      setStatus("Speaking");
      await playBulbulAudio(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Voice turn failed");
      setStatus("Listening");
    } finally {
      setIsProcessingTurn(false);
      if (roomRef.current) setStatus("Listening");
    }
  }

  async function playBulbulAudio(result: TurnResponse) {
    if (!result.audio_base64) return;
    responseAudioRef.current?.pause();
    const audio = new Audio(`data:${result.audio_mime_type};base64,${result.audio_base64}`);
    responseAudioRef.current = audio;
    await new Promise<void>((resolve) => {
      audio.onended = () => resolve();
      audio.onerror = () => resolve();
      audio.play().catch(() => resolve());
    });
  }

  function stopCurrentRecorder(discard = false) {
    cancelAnimationFrameIfNeeded();
    const recorder = recorderRef.current;
    recorderRef.current = null;
    if (recorder?.state === "recording") {
      speechStateRef.current.stopped = true;
      speechStateRef.current.discard = discard;
      recorder.stop();
    }
  }

  function cancelAnimationFrameIfNeeded() {
    if (animationRef.current) {
      window.cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    }
  }

  async function toggleRealtime() {
    if (isLive) {
      await stopRealtime();
      return;
    }
    await startRealtime();
  }

  async function runSafely(fn: () => Promise<void>) {
    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
      setStatus(isLive ? "Listening" : "Ready");
      setAgentState(isLive ? "LiveKit connected" : "Not connected");
    }
  }

  useEffect(() => {
    return () => {
      stopCurrentRecorder(true);
      stopLevelMeter();
      micStreamRef.current?.getTracks().forEach((t) => t.stop());
      roomRef.current?.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pulseScale = 1 + Math.min(voiceLevel * 8, 0.45);
  const pulseOpacity = isLive ? Math.min(0.2 + voiceLevel * 6, 0.7) : 0;

  const micUnavailable =
    typeof window !== "undefined" &&
    window.location.protocol === "http:" &&
    window.location.hostname !== "localhost" &&
    window.location.hostname !== "127.0.0.1";

  // Audio player for last turn (shown in chat bubble)
  const audioSrc = useMemo(() => {
    if (!turn?.audio_base64) return null;
    return `data:${turn.audio_mime_type};base64,${turn.audio_base64}`;
  }, [turn]);

  return (
    <main className="shell">
      {micUnavailable && (
        <div className="insecure-banner">
          Microphone access requires a secure origin. Open the app at{" "}
          <strong>http://localhost:3001</strong> in the browser on this machine, or serve over HTTPS.
        </div>
      )}
      <header className="topbar">
        <div>
          <p className="eyebrow">Module 1</p>
          <h1>Citizen Health AI</h1>
        </div>
        <div className="status-pill">
          {isProcessingTurn ? <Loader2 className="spin" size={16} /> : <Radio size={16} />}
          <span>{status}</span>
        </div>
      </header>

      <section className="workspace">
        {/* ── Left panel: citizen profile ───────────────────────── */}
        <aside className="profile-panel">
          <div className="panel-heading">
            <UserRound size={18} />
            <h2>Citizen</h2>
          </div>
          <label>
            Phone
            <input value={phoneNumber} onChange={(e) => setPhoneNumber(e.target.value)} />
          </label>
          <label>
            Name
            <input value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </label>
          <label>
            Language
            <select value={languageCode} onChange={(e) => setLanguageCode(e.target.value)}>
              <option value="ta-IN">Tamil</option>
              <option value="kn-IN">Kannada</option>
              <option value="en-IN">English</option>
            </select>
          </label>
          <label>
            District
            <input value={district} onChange={(e) => setDistrict(e.target.value)} />
          </label>
          <label>
            PHC
            <input value={phcName} onChange={(e) => setPhcName(e.target.value)} />
          </label>
          <button className="secondary-button" onClick={() => runSafely(saveCitizen)}>
            <ShieldCheck size={17} />
            Save
          </button>
        </aside>

        {/* ── Centre panel: voice + chat ────────────────────────── */}
        <section className="assistant-panel">
          <div className="intent-strip">
            {quickPrompts.map((prompt) => {
              const Icon = prompt.icon;
              return (
                <button
                  className="quick-chip"
                  key={prompt.label}
                  onClick={() => {
                    setText(prompt.text);
                    runSafely(() => submitText(prompt.text));
                  }}
                >
                  <Icon size={16} />
                  {prompt.label}
                </button>
              );
            })}
          </div>

          {/* Mic + language line */}
          <div className="voice-stage">
            <div className="mic-wrapper">
              <div
                className="pulse-ring"
                style={{
                  transform: `scale(${pulseScale})`,
                  opacity: pulseOpacity,
                  background: isLive ? "var(--coral)" : "var(--green)"
                }}
              />
              <button
                aria-label={isLive ? "End realtime voice session" : "Start realtime voice session"}
                className={isLive ? "record-button recording" : "record-button"}
                onClick={() => runSafely(toggleRealtime)}
              >
                {isLive ? <PhoneOff size={36} /> : <Mic size={40} />}
              </button>
            </div>
            <div className="stage-copy">
              <div className="language-line">
                <Languages size={17} />
                <span>{languageCode}</span>
              </div>
              <p className="stage-hint">
                {isLive
                  ? "Listening — speak naturally. Silence ends each turn automatically."
                  : "Tap the mic to start. The agent will introduce itself, then listen."}
              </p>
              {audioSrc && <audio controls src={audioSrc} />}
            </div>
          </div>

          {/* Conversation history */}
          {chatHistory.length > 0 && (
            <div className="chat-history">
              {chatHistory.map((entry, i) => (
                <div key={i} className={`chat-bubble chat-bubble--${entry.role}`}>
                  <div className="chat-avatar">
                    {entry.role === "agent" ? <Bot size={15} /> : <UserRound size={15} />}
                  </div>
                  <div className="chat-body">
                    {entry.intent && entry.role === "agent" && (
                      <span className="chat-intent">{entry.intent.replace(/_/g, " ")}</span>
                    )}
                    <p>{entry.text}</p>
                  </div>
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>
          )}

          {/* Text test row */}
          <div className="text-row">
            <input value={text} onChange={(e) => setText(e.target.value)} />
            <button className="primary-button" onClick={() => runSafely(() => submitText())}>
              <Send size={17} />
              Test
            </button>
          </div>

          {/* Latest turn metadata */}
          {turn && (
            <div className="result-grid">
              <div>
                <span>Transcript</span>
                <p>{turn.transcript}</p>
              </div>
              <div>
                <span>Intent</span>
                <p>{turn.intent}</p>
              </div>
              <div>
                <span>Interaction</span>
                <p>{turn.interaction_id || "local"}</p>
              </div>
              <div>
                <span>Database</span>
                <p>{turn.db_configured ? "Supabase" : "demo"}</p>
              </div>
            </div>
          )}

          {turn?.actions?.length ? (
            <pre className="actions">{JSON.stringify(turn.actions, null, 2)}</pre>
          ) : null}

          {error && <div className="error-box">{error}</div>}
        </section>

        {/* ── Right panel: realtime state ───────────────────────── */}
        <aside className="livekit-panel">
          <div className="panel-heading">
            <Activity size={18} />
            <h2>Realtime State</h2>
          </div>
          <div className="metric">
            <span>Transport</span>
            <strong>{agentState}</strong>
          </div>
          <div className="metric">
            <span>Room</span>
            <strong>{roomName || "None"}</strong>
          </div>
          <div className="metric">
            <span>Session</span>
            <strong>{sessionId ? sessionId.slice(0, 8) + "…" : "None"}</strong>
          </div>
          <div className="metric">
            <span>Turn mode</span>
            <strong>{isLive ? "Auto VAD" : "Idle"}</strong>
          </div>
          <div className="metric">
            <span>Voice</span>
            <strong>Bulbul TTS</strong>
          </div>
          {isLive && (
            <div className="metric">
              <span>Mic level</span>
              <div className="level-bar-track">
                <div
                  className="level-bar-fill"
                  style={{ width: `${Math.min(voiceLevel * 400, 100)}%` }}
                />
              </div>
            </div>
          )}
          <div className="remote-audio" ref={remoteAudioRef} />
          <div className="signal-row">
            <Volume2 size={16} />
            <span>{isLive ? "Microphone is publishing to LiveKit" : "Click mic to start"}</span>
          </div>
        </aside>
      </section>
    </main>
  );
}
