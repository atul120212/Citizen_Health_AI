"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft, Mic, PhoneOff, Loader2, User, ClipboardList,
  AlertTriangle, CheckCircle2, Stethoscope, BookOpen, GitBranch, X,
} from "lucide-react";
import { API_BASE_URL } from "@/lib/api";
import TeleConsultQueue from "@/components/TeleConsultQueue";
import WorkerLeaderboard from "@/components/WorkerLeaderboard";
import OutreachTaskList from "@/components/OutreachTaskList";

// ── Types ──────────────────────────────────────────────────
type WorkerRole = "asha" | "phc_nurse" | "doctor";
type AppState = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "ended";

type TurnResult = {
  intent: string;
  response_text: string;
  transcript?: string;
  audio_base64?: string | null;
  audio_mime_type?: string;
  patient_record?: Record<string, any> | null;
  referral_level?: string;
  referral_reason?: string | null;
  protocol_name?: string | null;
  action_points?: string[];
  needs_supervisor?: boolean;
};

type ChatEntry = { role: "agent" | "user"; text: string; intent: string; timestamp: number };

const SILENCE_MS = 600;
const MIN_SPEECH_MS = 300;
const MAX_TURN_MS = 20000;
const VOICE_THRESHOLD = 0.02;

const ROLE_META: Record<WorkerRole, { label: string; color: string; icon: typeof User }> = {
  asha:      { label: "ASHA Worker",  color: "#f9a8d4", icon: User },
  phc_nurse: { label: "PHC Nurse",    color: "#93c5fd", icon: Stethoscope },
  doctor:    { label: "PHC Doctor",   color: "#6ee7b7", icon: BookOpen },
};

const INTENT_META: Record<string, { label: string; color: string }> = {
  protocol_lookup:      { label: "Protocol", color: "#93c5fd" },
  patient_record_update:{ label: "Record",   color: "#6ee7b7" },
  referral_guidance:    { label: "Referral", color: "#fcd34d" },
  emergency_referral:   { label: "Emergency Referral", color: "#fca5a5" },
  urgent_referral:      { label: "Urgent Referral", color: "#fb923c" },
  manage_at_home:       { label: "Manage at Home", color: "#86efac" },
  general_query:        { label: "Query",    color: "#c4b5fd" },
};

function getSupportedMime() {
  for (const t of ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"]) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(t)) return t;
  }
  return "";
}

export default function HealthWorkerPage() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const [role, setRole] = useState<WorkerRole>("asha");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [appState, setAppState] = useState<AppState>("idle");
  const [chat, setChat] = useState<ChatEntry[]>([]);
  const [latestResult, setLatestResult] = useState<TurnResult | null>(null);
  const [voiceLevel, setVoiceLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [textInput, setTextInput] = useState("");
  const [useVoice, setUseVoice] = useState(false);
  const [tick, setTick] = useState(0);

  const micStreamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const animRef = useRef<number | null>(null);
  const levelAnimRef = useRef<number | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const speechRef = useRef({ hasSpeech: false, lastVoiceAt: 0, startedAt: 0, stopped: false });
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [chat]);
  useEffect(() => {
    if (appState === "listening" || appState === "speaking") {
      const id = setInterval(() => setTick(t => t + 1), 60);
      return () => clearInterval(id);
    }
  }, [appState]);
  void tick;
  useEffect(() => () => cleanup(), []);

  const startLevel = useCallback((analyser: AnalyserNode) => {
    analyserRef.current = analyser;
    const data = new Uint8Array(analyser.fftSize);
    const loop = () => {
      if (!analyserRef.current) return;
      analyser.getByteTimeDomainData(data);
      let s = 0; for (const v of data) { const c = (v - 128) / 128; s += c * c; }
      setVoiceLevel(p => p * 0.6 + Math.sqrt(s / data.length) * 0.4);
      levelAnimRef.current = requestAnimationFrame(loop);
    };
    levelAnimRef.current = requestAnimationFrame(loop);
  }, []);

  const stopLevel = useCallback(() => {
    analyserRef.current = null;
    if (levelAnimRef.current) { cancelAnimationFrame(levelAnimRef.current); levelAnimRef.current = null; }
    setVoiceLevel(0);
  }, []);

  function cleanup() {
    if (animRef.current) { cancelAnimationFrame(animRef.current); animRef.current = null; }
    stopLevel();
    recorderRef.current?.stop(); recorderRef.current = null;
    audioRef.current?.pause(); audioRef.current = null;
    micStreamRef.current?.getTracks().forEach(t => t.stop()); micStreamRef.current = null;
  }

  function pushChat(entry: ChatEntry) { setChat(prev => [...prev, entry]); }

  async function playAudio(b64: string | null | undefined, mime?: string) {
    if (!b64) return;
    audioRef.current?.pause();
    const audio = new Audio(`data:${mime || "audio/wav"};base64,${b64}`);
    audioRef.current = audio;
    await new Promise<void>(r => { audio.onended = () => r(); audio.onerror = () => r(); audio.play().catch(() => r()); });
  }

  // ── Start session ─────────────────────────────────────────
  async function startSession() {
    setError(null); setChat([]); setLatestResult(null); setAppState("connecting");
    const res = await fetch(`${API_BASE_URL}/api/health-worker/session/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language_code: "en-IN", worker_role: role }),
    });
    const data = await res.json();
    setSessionId(data.session_id);
    pushChat({ role: "agent", text: data.intro_text, intent: "greeting", timestamp: Date.now() });
    setAppState("speaking");
    setTimeout(() => setAppState("listening"), 800);
  }

  // ── text submit ───────────────────────────────────────────
  async function submitText(e: React.FormEvent) {
    e.preventDefault();
    if (!textInput.trim() || appState === "thinking") return;
    const text = textInput.trim();
    setTextInput("");
    pushChat({ role: "user", text, intent: "", timestamp: Date.now() });
    setAppState("thinking");
    try {
      const res = await fetch(`${API_BASE_URL}/api/health-worker/turn`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, language_code: "en-IN", session_id: sessionId, worker_role: role }),
      });
      const result: TurnResult = await res.json();
      setLatestResult(result);
      pushChat({ role: "agent", text: result.response_text, intent: result.intent, timestamp: Date.now() });
      setAppState("speaking");
      await playAudio(result.audio_base64, result.audio_mime_type);
      setAppState("listening");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
      setAppState("listening");
    }
  }

  // ── Voice recording ───────────────────────────────────────
  async function toggleVoice() {
    if (appState === "listening" && useVoice) {
      startVAD();
    }
  }

  function startVAD() {
    navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
      .then(stream => {
        micStreamRef.current = stream;
        const mime = getSupportedMime();
        const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : {});
        recorderRef.current = rec;
        chunksRef.current = [];
        speechRef.current = { hasSpeech: false, lastVoiceAt: 0, startedAt: performance.now(), stopped: false };

        const ctx = new AudioContext();
        const analyser = ctx.createAnalyser();
        ctx.createMediaStreamSource(stream).connect(analyser);
        startLevel(analyser);

        rec.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data); };
        rec.onstop = async () => {
          stopLevel(); await ctx.close();
          const s = speechRef.current;
          const blob = new Blob(chunksRef.current, { type: "audio/webm" });
          chunksRef.current = [];
          if (!s.hasSpeech || blob.size < 900) { cleanup(); return; }
          await sendVoice(blob);
        };
        rec.start(200);
        monitorSpeech(analyser, stream);
      })
      .catch(err => setError("Microphone access denied"));
  }

  function monitorSpeech(analyser: AnalyserNode, stream: MediaStream) {
    const data = new Uint8Array(analyser.fftSize);
    const loop = () => {
      const r = recorderRef.current; const s = speechRef.current;
      if (!r || r.state !== "recording" || s.stopped) return;
      analyser.getByteTimeDomainData(data);
      let sum = 0; for (const v of data) { const c = (v - 128) / 128; sum += c * c; }
      const rms = Math.sqrt(sum / data.length);
      const now = performance.now();
      if (rms > VOICE_THRESHOLD) { if (!s.hasSpeech) s.startedAt = now; s.hasSpeech = true; s.lastVoiceAt = now; }
      const dur = now - s.startedAt; const sil = now - s.lastVoiceAt;
      if ((s.hasSpeech && dur > MIN_SPEECH_MS && sil > SILENCE_MS) || (s.hasSpeech && dur > MAX_TURN_MS)) {
        s.stopped = true; r.stop(); return;
      }
      animRef.current = requestAnimationFrame(loop);
    };
    animRef.current = requestAnimationFrame(loop);
  }

  async function sendVoice(blob: Blob) {
    setAppState("thinking");
    const fd = new FormData();
    fd.append("audio", blob, "worker-turn.webm");
    if (sessionId) fd.append("session_id", sessionId);
    fd.append("worker_role", role);
    try {
      const res = await fetch(`${API_BASE_URL}/api/health-worker/voice-turn`, { method: "POST", body: fd });
      const result: TurnResult = await res.json();
      if (result.transcript) pushChat({ role: "user", text: result.transcript, intent: "", timestamp: Date.now() });
      setLatestResult(result);
      pushChat({ role: "agent", text: result.response_text, intent: result.intent, timestamp: Date.now() });
      setAppState("speaking");
      await playAudio(result.audio_base64, result.audio_mime_type);
      setAppState("listening");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Voice turn failed");
      setAppState("listening");
    } finally {
      cleanup();
    }
  }

  if (!mounted) return <div className="hw-shell" />;

  const roleMeta = ROLE_META[role];
  const isActive = !["idle", "ended"].includes(appState);

  return (
    <div className="hw-shell">
      {/* Header */}
      <header className="hw-header">
        <div className="hw-header-left">
          <Link href="/" className="an-back-btn"><ArrowLeft size={18} /></Link>
          <Stethoscope size={20} style={{ color: "#93c5fd" }} />
          <div>
            <div className="hw-title">Health Worker AI</div>
            <div className="hw-subtitle">Sahayak — Protocol · Records · Referral</div>
          </div>
        </div>
        {isActive && (
          <button className="hw-end-btn" onClick={() => { cleanup(); setAppState("ended"); setSessionId(null); }}>
            <X size={14} /> End Session
          </button>
        )}
      </header>

      <div className="hw-body">
        {/* Left: Controls */}
        <div className="hw-sidebar">
          {/* Role selector */}
          <div className="hw-card">
            <div className="hw-card-title">Worker Role</div>
            <div className="hw-role-grid">
              {(Object.entries(ROLE_META) as [WorkerRole, typeof ROLE_META[WorkerRole]][]).map(([r, m]) => (
                <button
                  key={r}
                  className={`hw-role-btn ${role === r ? "hw-role-btn--active" : ""}`}
                  style={role === r ? { borderColor: m.color, color: m.color } : {}}
                  onClick={() => setRole(r)}
                  disabled={isActive}
                >
                  <m.icon size={14} />
                  {m.label}
                </button>
              ))}
            </div>
          </div>

          {/* Quick prompts */}
          <div className="hw-card">
            <div className="hw-card-title">Quick Prompts</div>
            <div className="hw-quick-list">
              {[
                "What is the HBNC visit schedule for newborns?",
                "Patient: fever 3 days, 4 year old child, not eating",
                "ORS preparation and dosage protocol",
                "IFA dosage for pregnant women",
                "When to refer for severe acute malnutrition?",
                "DOTS protocol for new TB patient",
              ].map(q => (
                <button key={q} className="hw-quick-btn"
                  onClick={() => { setTextInput(q); }}
                  disabled={!isActive || appState === "thinking"}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>

          {/* Latest patient record */}
          {latestResult?.patient_record?.patient_name && (
            <div className="hw-card hw-record-card">
              <div className="hw-card-title"><ClipboardList size={13} /> Extracted Record</div>
              {Object.entries(latestResult.patient_record).map(([k, v]) => {
                if (!v || (Array.isArray(v) && v.length === 0) || typeof v === "object") return null;
                return (
                  <div key={k} className="hw-record-row">
                    <span className="hw-record-key">{k.replace(/_/g, " ")}</span>
                    <span className="hw-record-val">{String(v)}</span>
                  </div>
                );
              })}
            </div>
          )}
          <OutreachTaskList />
          <WorkerLeaderboard />
        </div>

        {/* Right: Chat + Input */}
        <div className="hw-main">
          {!isActive ? (
            <div className="hw-start-panel">
              <div className="hw-orb-icon" style={{ background: `${roleMeta.color}18`, borderColor: `${roleMeta.color}40` }}>
                <roleMeta.icon size={40} style={{ color: roleMeta.color }} />
              </div>
              <h2 className="hw-start-title">Sahayak Clinical AI</h2>
              <p className="hw-start-desc">
                Ask about NHM protocols, update patient records by voice, or get referral guidance.
              </p>
              <button className="hw-start-btn" onClick={() => runSafely(startSession)}
                style={{ background: `${roleMeta.color}22`, borderColor: `${roleMeta.color}50`, color: roleMeta.color }}>
                Start Session as {roleMeta.label}
              </button>
            </div>
          ) : (
            <>
              {/* Referral alert banner */}
              {latestResult && (latestResult.referral_level === "emergency" || latestResult.intent === "emergency_referral") && (
                <div className="hw-alert-banner hw-alert-banner--critical">
                  <AlertTriangle size={16} /> EMERGENCY REFERRAL REQUIRED — {latestResult.referral_reason}
                </div>
              )}
              {latestResult && latestResult.intent === "urgent_referral" && (
                <div className="hw-alert-banner hw-alert-banner--urgent">
                  <AlertTriangle size={14} /> Urgent referral within 24 hours — {latestResult.referral_reason}
                </div>
              )}

              {/* Action points */}
              {latestResult?.action_points && latestResult.action_points.length > 0 && (
                <div className="hw-action-points">
                  {latestResult.action_points.map((p, i) => (
                    <div key={i} className="hw-action-item"><CheckCircle2 size={12} /> {p}</div>
                  ))}
                </div>
              )}

              {role === "doctor" && (
                <TeleConsultQueue onJoin={(sid) => {
                  alert(`Joining Tele-Consultation for Session: ${sid}. \n(LiveKit Room connection logic is being initialized...)`);
                }} />
              )}

              {/* Chat messages */}
              <div className="hw-chat">
                {chat.map((e, i) => (
                  <div key={i} className={`hw-msg hw-msg--${e.role}`}>
                    {e.role === "agent" && e.intent && INTENT_META[e.intent] && (
                      <span className="hw-msg-intent" style={{ color: INTENT_META[e.intent].color }}>
                        {INTENT_META[e.intent].label}
                      </span>
                    )}
                    <div className="hw-msg-bubble">{e.text}</div>
                  </div>
                ))}
                <div ref={chatEndRef} />
              </div>

              {/* Status + voice level */}
              <div className="hw-status-bar">
                <div className={`hw-status-dot hw-status-dot--${appState}`} />
                <span>
                  {appState === "thinking" ? "Processing…"
                    : appState === "speaking" ? "Speaking…"
                    : appState === "listening" ? "Ready"
                    : "Connecting…"}
                </span>
                {appState === "listening" && useVoice && voiceLevel > 0.01 && (
                  <div className="hw-level-bars">
                    {Array.from({ length: 5 }, (_, i) => (
                      <div key={i} className="hw-level-bar"
                        style={{ height: `${4 + voiceLevel * 80 * Math.abs(Math.sin(i * 1.2))}px` }} />
                    ))}
                  </div>
                )}
              </div>

              {/* Input row */}
              {error && <div className="hw-error"><AlertTriangle size={12} /> {error}</div>}
              <form className="hw-input-row" onSubmit={submitText}>
                <input
                  className="hw-input"
                  placeholder="Ask a protocol question or describe a patient visit…"
                  value={textInput}
                  onChange={e => setTextInput(e.target.value)}
                  disabled={appState === "thinking"}
                />
                <button type="submit" className="hw-send-btn" disabled={!textInput.trim() || appState === "thinking"}>
                  {appState === "thinking" ? <Loader2 size={16} className="spin" /> : "Send"}
                </button>
                <button type="button" className={`hw-mic-btn ${useVoice ? "hw-mic-btn--active" : ""}`}
                  onClick={() => { setUseVoice(v => !v); if (!useVoice && appState === "listening") startVAD(); }}
                  title="Toggle voice input"
                >
                  <Mic size={16} />
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );

  async function runSafely(fn: () => Promise<void>) {
    try { await fn(); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed"); setAppState("idle"); }
  }
}
