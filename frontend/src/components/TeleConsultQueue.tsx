"use client";
import { useEffect, useState } from "react";
import { Zap, User, PhoneForwarded, Clock, ExternalLink } from "lucide-react";
import { API_BASE_URL } from "@/lib/api";

type LiveRequest = {
  session_id: string;
  patient_name: string;
  reason: string;
  last_active: string;
};

export default function TeleConsultQueue({ onJoin }: { onJoin: (sessionId: string) => void }) {
  const [requests, setRequests] = useState<LiveRequest[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchRequests = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/health-worker/live-requests`);
      const data = await res.json();
      setRequests(data.requests || []);
    } catch (e) {
      console.error("Failed to fetch live requests", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRequests();
    const id = setInterval(fetchRequests, 5000); // Poll every 5s
    return () => clearInterval(id);
  }, []);

  if (loading && requests.length === 0) return null;

  return (
    <div className="tc-queue">
      <div className="tc-header">
        <Zap size={14} className="pulse" style={{ color: "#f87171" }} />
        <span>Live Tele-Consultation Queue</span>
        {requests.length > 0 && <span className="tc-count">{requests.length}</span>}
      </div>

      <div className="tc-list">
        {requests.map(req => (
          <div key={req.session_id} className="tc-card">
            <div className="tc-card-left">
              <div className="tc-patient">
                <User size={14} />
                <span>{req.patient_name}</span>
              </div>
              <div className="tc-reason">{req.reason}</div>
              <div className="tc-time">
                <Clock size={10} />
                <span>Active {new Date(req.last_active).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
              </div>
            </div>
            <button className="tc-join-btn" onClick={() => onJoin(req.session_id)}>
              <PhoneForwarded size={14} />
              Join
            </button>
          </div>
        ))}

        {requests.length === 0 && (
          <div className="tc-empty">
            No active emergency triage requests.
          </div>
        )}
      </div>

      <style jsx>{`
        .tc-queue {
          background: rgba(24, 24, 27, 0.6);
          backdrop-filter: blur(12px);
          border: 1px solid rgba(248, 113, 113, 0.2);
          border-radius: 12px;
          overflow: hidden;
          margin-bottom: 20px;
        }
        .tc-header {
          padding: 10px 16px;
          background: rgba(248, 113, 113, 0.05);
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 13px;
          font-weight: 600;
          color: #f87171;
          border-bottom: 1px solid rgba(248, 113, 113, 0.1);
        }
        .tc-count {
          background: #f87171;
          color: white;
          font-size: 10px;
          padding: 1px 6px;
          border-radius: 10px;
        }
        .tc-list {
          padding: 12px;
          display: flex;
          flex-direction: column;
          gap: 10px;
          max-height: 250px;
          overflow-y: auto;
        }
        .tc-card {
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.05);
          padding: 12px;
          border-radius: 8px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          transition: all 0.2s;
        }
        .tc-card:hover {
          background: rgba(255, 255, 255, 0.06);
          border-color: rgba(248, 113, 113, 0.3);
        }
        .tc-card-left {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .tc-patient {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 13px;
          font-weight: 500;
          color: #f4f4f5;
        }
        .tc-reason {
          font-size: 11px;
          color: #a1a1aa;
        }
        .tc-time {
          display: flex;
          align-items: center;
          gap: 4px;
          font-size: 10px;
          color: #71717a;
        }
        .tc-join-btn {
          background: #f87171;
          color: white;
          border: none;
          padding: 6px 14px;
          border-radius: 6px;
          font-size: 12px;
          font-weight: 600;
          display: flex;
          align-items: center;
          gap: 6px;
          cursor: pointer;
          transition: all 0.2s;
        }
        .tc-join-btn:hover {
          background: #ef4444;
          transform: translateY(-1px);
        }
        .tc-empty {
          padding: 20px;
          text-align: center;
          font-size: 12px;
          color: #71717a;
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
