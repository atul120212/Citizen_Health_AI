"use client";
import { useEffect, useState } from "react";
import { Trophy, Medal, Target, TrendingUp, User } from "lucide-react";
import { API_BASE_URL } from "@/lib/api";

type Performance = {
  worker_id: string;
  name: string;
  role: string;
  district_name: string;
  records_count: number;
  unique_patients: number;
  performance_score: number;
};

export default function WorkerLeaderboard() {
  const [leaders, setLeaders] = useState<Performance[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/health-worker/leaderboard`)
      .then(res => res.json())
      .then(data => {
        setLeaders(data.leaderboard || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return <div className="lb-loading">Calculating Performance...</div>;

  return (
    <div className="lb-shell">
      <div className="lb-header">
        <Trophy size={16} style={{ color: "#fcd34d" }} />
        <span>Sahayak Performance Leaderboard</span>
      </div>

      <div className="lb-list">
        {leaders.map((worker, i) => (
          <div key={worker.worker_id} className={`lb-row ${i === 0 ? "lb-row--top" : ""}`}>
            <div className="lb-rank">
              {i === 0 ? <Medal size={16} style={{ color: "#fcd34d" }} /> : <span>#{i + 1}</span>}
            </div>
            
            <div className="lb-info">
              <div className="lb-name">{worker.name}</div>
              <div className="lb-meta">
                {worker.role.toUpperCase()} • {worker.district_name}
              </div>
            </div>

            <div className="lb-stats">
              <div className="lb-stat">
                <Target size={10} />
                <span>{worker.records_count}</span>
              </div>
              <div className="lb-score">
                <TrendingUp size={10} />
                <span>{worker.performance_score} pts</span>
              </div>
            </div>
          </div>
        ))}

        {leaders.length === 0 && (
          <div className="lb-empty">No performance data available yet.</div>
        )}
      </div>

      <style jsx>{`
        .lb-shell {
          background: rgba(24, 24, 27, 0.4);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 12px;
          overflow: hidden;
        }
        .lb-header {
          padding: 12px 16px;
          background: rgba(252, 211, 77, 0.05);
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 13px;
          font-weight: 600;
          color: #fcd34d;
          border-bottom: 1px solid rgba(252, 211, 77, 0.1);
        }
        .lb-list {
          padding: 8px;
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .lb-row {
          display: flex;
          align-items: center;
          padding: 10px 12px;
          border-radius: 8px;
          gap: 12px;
          transition: background 0.2s;
        }
        .lb-row:hover {
          background: rgba(255, 255, 255, 0.03);
        }
        .lb-row--top {
          background: rgba(252, 211, 77, 0.05);
          border: 1px solid rgba(252, 211, 77, 0.1);
        }
        .lb-rank {
          width: 24px;
          font-size: 12px;
          font-weight: 700;
          color: #71717a;
          display: flex;
          justify-content: center;
        }
        .lb-info {
          flex: 1;
        }
        .lb-name {
          font-size: 13px;
          font-weight: 500;
          color: #f4f4f5;
        }
        .lb-meta {
          font-size: 10px;
          color: #71717a;
          text-transform: uppercase;
        }
        .lb-stats {
          display: flex;
          align-items: center;
          gap: 12px;
        }
        .lb-stat, .lb-score {
          display: flex;
          align-items: center;
          gap: 4px;
          font-size: 11px;
        }
        .lb-stat { color: #a1a1aa; }
        .lb-score { color: #fcd34d; font-weight: 600; }
        .lb-loading, .lb-empty {
          padding: 30px;
          text-align: center;
          font-size: 12px;
          color: #71717a;
        }
      `}</style>
    </div>
  );
}
