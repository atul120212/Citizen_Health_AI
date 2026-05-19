"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import {
  BarChart3, Brain, PhoneOff, Mic, Loader2, X,
  CheckCircle2, AlertTriangle, User, Calendar, Shield, Navigation, Radio, Stethoscope,
} from "lucide-react";
import { Room, RoomEvent, Track, ConnectionState, RemoteParticipant, RemoteTrack } from "livekit-client";
import {
  TurnResponse, SessionSummary,
  startSession, postVoiceTurn, fetchSessionSummary, createLiveKitToken,
} from "@/lib/api";
import { useNetworkStatus } from "@/lib/network";

// ── Constants ──────────────────────────────────────────────
const SILENCE_MS = 700;
const MIN_SPEECH_MS = 300;
const MAX_TURN_MS = 15000;
const NO_SPEECH_ROLLOVER_MS = 25000;
const VOICE_THRESHOLD = 0.02;
const MIN_AUDIO_BYTES = 2200;
const FALLBACK_CHAT_COOLDOWN_MS = 4000;

type AppState =
  | "idle" | "listening-wake" | "connecting" | "speaking-intro"
  | "awaiting-id" | "verifying" | "listening" | "thinking" | "speaking" | "ended";

type SpeechState = {
  hasSpeech: boolean; lastVoiceAt: number;
  startedAt: number; stopped: boolean; discard: boolean;
};

type ChatEntry = { role: "agent" | "user"; text: string; intent?: string; timestamp: number };

type CitizenInfo = { full_name?: string; phc_name?: string; ayushman_eligible?: boolean };

type LKStatus = "disconnected" | "connecting" | "connected" | "failed";

function getSupportedMimeType() {
  for (const t of ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"]) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(t)) return t;
  }
  return "";
}

const WAKE_WORDS = [
  { words: ["vanakkam", "one come", "வணக்கம்"], lang: "ta-IN" },
  { words: ["namaskara", "ನಮಸ್ಕಾರ", "namaskaar"], lang: "kn-IN" },
  { words: ["namaste", "namaskar", "नमस्ते", "नमस्कार"], lang: "hi-IN" },
  { words: ["pranam", "प्रणाम"], lang: "bho-IN" },
  { words: ["hello", "hi", "hey", "good morning", "good afternoon"], lang: "en-IN" },
];

function detectWakeWord(transcript: string): string | null {
  const lower = transcript.toLowerCase();
  for (const group of WAKE_WORDS) {
    if (group.words.some(w => lower.includes(w))) return group.lang;
  }
  return null;
}

function isGarbageTranscript(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed) return true;
  const words = trimmed.split(/\s+/);
  if (words.length >= 3) {
    const unique = new Set(words.map(w => w.toLowerCase()));
    if (unique.size <= 2) return true;
  }
  return false;
}

function orbStyle(state: AppState, level: number) {
  const scale = 1 + Math.min(level * 8, 0.5);
  switch (state) {
    case "listening": case "awaiting-id":
      return { grad: "radial-gradient(circle at 38% 30%, #1a6b45 0%, #0d3d26 50%, #061a10 100%)", glow: "#3ddc97", ring: `rgba(61,220,151,${0.15 + level * 5})`, scale, label: state === "awaiting-id" ? "Say your ID…" : "Listening" };
    case "thinking": case "verifying":
      return { grad: "radial-gradient(circle at 38% 30%, #1a3a7a 0%, #0d2050 50%, #06091e 100%)", glow: "#5b9cf6", ring: "rgba(91,156,246,0.3)", scale: 1, label: state === "verifying" ? "Verifying…" : "Thinking…" };
    case "speaking": case "speaking-intro":
      return { grad: "radial-gradient(circle at 38% 30%, #5a1a9a 0%, #32076a 50%, #110024 100%)", glow: "#a06ef5", ring: "rgba(160,110,245,0.35)", scale: 1.04, label: "Speaking" };
    case "connecting":
      return { grad: "radial-gradient(circle at 38% 30%, #1e3a4c 0%, #0d1e2b 50%, #040c14 100%)", glow: "#5b9cf6", ring: "rgba(91,156,246,0.2)", scale: 1, label: "Connecting…" };
    case "ended":
      return { grad: "radial-gradient(circle at 38% 30%, #2a1010 0%, #1a0808 50%, #0a0303 100%)", glow: "#ff6b4a", ring: "rgba(255,107,74,0.2)", scale: 1, label: "Call ended" };
    case "listening-wake":
      return { grad: "radial-gradient(circle at 38% 30%, #0d2a1c 0%, #071510 50%, #030a06 100%)", glow: "#1f6e4c", ring: "rgba(61,220,151,0.08)", scale: 1, label: 'Say "Hello" to begin' };
    default:
      return { grad: "radial-gradient(circle at 38% 30%, #0d2a1c 0%, #071510 50%, #030a06 100%)", glow: "#1f6e4c", ring: "rgba(61,220,151,0.06)", scale: 1, label: 'Say "Hello" to begin' };
  }
}

const INTENT_ICONS: Record<string, typeof CheckCircle2> = {
  verify_identity: User,
  appointment_booking: Calendar,
  eligibility_check: Shield,
  hospital_navigation: Navigation,
  emergency: AlertTriangle,
  session_end: CheckCircle2,
};

const LK_STATUS_COLORS: Record<LKStatus, string> = {
  disconnected: "#6a7c76",
  connecting: "#f4c154",
  connected: "#3ddc97",
  failed: "#ff6b4a",
};

export function VoiceConsole() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const { quality } = useNetworkStatus();
  const isLowBandwidth = quality === "poor";

  const [appState, setAppState] = useState<AppState>("idle");
  const [voiceLevel, setVoiceLevel] = useState(0);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [chat, setChat] = useState<ChatEntry[]>([]);
  const [latestText, setLatestText] = useState("");
  const [latestIntent, setLatestIntent] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [citizen, setCitizen] = useState<CitizenInfo | null>(null);
  const [verificationState, setVerificationState] = useState<"pending" | "verified" | "guest">("pending");
  const [summary, setSummary] = useState<SessionSummary | null>(null);
  const [tick, setTick] = useState(0);
  const [lkStatus, setLkStatus] = useState<LKStatus>("disconnected");
  const [lkRoom, setLkRoom] = useState<string | null>(null);
  const [lkAgentActive, setLkAgentActive] = useState(false);

  const micStreamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const animRef = useRef<number | null>(null);
  const levelAnimRef = useRef<number | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const speechStateRef = useRef<SpeechState>({ hasSpeech: false, lastVoiceAt: 0, startedAt: 0, stopped: false, discard: false });
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const lkRoomRef = useRef<Room | null>(null);
  const agentModeRef = useRef(false);
  const agentAudioRef = useRef<HTMLAudioElement | null>(null);
  const agentSpeakingRef = useRef(false);
  const turnInFlightRef = useRef(false);
  const lastFallbackChatRef = useRef(0);
  const languageRef = useRef("en-IN");
  const isLive = !["idle", "listening-wake", "ended"].includes(appState);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [chat]);

  useEffect(() => {
    if (["speaking", "speaking-intro", "listening", "awaiting-id"].includes(appState)) {
      const id = setInterval(() => setTick(t => t + 1), 60);
      return () => clearInterval(id);
    }
  }, [appState]);
  void tick;

  useEffect(() => () => { cleanup(); }, []);

  // ── Level meter ────────────────────────────────────────────
  const startLevelMeter = useCallback((analyser: AnalyserNode) => {
    analyserRef.current = analyser;
    const data = new Uint8Array(analyser.fftSize);
    const tick = () => {
      if (!analyserRef.current) return;
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (const v of data) { const c = (v - 128) / 128; sum += c * c; }
      setVoiceLevel(p => p * 0.6 + Math.sqrt(sum / data.length) * 0.4);
      levelAnimRef.current = requestAnimationFrame(tick);
    };
    levelAnimRef.current = requestAnimationFrame(tick);
  }, []);

  const stopLevelMeter = useCallback(() => {
    analyserRef.current = null;
    if (levelAnimRef.current) { cancelAnimationFrame(levelAnimRef.current); levelAnimRef.current = null; }
    setVoiceLevel(0);
  }, []);

  function pushChat(entry: ChatEntry) {
    setChat(prev => [...prev, entry]);
    if (entry.role === "agent") { setLatestText(entry.text); if (entry.intent) setLatestIntent(entry.intent); }
  }

  async function playAudio(b64: string | null, mime: string) {
    if (!b64) return;
    agentSpeakingRef.current = true;
    stopRestVad();
    audioRef.current?.pause();
    const audio = new Audio(`data:${mime};base64,${b64}`);
    audioRef.current = audio;
    try {
      await new Promise<void>(r => {
        audio.onended = () => r();
        audio.onerror = () => r();
        audio.play().catch(() => r());
      });
    } finally {
      agentSpeakingRef.current = false;
    }
  }

  function stopRestVad() {
    speechStateRef.current.stopped = true;
    speechStateRef.current.discard = true;
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      try { recorderRef.current.stop(); } catch { /* ignore */ }
    }
    recorderRef.current = null;
    if (animRef.current) {
      cancelAnimationFrame(animRef.current);
      animRef.current = null;
    }
  }

  function cleanup() {
    if (animRef.current) { cancelAnimationFrame(animRef.current); animRef.current = null; }
    stopLevelMeter();
    recorderRef.current?.stop();
    recorderRef.current = null;
    audioRef.current?.pause();
    audioRef.current = null;
    micStreamRef.current?.getTracks().forEach(t => t.stop());
    micStreamRef.current = null;
    if (agentAudioRef.current) {
      agentAudioRef.current.pause();
      agentAudioRef.current.srcObject = null;
      agentAudioRef.current = null;
    }
    if (lkRoomRef.current) {
      lkRoomRef.current.disconnect().catch(() => {});
      lkRoomRef.current = null;
    }
    agentModeRef.current = false;
    setLkAgentActive(false);
    setLkStatus("disconnected");
    setLkRoom(null);
  }

  function attachAgentAudio(track: RemoteTrack, participant: RemoteParticipant) {
    if (track.kind !== Track.Kind.Audio) return;
    if (participant.identity === lkRoomRef.current?.localParticipant.identity) return;

    agentModeRef.current = true;
    setLkAgentActive(true);
    stopRestVad();

    if (agentAudioRef.current) {
      agentAudioRef.current.pause();
      track.detach(agentAudioRef.current);
    }
    const el = track.attach() as HTMLAudioElement;
    el.autoplay = true;
    el.volume = 1;
    agentAudioRef.current = el;
    el.play().catch(() => {});

    setAppState(prev =>
      prev === "connecting" || prev === "speaking-intro" ? prev : prev === "awaiting-id" ? "awaiting-id" : "listening"
    );
  }

  function waitForLiveKitAgent(room: Room, timeoutMs: number): Promise<boolean> {
    const hasAgent = () =>
      Array.from(room.remoteParticipants.values()).some(p =>
        p.audioTrackPublications.size > 0 || !p.identity.startsWith("user-")
      );

    if (hasAgent()) return Promise.resolve(true);

    return new Promise(resolve => {
      const timer = window.setTimeout(() => resolve(hasAgent()), timeoutMs);

      const onParticipant = (p: RemoteParticipant) => {
        if (!p.identity.startsWith("user-")) {
          window.clearTimeout(timer);
          room.off(RoomEvent.ParticipantConnected, onParticipant);
          room.off(RoomEvent.TrackSubscribed, onTrack);
          resolve(true);
        }
      };

      const onTrack = (track: RemoteTrack, _pub: unknown, participant: RemoteParticipant) => {
        if (track.kind === Track.Kind.Audio && participant.identity !== room.localParticipant.identity) {
          attachAgentAudio(track, participant);
          window.clearTimeout(timer);
          room.off(RoomEvent.ParticipantConnected, onParticipant);
          room.off(RoomEvent.TrackSubscribed, onTrack);
          resolve(true);
        }
      };

      room.on(RoomEvent.ParticipantConnected, onParticipant);
      room.on(RoomEvent.TrackSubscribed, onTrack);
    });
  }

  // ── LiveKit room setup ─────────────────────────────────────
  async function connectLiveKit(
    roomName: string,
    participantName: string,
    sessionId: string,
    languageCode: string,
  ): Promise<{ stream: MediaStream | null; agentJoined: boolean }> {
    setLkStatus("connecting");
    try {
      const { token, url } = await createLiveKitToken(roomName, participantName, {
        session_id: sessionId,
        language_code: languageCode,
        room_name: roomName,
      });

      const room = new Room({
        audioCaptureDefaults: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
        adaptiveStream: true,
        dynacast: true,
      });

      lkRoomRef.current = room;

      room.on(RoomEvent.Disconnected, () => {
        setLkStatus("disconnected");
        setLkRoom(null);
        agentModeRef.current = false;
        setLkAgentActive(false);
      });
      room.on(RoomEvent.ConnectionStateChanged, (state: ConnectionState) => {
        if (state === ConnectionState.Connected) setLkStatus("connected");
        else if (state === ConnectionState.Connecting) setLkStatus("connecting");
        else if (state === ConnectionState.Disconnected) {
          setLkStatus("disconnected");
          setLkRoom(null);
          agentModeRef.current = false;
          setLkAgentActive(false);
        }
      });
      room.on(RoomEvent.Reconnecting, () => setLkStatus("connecting"));
      room.on(RoomEvent.Reconnected, () => setLkStatus("connected"));
      room.on(RoomEvent.TrackSubscribed, (track, _pub, participant) => {
        attachAgentAudio(track, participant);
      });
      room.on(RoomEvent.ParticipantConnected, participant => {
        if (participant.identity !== room.localParticipant.identity) {
          setLkAgentActive(true);
        }
      });

      await room.connect(url, token);
      await room.localParticipant.setMicrophoneEnabled(true);

      const pub = room.localParticipant.getTrackPublication(Track.Source.Microphone);
      const mst = pub?.audioTrack?.mediaStreamTrack;

      setLkStatus("connected");
      setLkRoom(roomName);

      const agentJoined = await waitForLiveKitAgent(room, 8000);
      if (agentJoined) agentModeRef.current = true;

      return {
        stream: mst ? new MediaStream([mst]) : null,
        agentJoined,
      };
    } catch (err) {
      console.warn("[LiveKit] Connection failed:", err);
      setLkStatus("failed");
      return { stream: null, agentJoined: false };
    }
  }

  async function disconnectLiveKitRoom() {
    if (lkRoomRef.current) {
      try { await lkRoomRef.current.disconnect(); } catch { /* ignore */ }
      lkRoomRef.current = null;
    }
    setLkStatus("disconnected");
    setLkRoom(null);
    setLkAgentActive(false);
    agentModeRef.current = false;
  }

  // ── Wake word listener ─────────────────────────────────────
  useEffect(() => {
    if (!mounted || isLive) return;
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) { setAppState("idle"); return; }
    setAppState("listening-wake");
    const rec = new SR();
    rec.continuous = true;
    rec.interimResults = false;
    rec.lang = "en-IN";
    let active = true;

    rec.onresult = (e: any) => {
      if (!active) return;
      const t = e.results[e.results.length - 1][0].transcript;
      const lang = detectWakeWord(t);
      if (lang) { active = false; rec.stop(); runSafely(() => beginSession(lang)); }
    };
    rec.onend = () => { if (active && !isLive) { try { rec.start(); } catch {} } };
    try { rec.start(); } catch {}
    return () => { active = false; try { rec.stop(); } catch {} setAppState("idle"); };
  }, [mounted, isLive]);

  // ── Start session ─────────────────────────────────────────
  async function beginSession(lang: string) {
    setError(null);
    setChat([]);
    setSummary(null);
    setCitizen(null);
    setVerificationState("pending");
    setLatestText("");
    setLatestIntent("");
    setAppState("connecting");

    languageRef.current = lang;
    const session = await startSession({ language_code: lang });
    setSessionId(session.session_id);
    pushChat({ role: "agent", text: session.intro_text, intent: "verify_identity", timestamp: Date.now() });

    setAppState("speaking-intro");
    await playAudio(session.audio_base64, session.audio_mime_type);

    // Connect to LiveKit room (dispatches realtime agent); fall back to direct mic + REST if needed
    const roomName = `aarogya-${session.session_id.slice(0, 8)}`;
    const participantName = `user-${session.session_id.slice(0, 8)}`;
    const { agentJoined } = (isLowBandwidth) 
      ? { agentJoined: false } 
      : await connectLiveKit(
          roomName,
          participantName,
          session.session_id,
          lang,
        );

    // Always use a dedicated browser mic for REST/VAD — never share path with LiveKit agent audio
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });

    setLkAgentActive(agentJoined);
    agentModeRef.current = agentJoined;

    if (agentJoined) {
      stopRestVad();
      stream.getTracks().forEach(t => t.stop());
      const lkTrack = lkRoomRef.current?.localParticipant.getTrackPublication(Track.Source.Microphone)
        ?.audioTrack?.mediaStreamTrack;
      micStreamRef.current = lkTrack ? new MediaStream([lkTrack]) : null;
      if (micStreamRef.current) startLevelMeterFromStream(micStreamRef.current);
      setAppState("awaiting-id");
    } else {
      await disconnectLiveKitRoom();
      micStreamRef.current = stream;
      setAppState("awaiting-id");
    }
  }

  // ── Auto-start session on page load ─────────────────────────
  useEffect(() => {
    if (mounted) {
      runSafely(() => beginSession("en-IN"));
    }
  }, [mounted]);


  function startLevelMeterFromStream(stream: MediaStream) {
    const audioCtx = new AudioContext();
    const analyser = audioCtx.createAnalyser();
    audioCtx.createMediaStreamSource(stream).connect(analyser);
    startLevelMeter(analyser);
  }

  // ── End session ───────────────────────────────────────────
  async function endSession() {
    const sid = sessionId;
    cleanup();
    setAppState("ended");
    if (sid) {
      try {
        const s = await fetchSessionSummary(sid);
        setSummary(s);
      } catch {}
    }
    setSessionId(null);
  }

  // ── VAD recorder ──────────────────────────────────────────
  function startVADRecorder(stream: MediaStream, sid: string) {
    if (agentModeRef.current) return;
    if (recorderRef.current) { recorderRef.current.stop(); recorderRef.current = null; }
    chunksRef.current = [];
    speechStateRef.current = { hasSpeech: false, lastVoiceAt: 0, startedAt: performance.now(), stopped: false, discard: false };

    const mime = getSupportedMimeType();
    const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : {});
    recorderRef.current = recorder;

    const audioCtx = new AudioContext();
    const analyser = audioCtx.createAnalyser();
    audioCtx.createMediaStreamSource(stream).connect(analyser);
    startLevelMeter(analyser);

    recorder.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data); };
    recorder.onstop = async () => {
      if (animRef.current) { cancelAnimationFrame(animRef.current); animRef.current = null; }
      stopLevelMeter();
      await audioCtx.close();
      const state = speechStateRef.current;
      const blob = new Blob(chunksRef.current, { type: "audio/webm" });
      chunksRef.current = [];
      if (
        agentModeRef.current ||
        state.discard ||
        !state.hasSpeech ||
        blob.size < MIN_AUDIO_BYTES ||
        !micStreamRef.current
      ) {
        if (micStreamRef.current && !agentModeRef.current) {
          setTimeout(() => startVADRecorder(stream, sid), 150);
        }
        return;
      }
      await handleVoiceTurn(blob, sid, stream);
    };

    recorder.start(200);
    monitorSpeech(analyser, stream, sid);
  }

  function monitorSpeech(analyser: AnalyserNode, stream: MediaStream, sid: string) {
    const data = new Uint8Array(analyser.fftSize);
    const tick = () => {
      const r = recorderRef.current;
      const s = speechStateRef.current;
      if (!r || r.state !== "recording" || s.stopped) return;
      if (agentModeRef.current || agentSpeakingRef.current || turnInFlightRef.current) {
        animRef.current = requestAnimationFrame(tick);
        return;
      }
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (const v of data) { const c = (v - 128) / 128; sum += c * c; }
      const rms = Math.sqrt(sum / data.length);
      const now = performance.now();
      if (rms > VOICE_THRESHOLD) {
        if (!s.hasSpeech) s.startedAt = now;
        s.hasSpeech = true; s.lastVoiceAt = now;
        setAppState(prev => prev === "awaiting-id" ? "awaiting-id" : "listening");
      }
      const dur = now - s.startedAt;
      const adaptiveSilence = isLowBandwidth ? 1500 : SILENCE_MS;
      const sil = now - s.lastVoiceAt;
      if ((s.hasSpeech && dur > MIN_SPEECH_MS && sil > adaptiveSilence) || (s.hasSpeech && dur > MAX_TURN_MS) || (!s.hasSpeech && dur > NO_SPEECH_ROLLOVER_MS)) {
        s.stopped = true; r.stop(); return;
      }
      animRef.current = requestAnimationFrame(tick);
    };
    animRef.current = requestAnimationFrame(tick);
  }

  async function handleVoiceTurn(blob: Blob, sid: string, stream: MediaStream) {
    if (agentModeRef.current || turnInFlightRef.current) return;

    turnInFlightRef.current = true;
    setAppState("thinking");
    try {
      const result = await postVoiceTurn(blob, undefined, sid);

      const silentFallback =
        result.intent === "fallback" &&
        (!result.transcript?.trim() || isGarbageTranscript(result.transcript));

      if (silentFallback) {
        const now = Date.now();
        if (now - lastFallbackChatRef.current > FALLBACK_CHAT_COOLDOWN_MS) {
          lastFallbackChatRef.current = now;
          pushChat({ role: "agent", text: result.response_text, intent: result.intent, timestamp: now });
          setLatestText(result.response_text);
          setLatestIntent(result.intent);
          await playAudio(result.audio_base64, result.audio_mime_type);
        }
        const nextState =
          verificationState === "pending" ? "awaiting-id" : "listening";
        setAppState(nextState);
        if (micStreamRef.current && !agentModeRef.current) {
          setTimeout(() => startVADRecorder(stream, sid), 200);
        }
        return;
      }

      if (result.intent === "verify_identity" || result.intent === "verification_failed") {
        const verAction = result.actions.find((a: any) => a.type === "citizen_verified");
        const guestAction = result.actions.find((a: any) => a.type === "guest_mode");
        if (verAction) {
          setVerificationState("verified");
          setCitizen({ full_name: verAction.citizen_name as string, phc_name: verAction.phc as string, ayushman_eligible: verAction.ayushman_eligible as boolean });
        } else if (guestAction) {
          setVerificationState("guest");
        }
      }

      if (result.transcript?.trim() && !isGarbageTranscript(result.transcript)) {
        pushChat({ role: "user", text: result.transcript, timestamp: Date.now() });
      }
      pushChat({ role: "agent", text: result.response_text, intent: result.intent, timestamp: Date.now() });

      if (result.intent === "session_end") {
        setAppState("speaking");
        await playAudio(result.audio_base64, result.audio_mime_type);
        await endSession();
        return;
      }

      setAppState("speaking");
      await playAudio(result.audio_base64, result.audio_mime_type);

      const nextState = verificationState === "pending" && result.intent === "verify_identity" && !result.actions.find((a: any) => a.type === "citizen_verified") ? "awaiting-id" : "listening";
      setAppState(nextState);
      if (micStreamRef.current && !agentModeRef.current) {
        setTimeout(() => startVADRecorder(stream, sid), 200);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Turn failed");
      setAppState(micStreamRef.current ? "listening" : "idle");
      if (micStreamRef.current && !agentModeRef.current) {
        setTimeout(() => startVADRecorder(stream, sid), 200);
      }
    } finally {
      turnInFlightRef.current = false;
    }
  }

  async function runSafely(fn: () => Promise<void>) {
    try { await fn(); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed"); setAppState("idle"); }
  }

  if (!mounted) return <div className="va-shell" />;

  const orb = orbStyle(appState, voiceLevel);
  const waveBars = Array.from({ length: 9 }, (_, i) => {
    const speaking = appState === "speaking" || appState === "speaking-intro";
    const listening = appState === "listening" || appState === "awaiting-id";
    const h = speaking ? 4 + Math.abs(Math.sin(Date.now() / 180 + i * 0.9)) * 28
            : listening ? 4 + voiceLevel * 140 * Math.abs(Math.sin(i * 1.3))
            : 4;
    return h;
  });

  return (
    <div className="va-shell">
      {/* Top bar */}
      <header className="va-topbar">
        <div className="va-brand">
          <div className="va-brand-dot" />
          <span>Aarogya</span>
          <span className="va-brand-sub">Citizen Health AI</span>
        </div>
        <div className="va-topbar-right">
          {/* LiveKit status badge */}
          <div
            className="va-lk-badge"
            title={lkRoom ? `LiveKit room: ${lkRoom}` : `LiveKit: ${lkStatus}`}
            style={{ borderColor: `${LK_STATUS_COLORS[lkStatus]}40`, color: LK_STATUS_COLORS[lkStatus] }}
          >
            <Radio size={11} />
            <span>
              {lkStatus === "connected"
                ? lkAgentActive ? "LiveKit Agent" : "LiveKit"
                : lkStatus === "connecting"
                  ? "Connecting…"
                  : lkStatus === "failed"
                    ? "LK Failed"
                    : "LiveKit"}
            </span>
            <span
              className="va-lk-dot"
              style={{ background: LK_STATUS_COLORS[lkStatus], boxShadow: lkStatus === "connected" ? `0 0 6px ${LK_STATUS_COLORS[lkStatus]}` : "none" }}
            />
          </div>
          {citizen && verificationState === "verified" && (
            <div className="va-citizen-badge">
              <User size={13} />
              <span>{citizen.full_name}</span>
              {citizen.ayushman_eligible && <span className="va-ayush-dot" title="Ayushman eligible" />}
            </div>
          )}
          <Link href="/health-worker" className="va-nav-pill"><Stethoscope size={13} /> Health Worker</Link>
          <Link href="/surveillance" className="va-nav-pill"><Radio size={13} /> Surveillance</Link>
          <Link href="/analytics" className="va-nav-pill"><BarChart3 size={13} /> Analytics</Link>
          <Link href="/debug" className="va-nav-pill"><Brain size={13} /> LLM Probe</Link>
          {isLowBandwidth && (
            <div className="va-low-bw-badge" title="Low bandwidth detected. Using optimized REST protocol.">
              <Radio size={11} className="pulse" />
              Micro-Voice Mode
            </div>
          )}
        </div>
      </header>

      {/* Main stage */}
      <main className="va-stage">
        <div className="va-ambient" style={{ background: orb.glow }} />

        <div className="va-orb-wrap">
          <div
            className="va-orb"
            role="button"
            aria-label={isLive ? "End call" : "Waiting for wake word"}
            onClick={() => isLive ? runSafely(endSession) : runSafely(() => beginSession("en-IN"))}
            style={{ transform: `scale(${orb.scale})`, cursor: "pointer" }}
          >
            <div className="va-orb-core" style={{ background: orb.grad }} />
            <div className="va-orb-shine" />
            <div className="va-orb-ring" style={{ borderColor: orb.ring }} />
            <div className="va-orb-halo" />
            <div className="va-orb-icon">
              {appState === "connecting" || appState === "thinking" || appState === "verifying"
                ? <Loader2 size={44} color="rgba(255,255,255,0.55)" className="spin" />
                : isLive
                  ? <PhoneOff size={36} color="rgba(255,255,255,0.45)" />
                  : <Mic size={44} color="rgba(255,255,255,0.6)" />
              }
            </div>
          </div>

          {/* Wave bars */}
          <div className="va-wave">
            {waveBars.map((h, i) => (
              <div key={i} className="va-wave-bar" style={{ height: `${h}px`, opacity: isLive ? 0.75 : 0.18, background: orb.glow }} />
            ))}
          </div>

          {/* Status */}
          <div className="va-status">
            <div className="va-status-dot" style={{ background: orb.glow }} />
            {orb.label}
          </div>
        </div>

        {/* Latest agent text */}
        {latestText && (
          <div className="va-latest">
            {latestIntent && (
              <div className="va-intent-tag">
                {(() => { const Icon = INTENT_ICONS[latestIntent]; return Icon ? <Icon size={11} /> : null; })()}
                {latestIntent.replace(/_/g, " ")}
              </div>
            )}
            <p>{latestText}</p>
          </div>
        )}

        {error && (
          <div className="va-error">
            <AlertTriangle size={14} /> {error}
          </div>
        )}

        {/* LiveKit room info when connected */}
        {lkStatus === "connected" && lkRoom && (
          <div className="va-lk-room-info">
            <Radio size={11} />
            <span>Room: <strong>{lkRoom}</strong></span>
          </div>
        )}

        {appState === "listening-wake" && (
          <div className="va-wake-hint">
            <div className="va-wake-langs">
              <span>Say:</span>
              <span className="va-wake-word">Hello</span>
              <span className="va-wake-sep">·</span>
              <span className="va-wake-word">Namaste</span>
              <span className="va-wake-sep">·</span>
              <span className="va-wake-word">Pranam</span>
              <span className="va-wake-sep">·</span>
              <span className="va-wake-word">Namaskara</span>
              <span className="va-wake-sep">·</span>
              <span className="va-wake-word">Vanakkam</span>
            </div>
          </div>
        )}
      </main>

      {/* Chat history */}
      {chat.length > 0 && (
        <div className="va-chat-rail">
          {chat.slice(-6).map((e, i) => (
            <div key={i} className={`va-msg va-msg--${e.role}`}>
              {e.role === "agent" && e.intent && (
                <span className="va-msg-intent">{e.intent.replace(/_/g, " ")}</span>
              )}
              <div className="va-msg-bubble">
                <ReactMarkdown>{e.text}</ReactMarkdown>
              </div>
            </div>
          ))}
          <div ref={chatEndRef} />
        </div>
      )}

      {/* End call button */}
      {isLive && (
        <footer className="va-footer">
          <button className="va-end-btn" onClick={() => runSafely(endSession)}>
            <PhoneOff size={18} /> End Call
          </button>
        </footer>
      )}

      {/* Post-call summary */}
      {appState === "ended" && summary && (
        <div className="va-summary-overlay">
          <div className="va-summary-card">
            <div className="va-summary-header">
              <CheckCircle2 size={22} color="#6ee7b7" />
              <h2>Call Summary</h2>
              <button className="va-summary-close" onClick={() => { setSummary(null); setAppState("idle"); }}><X size={16} /></button>
            </div>

            {summary.citizen && (
              <div className="va-summary-citizen">
                <User size={16} />
                <div>
                  <div className="va-summary-name">{(summary.citizen as any).full_name || "Guest"}</div>
                  <div className="va-summary-phc">{(summary.citizen as any).phc_name || ""}</div>
                </div>
                <div className="va-summary-badge" style={{ color: summary.verification_state === "verified" ? "#6ee7b7" : "#fbbf24" }}>
                  {summary.verification_state === "verified" ? "✓ Verified" : "Guest"}
                </div>
              </div>
            )}

            <div className="va-summary-stats">
              <div className="va-stat"><span>{summary.turns}</span><label>Turns</label></div>
              <div className="va-stat"><span>{summary.language_code?.split("-")[0].toUpperCase()}</span><label>Language</label></div>
              <div className="va-stat"><span>{summary.history_length}</span><label>Messages</label></div>
            </div>

            {summary.call_summary && (
              <p className="va-summary-text">{summary.call_summary}</p>
            )}

            <button className="va-summary-new-btn" onClick={() => { setSummary(null); setAppState("idle"); setChat([]); setLatestText(""); }}>
              Start New Call
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
