"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Room, RoomEvent, Track } from "livekit-client";
import {
  Baby,
  CalendarClock,
  Hospital,
  Loader2,
  MessageSquare,
  Mic,
  PhoneOff,
  Send,
  Settings,
  ShieldCheck,
  X
} from "lucide-react";

import {
  TurnResponse,
  createCitizen,
  createLiveKitToken,
  postTextTurn,
  postVoiceTurn,
  startSession
} from "@/lib/api";

// ── Types ──────────────────────────────────────────────────
type AppState = "idle" | "connecting" | "speaking-intro" | "listening" | "thinking" | "speaking";

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

// ── Quick prompts ──────────────────────────────────────────
const quickPrompts = [
  { icon: Hospital,     label: "PHC counter",  text: "Where is the registration counter?" },
  { icon: ShieldCheck,  label: "Eligibility",  text: "Am I eligible for Ayushman Bharat or CMCHIS?" },
  { icon: CalendarClock,label: "Appointment",  text: "Book a doctor appointment for tomorrow morning." },
  { icon: Baby,         label: "ANC reminder", text: "Set my maternal health reminder for ANC visit." }
];

// ── VAD constants ──────────────────────────────────────────
const SILENCE_MS            = 650;
const MIN_SPEECH_MS         = 250;
const MAX_TURN_MS           = 14000;
const NO_SPEECH_ROLLOVER_MS = 30000;
const VOICE_THRESHOLD       = 0.022;

// ── Codec probe ────────────────────────────────────────────
function getSupportedMimeType(): string {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
  for (const type of candidates) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(type)) return type;
  }
  return "";
}

// ── State → orb visual config ──────────────────────────────
function orbConfig(state: AppState, voiceLevel: number) {
  const scale = 1 + Math.min(voiceLevel * 8, 0.45);
  const ringOpacity = Math.min(0.15 + voiceLevel * 6, 0.8);

  switch (state) {
    case "listening":
      return {
        bg: "radial-gradient(circle at 38% 30%, #2a8f62 0%, #155038 45%, #072418 100%)",
        ambient: "#3ddc97",
        ring: `rgba(61,220,151,${ringOpacity})`,
        scale,
        haloBorder: "rgba(61,220,151,0.2)",
        dotColor: "#3ddc97",
        label: "Listening",
      };
    case "thinking":
      return {
        bg: "radial-gradient(circle at 38% 30%, #1a4a7a 0%, #0d2d54 45%, #060f1f 100%)",
        ambient: "#5b9cf6",
        ring: "rgba(91,156,246,0.3)",
        scale: 1,
        haloBorder: "rgba(91,156,246,0.2)",
        dotColor: "#5b9cf6",
        label: "Thinking",
      };
    case "speaking":
    case "speaking-intro":
      return {
        bg: "radial-gradient(circle at 38% 30%, #6e3ddc 0%, #3d1a8a 45%, #140a2e 100%)",
        ambient: "#a06ef5",
        ring: "rgba(160,110,245,0.35)",
        scale: 1.04 + Math.sin(Date.now() / 300) * 0.02,
        haloBorder: "rgba(160,110,245,0.2)",
        dotColor: "#a06ef5",
        label: "Speaking",
      };
    case "connecting":
      return {
        bg: "radial-gradient(circle at 38% 30%, #1e6e4c 0%, #0d3d2b 45%, #061a14 100%)",
        ambient: "#3ddc97",
        ring: "rgba(61,220,151,0.15)",
        scale: 1,
        haloBorder: "rgba(61,220,151,0.1)",
        dotColor: "#f4c154",
        label: "Connecting",
      };
    default:
      return {
        bg: "radial-gradient(circle at 38% 30%, #1e6e4c 0%, #0d3d2b 45%, #061a14 100%)",
        ambient: "#1f6e4c",
        ring: "rgba(61,220,151,0.12)",
        scale: 1,
        haloBorder: "rgba(61,220,151,0.08)",
        dotColor: "#3ddc97",
        label: "Tap to start",
      };
  }
}

// ── Component ──────────────────────────────────────────────
export function VoiceConsole() {
  // Citizen settings
  const [phoneNumber, setPhoneNumber] = useState("9000001001");
  const [fullName,    setFullName]    = useState("Meena Ravi");
  const [languageCode,setLanguageCode]= useState("ta-IN");
  const [district,    setDistrict]    = useState("Chennai");
  const [phcName,     setPhcName]     = useState("T Nagar Urban Primary Health Centre");
  const [text,        setText]        = useState("");

  // App state machine
  const [appState,          setAppState]          = useState<AppState>("idle");
  const [error,             setError]             = useState<string | null>(null);
  const [voiceLevel,        setVoiceLevel]        = useState(0);
  const [sessionId,         setSessionId]         = useState<string | null>(null);
  const [chatHistory,       setChatHistory]       = useState<ChatEntry[]>([]);
  const [latestAgentText,   setLatestAgentText]   = useState<string>("");
  const [latestAgentIntent, setLatestAgentIntent] = useState<string>("");
  const [showChat,          setShowChat]          = useState(false);
  const [showSettings,      setShowSettings]      = useState(false);
  const [turn,              setTurn]              = useState<TurnResponse | null>(null);

  // Refs
  const roomRef          = useRef<Room | null>(null);
  const micStreamRef     = useRef<MediaStream | null>(null);
  const recorderRef      = useRef<MediaRecorder | null>(null);
  const chunksRef        = useRef<Blob[]>([]);
  const animRef          = useRef<number | null>(null);
  const levelAnimRef     = useRef<number | null>(null);
  const analyserRef      = useRef<AnalyserNode | null>(null);
  const speechStateRef   = useRef<SpeechState>({ hasSpeech: false, lastVoiceAt: 0, startedAt: 0, stopped: false, discard: false });
  const responseAudioRef = useRef<HTMLAudioElement | null>(null);
  const remoteAudioRef   = useRef<HTMLDivElement | null>(null);
  const chatEndRef       = useRef<HTMLDivElement | null>(null);
  const isLive           = appState !== "idle" && appState !== "connecting";

  // Scroll chat to bottom
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [chatHistory]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopCurrentRecorder(true);
      stopLevelMeter();
      micStreamRef.current?.getTracks().forEach(t => t.stop());
      roomRef.current?.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Level meter ────────────────────────────────────────────
  const startLevelMeter = useCallback((analyser: AnalyserNode) => {
    analyserRef.current = analyser;
    const data = new Uint8Array(analyser.fftSize);
    const tick = () => {
      if (!analyserRef.current) return;
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (const v of data) { const c = (v - 128) / 128; sum += c * c; }
      const rms = Math.sqrt(sum / data.length);
      setVoiceLevel(prev => prev * 0.6 + rms * 0.4);
      levelAnimRef.current = requestAnimationFrame(tick);
    };
    levelAnimRef.current = requestAnimationFrame(tick);
  }, []);

  const stopLevelMeter = useCallback(() => {
    analyserRef.current = null;
    if (levelAnimRef.current) { cancelAnimationFrame(levelAnimRef.current); levelAnimRef.current = null; }
    setVoiceLevel(0);
  }, []);

  // ── Chat helpers ───────────────────────────────────────────
  function pushChat(entry: ChatEntry) {
    setChatHistory(prev => [...prev, entry]);
    if (entry.role === "agent") {
      setLatestAgentText(entry.text);
      if (entry.intent) setLatestAgentIntent(entry.intent);
    }
  }

  // ── Save citizen ───────────────────────────────────────────
  async function saveCitizen() {
    await createCitizen({
      phone_number: phoneNumber,
      full_name: fullName,
      preferred_language: languageCode.slice(0, 2),
      district_name: district,
      phc_name: phcName
    });
  }

  // ── Text turn ──────────────────────────────────────────────
  async function submitText(promptText = text) {
    if (!promptText.trim()) return;
    setAppState("thinking");
    setError(null);
    const result = await postTextTurn({ text: promptText, phone_number: phoneNumber, language_code: languageCode, session_id: sessionId ?? undefined });
    setTurn(result);
    pushChat({ role: "user", text: promptText });
    pushChat({ role: "agent", text: result.response_text, intent: result.intent });
    setAppState("speaking");
    await playAudio(result.audio_base64, result.audio_mime_type);
    setAppState(sessionId ? "listening" : "idle");
  }

  // ── Start / stop realtime ──────────────────────────────────
  async function startRealtime() {
    setError(null);
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setError("Microphone access unavailable. Open via http://localhost:3001 or HTTPS.");
      return;
    }

    setAppState("connecting");

    const session = await startSession({ phone_number: phoneNumber, language_code: languageCode });
    setSessionId(session.session_id);
    pushChat({ role: "agent", text: session.intro_text });

    // LiveKit
    const nextRoom    = `citizen-health-${Date.now()}`;
    const participant = phoneNumber || `citizen-${Date.now()}`;
    const token = await createLiveKitToken(nextRoom, participant, { phone_number: phoneNumber, language_code: languageCode, full_name: fullName });
    const room = new Room({ adaptiveStream: true, dynacast: true });
    roomRef.current = room;

    room
      .on(RoomEvent.Disconnected, () => { setAppState("idle"); stopLevelMeter(); })
      .on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind === Track.Kind.Audio && remoteAudioRef.current) {
          remoteAudioRef.current.appendChild(track.attach());
        }
      });

    await room.connect(token.url, token.token);

    // Intro audio
    setAppState("speaking-intro");
    await playAudio(session.audio_base64, session.audio_mime_type);

    // Open mic
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    micStreamRef.current = stream;
    const [audioTrack] = stream.getAudioTracks();
    await room.localParticipant.publishTrack(audioTrack, { name: "citizen-microphone", source: Track.Source.Microphone });

    setAppState("listening");
    startAutoTurnRecorder(stream, session.session_id);
  }

  async function stopRealtime() {
    stopCurrentRecorder(true);
    stopLevelMeter();
    responseAudioRef.current?.pause();
    responseAudioRef.current = null;
    micStreamRef.current?.getTracks().forEach(t => t.stop());
    micStreamRef.current = null;
    await roomRef.current?.disconnect();
    roomRef.current = null;
    setSessionId(null);
    setChatHistory([]);
    setLatestAgentText("");
    setLatestAgentIntent("");
    setTurn(null);
    setAppState("idle");
  }

  // ── VAD recorder ──────────────────────────────────────────
  function startAutoTurnRecorder(stream: MediaStream, sid: string) {
    if (!roomRef.current) return;
    stopCurrentRecorder();
    chunksRef.current = [];
    speechStateRef.current = { hasSpeech: false, lastVoiceAt: 0, startedAt: performance.now(), stopped: false, discard: false };

    const mimeType = getSupportedMimeType();
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
    recorderRef.current = recorder;

    const audioCtx = new AudioContext();
    const analyser = audioCtx.createAnalyser();
    audioCtx.createMediaStreamSource(stream).connect(analyser);
    startLevelMeter(analyser);

    recorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };

    recorder.onstop = async () => {
      cancelAnimFrames();
      stopLevelMeter();
      await audioCtx.close();

      const state = speechStateRef.current;
      const blob  = new Blob(chunksRef.current, { type: "audio/webm" });
      chunksRef.current = [];

      if (state.discard || !roomRef.current || !state.hasSpeech || blob.size < 900) {
        if (roomRef.current) window.setTimeout(() => startAutoTurnRecorder(stream, sid), 150);
        return;
      }
      await sendVoiceTurn(blob, sid);
      if (roomRef.current) window.setTimeout(() => startAutoTurnRecorder(stream, sid), 150);
    };

    recorder.start(200);
    monitorSpeech(analyser, stream, sid);
  }

  function monitorSpeech(analyser: AnalyserNode, stream: MediaStream, sid: string) {
    const data = new Uint8Array(analyser.fftSize);
    const tick = () => {
      const recorder = recorderRef.current;
      const state    = speechStateRef.current;
      if (!recorder || recorder.state !== "recording" || state.stopped) return;

      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (const v of data) { const c = (v - 128) / 128; sum += c * c; }
      const rms = Math.sqrt(sum / data.length);
      const now = performance.now();

      if (rms > VOICE_THRESHOLD) {
        if (!state.hasSpeech) state.startedAt = now;
        state.hasSpeech  = true;
        state.lastVoiceAt = now;
        setAppState("listening");
      }

      const speechDur  = now - state.startedAt;
      const silenceDur = now - state.lastVoiceAt;
      const close =
        (state.hasSpeech && speechDur > MIN_SPEECH_MS && silenceDur > SILENCE_MS) ||
        (state.hasSpeech && speechDur > MAX_TURN_MS) ||
        (!state.hasSpeech && speechDur > NO_SPEECH_ROLLOVER_MS);

      if (close) { state.stopped = true; recorder.stop(); return; }
      animRef.current = window.requestAnimationFrame(tick);
    };
    animRef.current = window.requestAnimationFrame(tick);
    void stream; void sid; // used by onstop closure
  }

  async function sendVoiceTurn(blob: Blob, sid: string) {
    setAppState("thinking");
    try {
      const result = await postVoiceTurn(blob, phoneNumber, sid);
      setTurn(result);
      if (result.transcript) pushChat({ role: "user", text: result.transcript });
      pushChat({ role: "agent", text: result.response_text, intent: result.intent });
      setAppState("speaking");
      await playAudio(result.audio_base64, result.audio_mime_type);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Voice turn failed");
    } finally {
      if (roomRef.current) setAppState("listening");
    }
  }

  // ── Audio playback ─────────────────────────────────────────
  async function playAudio(base64: string | null, mime: string) {
    if (!base64) return;
    responseAudioRef.current?.pause();
    const audio = new Audio(`data:${mime};base64,${base64}`);
    responseAudioRef.current = audio;
    await new Promise<void>(resolve => {
      audio.onended = () => resolve();
      audio.onerror = () => resolve();
      audio.play().catch(() => resolve());
    });
  }

  // ── Recorder helpers ───────────────────────────────────────
  function stopCurrentRecorder(discard = false) {
    cancelAnimFrames();
    const r = recorderRef.current;
    recorderRef.current = null;
    if (r?.state === "recording") {
      speechStateRef.current.stopped = true;
      speechStateRef.current.discard = discard;
      r.stop();
    }
  }

  function cancelAnimFrames() {
    if (animRef.current)      { window.cancelAnimationFrame(animRef.current);      animRef.current = null; }
    if (levelAnimRef.current) { cancelAnimationFrame(levelAnimRef.current); levelAnimRef.current = null; }
  }

  async function runSafely(fn: () => Promise<void>) {
    try { await fn(); }
    catch (err) { setError(err instanceof Error ? err.message : "Request failed"); setAppState("idle"); }
  }

  // ── Orb visuals ────────────────────────────────────────────
  const orb = orbConfig(appState, voiceLevel);

  const micUnavailable =
    typeof window !== "undefined" &&
    window.location.protocol === "http:" &&
    window.location.hostname !== "localhost" &&
    window.location.hostname !== "127.0.0.1";

  // Wave bars driven by voiceLevel when agent speaks
  const waveBars = Array.from({ length: 7 }, (_, i) => {
    const isSpeaking = appState === "speaking" || appState === "speaking-intro";
    const h = isSpeaking
      ? 4 + Math.abs(Math.sin((Date.now() / 200) + i * 0.8)) * 20
      : appState === "listening"
        ? 4 + voiceLevel * 120 * Math.abs(Math.sin(i * 1.2))
        : 4;
    return h;
  });

  // Force re-render while speaking/listening to animate waveform
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (appState === "speaking" || appState === "speaking-intro" || appState === "listening") {
      const id = window.setInterval(() => setTick(t => t + 1), 60);
      return () => window.clearInterval(id);
    }
  }, [appState]);
  void tick;

  const latestVisible = latestAgentText.length > 0;

  return (
    <div className="gl-shell">
      {/* Insecure origin banner */}
      {micUnavailable && (
        <div className="gl-insecure">
          Mic requires secure origin — open at <strong>http://localhost:3001</strong> or via HTTPS.
        </div>
      )}

      {/* Top bar */}
      <header className="gl-topbar">
        <div className="gl-wordmark">
          <div className="gl-wordmark-dot" />
          <h1>Citizen Health AI</h1>
        </div>
        <div className="gl-topbar-actions">
          {chatHistory.length > 0 && (
            <button className="gl-icon-btn" aria-label="History" onClick={() => setShowChat(v => !v)}>
              <MessageSquare size={18} />
            </button>
          )}
          <button className="gl-icon-btn" aria-label="Settings" onClick={() => setShowSettings(v => !v)}>
            <Settings size={18} />
          </button>
        </div>
      </header>

      {/* Center stage */}
      <main className="gl-stage">
        {/* Ambient glow */}
        <div className="gl-ambient" style={{ background: orb.ambient }} />

        {/* Orb */}
        <div className="gl-orb-wrapper">
          <div
            className="gl-orb"
            role="button"
            aria-label={isLive ? "End session" : "Start session"}
            onClick={() => runSafely(isLive ? stopRealtime : startRealtime)}
            style={{ transform: `scale(${orb.scale})` }}
          >
            <div className="gl-orb-core" style={{ background: orb.bg }} />
            <div className="gl-orb-shine" />
            <div className="gl-orb-ring" style={{ borderColor: orb.ring }} />
            <div className="gl-halo" style={{ borderColor: orb.haloBorder }} />

            {/* Center icon */}
            <div className="gl-orb-icon">
              {appState === "connecting" || appState === "thinking" ? (
                <Loader2 size={40} color="rgba(255,255,255,0.6)" className="spin" />
              ) : isLive ? (
                <PhoneOff size={34} color="rgba(255,255,255,0.5)" />
              ) : (
                <Mic size={40} color="rgba(255,255,255,0.7)" />
              )}
            </div>
          </div>

          {/* Status label */}
          <div className="gl-status-label">
            <div className="gl-status-dot" style={{ background: orb.dotColor }} />
            {orb.label}
          </div>

          {/* Waveform */}
          <div className="gl-wave">
            {waveBars.map((h, i) => (
              <div key={i} className="gl-wave-bar" style={{ height: `${h}px`, opacity: isLive ? 0.7 : 0.2 }} />
            ))}
          </div>
        </div>

        {/* Latest agent transcript */}
        <div className="gl-transcript">
          <div className={`gl-transcript-text ${latestVisible ? "visible" : ""}`}>
            {latestAgentIntent && (
              <span className="gl-transcript-intent">{latestAgentIntent.replace(/_/g, " ")}</span>
            )}
            {latestAgentText}
          </div>
        </div>

        {error && <div className="gl-error">{error}</div>}
      </main>

      {/* Bottom toolbar */}
      <footer className="gl-bottom">
        {/* Quick chips — hidden while live */}
        {!isLive && (
          <div className="gl-chips">
            {quickPrompts.map(p => {
              const Icon = p.icon;
              return (
                <button key={p.label} className="gl-chip" onClick={() => { setText(p.text); runSafely(() => submitText(p.text)); }}>
                  <Icon size={14} />
                  {p.label}
                </button>
              );
            })}
          </div>
        )}

        {/* Text input */}
        <div className="gl-text-row">
          <input
            className="gl-text-input"
            placeholder="Type a message…"
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") runSafely(() => submitText()); }}
          />
          <button
            className="gl-send-btn"
            disabled={!text.trim() || appState === "thinking" || appState === "connecting"}
            onClick={() => runSafely(() => submitText())}
            aria-label="Send"
          >
            {appState === "thinking" ? <Loader2 size={16} className="spin" /> : <Send size={16} />}
          </button>
        </div>

        {/* End call button while live */}
        {isLive && (
          <button className="gl-end-btn" onClick={() => runSafely(stopRealtime)}>
            <PhoneOff size={18} /> End session
          </button>
        )}
      </footer>

      {/* Hidden LiveKit remote audio container */}
      <div ref={remoteAudioRef} style={{ display: "none" }} />

      {/* ── Settings drawer ───────────────────────────────── */}
      <div className={`gl-settings-overlay ${showSettings ? "open" : ""}`} onClick={e => { if (e.target === e.currentTarget) setShowSettings(false); }}>
        <div className="gl-settings-drawer">
          <div className="gl-settings-title">
            <span>Settings</span>
            <button className="gl-icon-btn" onClick={() => setShowSettings(false)}><X size={16} /></button>
          </div>
          <label>
            Phone
            <input value={phoneNumber} onChange={e => setPhoneNumber(e.target.value)} />
          </label>
          <label>
            Name
            <input value={fullName} onChange={e => setFullName(e.target.value)} />
          </label>
          <label>
            Language
            <select value={languageCode} onChange={e => setLanguageCode(e.target.value)}>
              <option value="en-IN">English</option>
              <option value="hi-IN">Hindi / Hinglish</option>
              <option value="ta-IN">Tamil</option>
              <option value="kn-IN">Kannada</option>
            </select>
          </label>
          <label>
            District
            <input value={district} onChange={e => setDistrict(e.target.value)} />
          </label>
          <label>
            PHC
            <input value={phcName} onChange={e => setPhcName(e.target.value)} />
          </label>
          <button className="gl-save-btn" onClick={() => runSafely(saveCitizen)}>
            <ShieldCheck size={17} /> Save citizen
          </button>
          {turn && (
            <>
              <hr style={{ borderColor: "var(--line)", margin: "4px 0" }} />
              <small style={{ color: "var(--muted)", fontSize: "0.75rem" }}>
                Session: {sessionId ? sessionId.slice(0, 8) + "…" : "None"}<br />
                Intent: {turn.intent}<br />
                DB: {turn.db_configured ? "Supabase" : "demo"}
              </small>
            </>
          )}
        </div>
      </div>

      {/* ── Chat history panel ────────────────────────────── */}
      <div className={`gl-chat-panel ${showChat ? "open" : ""}`}>
        <div className="gl-chat-header">
          <span>Conversation</span>
          <button className="gl-icon-btn" onClick={() => setShowChat(false)}><X size={16} /></button>
        </div>
        <div className="gl-chat-messages">
          {chatHistory.map((entry, i) => (
            <div key={i} className={`gl-msg gl-msg--${entry.role}`}>
              {entry.intent && entry.role === "agent" && (
                <span className="gl-msg-intent">{entry.intent.replace(/_/g, " ")}</span>
              )}
              <div className="gl-msg-bubble">{entry.text}</div>
            </div>
          ))}
          <div ref={chatEndRef} />
        </div>
      </div>
    </div>
  );
}
