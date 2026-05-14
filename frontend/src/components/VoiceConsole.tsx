"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Room, RoomEvent, Track } from "livekit-client";
import {
  Activity,
  Baby,
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

import { TurnResponse, createCitizen, createLiveKitToken, postTextTurn, postVoiceTurn } from "@/lib/api";

type SpeechState = {
  hasSpeech: boolean;
  lastVoiceAt: number;
  startedAt: number;
  stopped: boolean;
  discard: boolean;
};

const quickPrompts = [
  { icon: Hospital, label: "PHC counter", text: "Where is the registration counter?" },
  { icon: ShieldCheck, label: "Eligibility", text: "Am I eligible for Ayushman Bharat or CMCHIS?" },
  { icon: CalendarClock, label: "Appointment", text: "Book a doctor appointment for tomorrow morning." },
  { icon: Baby, label: "ANC reminder", text: "Set my maternal health reminder for ANC visit." }
];

const audioMimeType =
  typeof window !== "undefined" && MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
    ? "audio/webm;codecs=opus"
    : "audio/webm";

// VAD tuning: fast silence detection for low latency
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
  const [turn, setTurn] = useState<TurnResponse | null>(null);
  const [status, setStatus] = useState("Ready");
  const [error, setError] = useState<string | null>(null);
  const [isLive, setIsLive] = useState(false);
  const [isProcessingTurn, setIsProcessingTurn] = useState(false);
  const [roomName, setRoomName] = useState<string | null>(null);
  const [agentState, setAgentState] = useState("Not connected");
  const [voiceLevel, setVoiceLevel] = useState(0); // 0-1 RMS for pulse ring

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

  const audioSrc = useMemo(() => {
    if (!turn?.audio_base64) return null;
    return `data:${turn.audio_mime_type};base64,${turn.audio_base64}`;
  }, [turn]);

  // Drive the pulse ring from the analyser independently of VAD logic
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
      // Smooth the value a little so the ring doesn't flicker
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
      language_code: languageCode
    });
    setTurn(result);
    await playBulbulAudio(result);
    setStatus(isLive ? "Listening" : "Ready");
  }

  async function startRealtime() {
    setError(null);

    // navigator.mediaDevices is only available on secure origins (localhost or https://).
    // Over plain HTTP on a LAN/remote IP the browser hides it entirely.
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      throw new Error(
        "Microphone access is not available on this page. " +
          "Open the app via http://localhost:3001 (or serve over HTTPS) so the browser grants microphone permission."
      );
    }

    setStatus("Joining LiveKit");
    setAgentState("Connecting");

    const nextRoomName = `citizen-health-${Date.now()}`;
    const participantName = phoneNumber || `citizen-${Math.floor(Math.random() * 1000)}`;
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
        setStatus("Listening");
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
      })
      .on(RoomEvent.DataReceived, (payload, participant, _kind, topic) => {
        if (topic !== "citizen-health-turn") return;
        try {
          const message = JSON.parse(new TextDecoder().decode(payload));
          if (message.response_text) {
            setAgentState(`${participant?.identity || "agent"} responded`);
          }
        } catch {
          setAgentState("Agent data received");
        }
      });

    await room.connect(token.url, token.token);

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
    startAutoTurnRecorder(stream);
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
  }

  function startAutoTurnRecorder(stream: MediaStream) {
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

    const recorder = new MediaRecorder(stream, { mimeType: audioMimeType });
    recorderRef.current = recorder;

    const audioContext = new AudioContext();
    const analyser = audioContext.createAnalyser();
    const source = audioContext.createMediaStreamSource(stream);
    source.connect(analyser);

    // Start the visual level meter from this analyser
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
        if (roomRef.current) {
          window.setTimeout(() => startAutoTurnRecorder(stream), 150);
        }
        return;
      }

      await sendVoiceTurn(blob);
      if (roomRef.current) {
        window.setTimeout(() => startAutoTurnRecorder(stream), 150);
      }
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
        const centered = (value - 128) / 128;
        sum += centered * centered;
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
      const shouldCloseTurn =
        (state.hasSpeech && speechDuration > MIN_SPEECH_MS && silenceDuration > SILENCE_MS) ||
        (state.hasSpeech && speechDuration > MAX_TURN_MS) ||
        (!state.hasSpeech && now - state.startedAt > NO_SPEECH_ROLLOVER_MS);

      if (shouldCloseTurn) {
        state.stopped = true;
        recorder.stop();
        return;
      }

      animationRef.current = window.requestAnimationFrame(tick);
    };

    animationRef.current = window.requestAnimationFrame(tick);
  }

  async function sendVoiceTurn(blob: Blob) {
    setIsProcessingTurn(true);
    setStatus("Thinking");
    try {
      const result = await postVoiceTurn(blob, phoneNumber);
      setTurn(result);
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

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopCurrentRecorder(true);
      stopLevelMeter();
      micStreamRef.current?.getTracks().forEach((t) => t.stop());
      roomRef.current?.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Compute pulse ring scale: 1.0 at silence, up to 1.45 when loud
  const pulseScale = 1 + Math.min(voiceLevel * 8, 0.45);
  const pulseOpacity = isLive ? Math.min(0.2 + voiceLevel * 6, 0.7) : 0;

  // Mic is blocked on non-localhost HTTP origins by the browser
  const micUnavailable =
    typeof window !== "undefined" &&
    window.location.protocol === "http:" &&
    window.location.hostname !== "localhost" &&
    window.location.hostname !== "127.0.0.1";

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

          <div className="voice-stage">
            <div className="mic-wrapper">
              {/* Pulse ring driven by live voice level */}
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
              <p>
                {turn?.response_text ||
                  "Tap the mic once. LiveKit streams your voice, silence ends each turn, and Bulbul speaks the reply."}
              </p>
              {audioSrc && <audio controls src={audioSrc} />}
            </div>
          </div>

          <div className="text-row">
            <input value={text} onChange={(e) => setText(e.target.value)} />
            <button className="primary-button" onClick={() => runSafely(() => submitText())}>
              <Send size={17} />
              Test
            </button>
          </div>

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
