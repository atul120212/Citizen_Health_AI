"use client";

import { useEffect, useState } from "react";
import { API_BASE_URL } from "@/lib/api";
import {
  ArrowLeft,
  Brain,
  CheckCircle2,
  RefreshCw,
  XCircle,
} from "lucide-react";
import Link from "next/link";

type ProbeCase = {
  id: string;
  description: string;
  passed: boolean;
  checks: Record<string, boolean>;
  raw_preview: string;
  parsed_intent: string | null;
  error?: string;
};

type ProbeReport = {
  score: number;
  passed: number;
  total: number;
  grade: string;
  model: string;
  timestamp: string;
  cases: ProbeCase[];
};

function gradeColor(score: number) {
  if (score >= 90) return "#6ee7b7";
  if (score >= 75) return "#fcd34d";
  if (score >= 60) return "#fb923c";
  return "#f87171";
}

export default function LLMProbePage() {
  const [report, setReport] = useState<ProbeReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runProbe = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/debug/llm-check`);
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      setReport(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Probe failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { runProbe(); }, []);

  return (
    <div className="analytics-shell">
      <header className="an-header">
        <div className="an-header-left">
          <Link href="/" className="an-back-btn" aria-label="Back">
            <ArrowLeft size={18} />
          </Link>
          <div className="an-title-group">
            <Brain size={22} className="an-title-icon" />
            <h1>LLM Intelligence Probe</h1>
          </div>
        </div>
        <button className="an-refresh-btn" onClick={runProbe} disabled={loading} aria-label="Re-run">
          <RefreshCw size={16} className={loading ? "spin" : ""} />
          {loading ? "Running…" : "Re-run Probe"}
        </button>
      </header>

      {error && <div className="an-error">{error}</div>}

      {report && (
        <div className="an-content">
          {/* Score card */}
          <div className="probe-score-card">
            <div className="probe-score-ring" style={{ borderColor: gradeColor(report.score) }}>
              <span className="probe-score-num" style={{ color: gradeColor(report.score) }}>
                {report.score}
              </span>
              <span className="probe-score-unit">/ 100</span>
            </div>
            <div className="probe-score-info">
              <div className="probe-grade" style={{ color: gradeColor(report.score) }}>
                {report.grade}
              </div>
              <div className="probe-meta">Model: <strong>{report.model}</strong></div>
              <div className="probe-meta">{report.passed}/{report.total} probes passed</div>
              <div className="probe-meta probe-ts">
                {new Date(report.timestamp).toLocaleString()}
              </div>
            </div>
          </div>

          {/* Cases */}
          <div className="probe-cases">
            {report.cases.map((c) => (
              <div key={c.id} className={`probe-case ${c.passed ? "probe-case--pass" : "probe-case--fail"}`}>
                <div className="probe-case-header">
                  {c.passed
                    ? <CheckCircle2 size={18} color="#6ee7b7" />
                    : <XCircle size={18} color="#f87171" />
                  }
                  <span className="probe-case-id">{c.id.replace(/_/g, " ")}</span>
                  {c.parsed_intent && (
                    <span className="probe-intent-badge">{c.parsed_intent}</span>
                  )}
                </div>
                <p className="probe-case-desc">{c.description}</p>

                {c.error && (
                  <div className="probe-case-error">{c.error}</div>
                )}

                <div className="probe-checks">
                  {Object.entries(c.checks).map(([check, ok]) => (
                    <span key={check} className={`probe-check ${ok ? "probe-check--ok" : "probe-check--fail"}`}>
                      {ok ? "✓" : "✗"} {check.replace(/_/g, " ")}
                    </span>
                  ))}
                </div>

                {c.raw_preview && (
                  <pre className="probe-raw">{c.raw_preview}</pre>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
