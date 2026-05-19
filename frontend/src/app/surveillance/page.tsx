"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft, Activity, AlertTriangle, RefreshCw, Bell,
  MapPin, TrendingUp, Shield, Zap, Radio,
} from "lucide-react";
import { API_BASE_URL } from "@/lib/api";
import SurveillanceMap from "@/components/SurveillanceMap";

// ── Types ──────────────────────────────────────────────────
type AlertLevel = "low" | "medium" | "high" | "critical";

type SurveillanceAlert = {
  id: string;
  disease: string;
  district: string;
  alert_level: AlertLevel;
  z_score: number;
  case_count: number;
  trend_pct: number;
  detected_at: string;
  description: string;
  recommended_action: string;
};

type WeekTrend = { week: string; [disease: string]: string | number };

type DistrictRisk = { district: string; risk: AlertLevel; active_alerts: number };

type DashboardData = {
  summary: {
    total_alerts: number;
    critical_alerts: number;
    high_alerts: number;
    districts_monitored: number;
    data_sources: number;
    last_updated: string;
  };
  alerts: SurveillanceAlert[];
  weekly_trends: WeekTrend[];
  district_risk: DistrictRisk[];
  demo: boolean;
};

const LEVEL_COLORS: Record<AlertLevel, string> = {
  low:      "#6ee7b7",
  medium:   "#fcd34d",
  high:     "#fb923c",
  critical: "#f87171",
};

const LEVEL_BG: Record<AlertLevel, string> = {
  low:      "rgba(110,231,183,0.08)",
  medium:   "rgba(252,211,77,0.08)",
  high:     "rgba(251,146,60,0.1)",
  critical: "rgba(248,113,113,0.12)",
};

const DISEASE_COLORS = [
  "#6ee7b7", "#93c5fd", "#fcd34d", "#f9a8d4", "#c4b5fd", "#86efac",
];

const DISEASES_TO_SHOW = ["Fever / ILI", "Diarrhoea", "Dengue", "Malaria", "Tuberculosis", "Anaemia"];

export default function SurveillancePage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const fetchDashboard = async () => {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/surveillance/dashboard`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load surveillance data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchDashboard(); }, []);

  const maxTrend = data
    ? Math.max(...(data.weekly_trends.flatMap(w => DISEASES_TO_SHOW.map(d => Number(w[d] ?? 0)))), 1)
    : 1;

  return (
    <div className="sv-shell">
      <header className="sv-header">
        <div className="sv-header-left">
          <Link href="/" className="an-back-btn"><ArrowLeft size={18} /></Link>
          <Radio size={20} style={{ color: "#f87171" }} />
          <div>
            <div className="sv-title">Disease Surveillance AI</div>
            <div className="sv-subtitle">Early outbreak detection for District Health Officers</div>
          </div>
          {data?.demo && <span className="an-demo-badge">Demo Data</span>}
        </div>
        <button className="an-refresh-btn" onClick={fetchDashboard} disabled={loading}>
          <RefreshCw size={15} className={loading ? "spin" : ""} />
          {loading ? "Loading…" : "Refresh"}
        </button>
      </header>

      {error && <div className="an-error">{error}</div>}

      {data && (
        <div className="sv-content">
          {/* KPI strip */}
          <div className="sv-kpi-strip">
            <div className="sv-kpi" style={{ borderColor: "rgba(248,113,113,0.3)" }}>
              <span className="sv-kpi-num" style={{ color: "#f87171" }}>{data.summary.critical_alerts}</span>
              <span className="sv-kpi-label">Critical Alerts</span>
            </div>
            <div className="sv-kpi" style={{ borderColor: "rgba(251,146,60,0.3)" }}>
              <span className="sv-kpi-num" style={{ color: "#fb923c" }}>{data.summary.high_alerts}</span>
              <span className="sv-kpi-label">High Alerts</span>
            </div>
            <div className="sv-kpi" style={{ borderColor: "rgba(110,231,183,0.2)" }}>
              <span className="sv-kpi-num" style={{ color: "#6ee7b7" }}>{data.summary.total_alerts}</span>
              <span className="sv-kpi-label">Total Alerts</span>
            </div>
            <div className="sv-kpi">
              <span className="sv-kpi-num">{data.summary.districts_monitored}</span>
              <span className="sv-kpi-label">Districts Monitored</span>
            </div>
            <div className="sv-kpi">
              <span className="sv-kpi-num">{data.summary.data_sources}</span>
              <span className="sv-kpi-label">Data Sources</span>
            </div>
            <div className="sv-kpi">
              <span className="sv-kpi-num sv-kpi-num--sm">
                {new Date(data.summary.last_updated).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </span>
              <span className="sv-kpi-label">Last Updated</span>
            </div>
          </div>

          <div className="sv-main-grid">
            {/* Alert cards */}
            <div className="sv-section">
              <div className="sv-section-title">
                <Bell size={15} style={{ color: "#f87171" }} /> Active Outbreak Alerts
              </div>
              <div className="sv-alert-list">
                {data.alerts.map(alert => (
                  <div
                    key={alert.id}
                    className="sv-alert-card"
                    style={{ borderColor: `${LEVEL_COLORS[alert.alert_level]}50`, background: LEVEL_BG[alert.alert_level] }}
                    onClick={() => setExpanded(expanded === alert.id ? null : alert.id)}
                  >
                    <div className="sv-alert-top">
                      <div className="sv-alert-left">
                        <span
                          className="sv-alert-level"
                          style={{ background: `${LEVEL_COLORS[alert.alert_level]}20`, color: LEVEL_COLORS[alert.alert_level] }}
                        >
                          {alert.alert_level === "critical" && <Zap size={10} />}
                          {alert.alert_level.toUpperCase()}
                        </span>
                        <span className="sv-alert-disease">{alert.disease}</span>
                        <span className="sv-alert-district"><MapPin size={10} /> {alert.district}</span>
                      </div>
                      <div className="sv-alert-stats">
                        <span className="sv-alert-cases">{alert.case_count} cases</span>
                        <span className="sv-alert-trend" style={{ color: LEVEL_COLORS[alert.alert_level] }}>
                          <TrendingUp size={11} /> +{alert.trend_pct}%
                        </span>
                        <span className="sv-alert-z">σ {alert.z_score}</span>
                      </div>
                    </div>
                    <p className="sv-alert-desc">{alert.description}</p>
                    {expanded === alert.id && (
                      <div className="sv-alert-action">
                        <AlertTriangle size={12} style={{ flexShrink: 0 }} />
                        {alert.recommended_action}
                      </div>
                    )}
                  </div>
                ))}
                {data.alerts.length === 0 && (
                  <div className="sv-no-alerts">
                    <Shield size={24} style={{ color: "#6ee7b7" }} />
                    <span>No active alerts — all indicators within normal range.</span>
                  </div>
                )}
              </div>
            </div>

            {/* Right column */}
            <div className="sv-right-col">
              {/* Interactive Outbreak Heatmap */}
              <div className="sv-card">
                <div className="sv-section-title"><MapPin size={14} /> Real-time Outbreak Hotspots</div>
                <SurveillanceMap />
              </div>

              {/* 8-week trend sparklines */}
              <div className="sv-card">
                <div className="sv-section-title"><Activity size={14} /> 8-Week Disease Trends</div>
                <div className="sv-sparks">
                  {DISEASES_TO_SHOW.map((disease, di) => {
                    const vals = data.weekly_trends.map(w => Number(w[disease] ?? 0));
                    const max = Math.max(...vals, 1);
                    const last = vals[vals.length - 1];
                    const prev = vals[vals.length - 2] || 1;
                    const trend = ((last - prev) / prev * 100).toFixed(0);
                    const color = DISEASE_COLORS[di % DISEASE_COLORS.length];
                    return (
                      <div key={disease} className="sv-spark-row">
                        <span className="sv-spark-label">{disease}</span>
                        <div className="sv-spark-chart">
                          {vals.map((v, i) => (
                            <div
                              key={i}
                              className="sv-spark-bar"
                              style={{ height: `${Math.max((v / max) * 40, 2)}px`, background: color, opacity: 0.6 + (i / vals.length) * 0.4 }}
                            />
                          ))}
                        </div>
                        <span className="sv-spark-trend" style={{ color: Number(trend) > 20 ? "#f87171" : Number(trend) < -10 ? "#6ee7b7" : "#fcd34d" }}>
                          {Number(trend) > 0 ? "+" : ""}{trend}%
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
