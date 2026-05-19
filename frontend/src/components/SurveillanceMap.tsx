"use client";
import { useEffect, useRef, useState } from "react";
import { MapPin, Info, Zap } from "lucide-react";
import { API_BASE_URL } from "@/lib/api";

type Hotspot = { lat: number; lng: number; disease: string; intensity: number };

export default function SurveillanceMap() {
  const [hotspots, setHotspots] = useState<Hotspot[]>([]);
  const [loading, setLoading] = useState(true);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/surveillance/hotspots`)
      .then(res => res.json())
      .then(data => {
        setHotspots(data.hotspots || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (loading || !canvasRef.current || hotspots.length === 0) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Clear and set dimensions
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    ctx.clearRect(0, 0, rect.width, rect.height);

    // Draw stylized map background (abstract India-like shape or grid)
    ctx.strokeStyle = "rgba(255,255,255,0.05)";
    ctx.lineWidth = 0.5;
    for (let i = 0; i < rect.width; i += 30) {
      ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, rect.height); ctx.stroke();
    }
    for (let j = 0; j < rect.height; j += 30) {
      ctx.beginPath(); ctx.moveTo(0, j); ctx.lineTo(rect.width, j); ctx.stroke();
    }

    // Normalizing coordinates to canvas space
    // Demo range roughly: Lat [8, 20], Lng [75, 85]
    const minLat = 8, maxLat = 20, minLng = 75, maxLng = 85;

    hotspots.forEach(spot => {
      const x = ((spot.lng - minLng) / (maxLng - minLng)) * rect.width;
      const y = rect.height - ((spot.lat - minLat) / (maxLat - minLat)) * rect.height;

      // Draw heat glow
      const grad = ctx.createRadialGradient(x, y, 0, x, y, 40 * spot.intensity);
      const color = spot.disease === "Dengue" ? "248, 113, 113" : "251, 146, 60";
      grad.addColorStop(0, `rgba(${color}, 0.3)`);
      grad.addColorStop(1, `rgba(${color}, 0)`);
      
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(x, y, 40 * spot.intensity, 0, Math.PI * 2);
      ctx.fill();

      // Draw center point
      ctx.fillStyle = `rgb(${color})`;
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, Math.PI * 2);
      ctx.fill();
    });

    // Pulse animation
    let frame = 0;
    const animate = () => {
      frame++;
      // Just a subtle refresh if needed
      // ...
    };
    const animId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animId);
  }, [hotspots, loading]);

  return (
    <div className="sv-map-container">
      <div className="sv-map-overlay">
        <div className="sv-map-legend">
          <div className="sv-legend-item">
            <span className="sv-dot" style={{ background: "#f87171" }}></span>
            <span>Dengue / Critical</span>
          </div>
          <div className="sv-legend-item">
            <span className="sv-dot" style={{ background: "#fb923c" }}></span>
            <span>Fever / High Risk</span>
          </div>
        </div>
        <div className="sv-map-status">
            <Zap size={12} className="pulse" />
            LIVE SYNDROMIC DATA
        </div>
      </div>
      
      {loading ? (
        <div className="sv-map-loading">Initializing Geo-Spatial Engine...</div>
      ) : (
        <canvas ref={canvasRef} className="sv-canvas-map" />
      )}
      
      <div className="sv-map-footer">
        <Info size={12} />
        Coordinates disaggregated at village level to protect patient privacy.
      </div>

      <style jsx>{`
        .sv-map-container {
          position: relative;
          width: 100%;
          height: 400px;
          background: #09090b;
          border-radius: 12px;
          overflow: hidden;
          border: 1px solid rgba(255,255,255,0.1);
        }
        .sv-canvas-map {
          width: 100%;
          height: 100%;
        }
        .sv-map-overlay {
          position: absolute;
          top: 16px;
          left: 16px;
          right: 16px;
          display: flex;
          justify-content: space-between;
          pointer-events: none;
          z-index: 10;
        }
        .sv-map-legend {
          background: rgba(15, 15, 20, 0.8);
          backdrop-filter: blur(8px);
          padding: 8px 12px;
          border-radius: 8px;
          border: 1px solid rgba(255,255,255,0.1);
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .sv-legend-item {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 11px;
          color: #a1a1aa;
        }
        .sv-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }
        .sv-map-status {
          background: rgba(248, 113, 113, 0.1);
          color: #f87171;
          padding: 4px 10px;
          border-radius: 20px;
          font-size: 10px;
          font-weight: 600;
          display: flex;
          align-items: center;
          gap: 6px;
          border: 1px solid rgba(248, 113, 113, 0.2);
        }
        .sv-map-loading {
          display: flex;
          align-items: center;
          justify-content: center;
          height: 100%;
          color: #71717a;
          font-size: 13px;
        }
        .sv-map-footer {
          position: absolute;
          bottom: 12px;
          left: 16px;
          color: #52525b;
          font-size: 10px;
          display: flex;
          align-items: center;
          gap: 4px;
        }
        @keyframes pulse {
          0% { opacity: 1; }
          50% { opacity: 0.4; }
          100% { opacity: 1; }
        }
        .pulse { animation: pulse 2s infinite; }
      `}</style>
    </div>
  );
}
