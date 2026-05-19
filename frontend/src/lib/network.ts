"use client";
import { useState, useEffect } from "react";

export type ConnectionQuality = "excellent" | "fair" | "poor";

export function useNetworkStatus() {
  const [quality, setQuality] = useState<ConnectionQuality>("excellent");
  const [latency, setLatency] = useState(0);

  useEffect(() => {
    const checkLatency = async () => {
      const start = performance.now();
      try {
        await fetch("/api/health", { method: "HEAD", cache: "no-store" });
        const end = performance.now();
        const rtt = end - start;
        setLatency(rtt);
        
        if (rtt > 800) setQuality("poor");
        else if (rtt > 300) setQuality("fair");
        else setQuality("excellent");
      } catch {
        setQuality("poor");
      }
    };

    checkLatency();
    const id = setInterval(checkLatency, 10000); // Check every 10s
    return () => clearInterval(id);
  }, []);

  // Also listen to browser's Network Information API if available
  useEffect(() => {
    const conn = (navigator as any).connection;
    if (!conn) return;

    const update = () => {
      if (conn.effectiveType === "2g" || conn.saveData) setQuality("poor");
      else if (conn.effectiveType === "3g") setQuality("fair");
    };

    conn.addEventListener("change", update);
    update();
    return () => conn.removeEventListener("change", update);
  }, []);

  return { quality, latency };
}
