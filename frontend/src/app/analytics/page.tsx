"use client";

import { useEffect, useState } from "react";
import { API_BASE_URL } from "@/lib/api";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  Globe,
  Heart,
  MessageSquare,
  RefreshCw,
  Shield,
  Stethoscope,
  Users,
} from "lucide-react";
import Link from "next/link";

type AnalyticsSummary = {
  total_interactions: number;
  emergency_count: number;
  followup_needed: number;
  by_intent: { intent: string; count: number }[];
  by_language: { language: string; count: number }[];
  recent_interactions: {
    id: string;
    intent_detected: string;
    transcript_text: string;
    created_at: string;
    full_name: string | null;
  }[];
  demo?: boolean;
};

const INTENT_META: Record<string, { label: string; color: string; icon: typeof Activity }> = {
  appointment_booking:      { label: "Appointments",    color: "#6ee7b7", icon: Activity },
  hospital_navigation:      { label: "Navigation",      color: "#93c5fd", icon: Stethoscope },
  eligibility_check:        { label: "Eligibility",     color: "#fcd34d", icon: Shield },
  maternal_health_reminder: { label: "Maternal Health", color: "#f9a8d4", icon: Heart },
  nhm_programme_query:      { label: "NHM Queries",     color: "#c4b5fd", icon: MessageSquare },
  emergency:                { label: "Emergency",       color: "#fca5a5", icon: AlertTriangle },
  vitals_tracking:          { label: "NCD Vitals",      color: "#fb923c", icon: Activity },
  med_adherence:            { label: "Medication Adherence", color: "#6ee7b7", icon: Activity },
  voice_prescription:       { label: "Prescription",    color: "#93c5fd", icon: Activity },
  register_citizen:         { label: "Registration",    color: "#c4b5fd", icon: Users },
};

const LANG_META: Record<string, { label: string; flag: string }> = {
  ta: { label: "Tamil",   flag: "🇮🇳" },
  hi: { label: "Hindi",   flag: "🇮🇳" },
  en: { label: "English", flag: "🇮🇳" },
  kn: { label: "Kannada", flag: "🇮🇳" },
  ml: { label: "Malayalam", flag: "🇮🇳" },
  te: { label: "Telugu",  flag: "🇮🇳" },
};

export default function AnalyticsDashboard() {
  const [data, setData] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/analytics/summary`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load analytics");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const maxIntentCount = data ? Math.max(...data.by_intent.map(i => i.count), 1) : 1;
  const maxLangCount   = data ? Math.max(...data.by_language.map(l => l.count), 1) : 1;

  return (
    <div className="analytics-shell">
      {/* Header */}
      <header className="an-header">
        <div className="an-header-left">
          <Link href="/" className="an-back-btn" aria-label="Back to console">
            <ArrowLeft size={18} />
          </Link>
          <div className="an-title-group">
            <BarChart3 size={22} className="an-title-icon" />
            <h1>Analytics Dashboard</h1>
          </div>
          {data?.demo && (
            <span className="an-demo-badge">Demo Data</span>
          )}
        </div>
        <button className="an-refresh-btn" onClick={fetchData} disabled={loading} aria-label="Refresh">
          <RefreshCw size={16} className={loading ? "spin" : ""} />
          {loading ? "Loading…" : "Refresh"}
        </button>
      </header>

      {error && <div className="an-error">{error}</div>}

      {data && (
        <div className="an-content">
          {/* KPI Cards */}
          <div className="an-kpi-grid">
            <div className="an-kpi-card">
              <div className="an-kpi-icon" style={{ background: "rgba(110,231,183,0.12)", color: "#6ee7b7" }}>
                <Users size={24} />
              </div>
              <div className="an-kpi-info">
                <span className="an-kpi-number">{data.total_interactions.toLocaleString()}</span>
                <span className="an-kpi-label">Total Interactions</span>
              </div>
            </div>

            <div className="an-kpi-card">
              <div className="an-kpi-icon" style={{ background: "rgba(252,165,165,0.12)", color: "#fca5a5" }}>
                <AlertTriangle size={24} />
              </div>
              <div className="an-kpi-info">
                <span className="an-kpi-number" style={{ color: "#fca5a5" }}>{data.emergency_count}</span>
                <span className="an-kpi-label">Emergency Cases</span>
              </div>
            </div>

            <div className="an-kpi-card">
              <div className="an-kpi-icon" style={{ background: "rgba(251,191,36,0.12)", color: "#fbbf24" }}>
                <Activity size={24} />
              </div>
              <div className="an-kpi-info">
                <span className="an-kpi-number" style={{ color: "#fbbf24" }}>{data.followup_needed}</span>
                <span className="an-kpi-label">Needs Followup</span>
              </div>
            </div>

            <div className="an-kpi-card">
              <div className="an-kpi-icon" style={{ background: "rgba(147,197,253,0.12)", color: "#93c5fd" }}>
                <Globe size={24} />
              </div>
              <div className="an-kpi-info">
                <span className="an-kpi-number">{data.by_language.length}</span>
                <span className="an-kpi-label">Languages Served</span>
              </div>
            </div>
          </div>

          {/* Charts Row */}
          <div className="an-charts-row">
            {/* Intent breakdown */}
            <div className="an-chart-card">
              <h2 className="an-chart-title">Intent Distribution</h2>
              <div className="an-bars">
                {data.by_intent.map((item) => {
                  const meta = INTENT_META[item.intent] || { label: item.intent, color: "#6ee7b7" };
                  const pct = Math.round((item.count / maxIntentCount) * 100);
                  return (
                    <div key={item.intent} className="an-bar-row">
                      <span className="an-bar-label">{meta.label}</span>
                      <div className="an-bar-track">
                        <div
                          className="an-bar-fill"
                          style={{ width: `${pct}%`, background: meta.color }}
                        />
                      </div>
                      <span className="an-bar-count" style={{ color: meta.color }}>{item.count}</span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Language breakdown */}
            <div className="an-chart-card">
              <h2 className="an-chart-title">Language Distribution</h2>
              <div className="an-lang-circles">
                {data.by_language.map((item) => {
                  const meta = LANG_META[item.language] || { label: item.language, flag: "🌐" };
                  const pct = Math.round((item.count / data.total_interactions) * 100);
                  const size = 60 + Math.round((item.count / maxLangCount) * 60);
                  return (
                    <div key={item.language} className="an-lang-bubble" style={{ width: size, height: size }}>
                      <span className="an-lang-flag">{meta.flag}</span>
                      <span className="an-lang-name">{meta.label}</span>
                      <span className="an-lang-pct">{pct}%</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Recent interactions */}
          {data.recent_interactions.length > 0 && (
            <div className="an-chart-card an-recent">
              <h2 className="an-chart-title">Recent Interactions</h2>
              <div className="an-table-wrapper">
                <table className="an-table">
                  <thead>
                    <tr>
                      <th>Citizen</th>
                      <th>Intent</th>
                      <th>Transcript Preview</th>
                      <th>Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent_interactions.map((row) => {
                      const meta = INTENT_META[row.intent_detected];
                      return (
                        <tr key={row.id}>
                          <td>{row.full_name || "Unknown"}</td>
                          <td>
                            <span className="an-intent-badge" style={{ color: meta?.color || "#6ee7b7" }}>
                              {meta?.label || row.intent_detected}
                            </span>
                          </td>
                          <td className="an-transcript-preview">{(row.transcript_text || "").slice(0, 60)}…</td>
                          <td className="an-time">{new Date(row.created_at).toLocaleTimeString()}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
