"use client";
import { useEffect, useState } from "react";
import { Bell, User, Calendar, Activity, AlertCircle } from "lucide-react";
import { API_BASE_URL } from "@/lib/api";

type OutreachTask = {
  type: string;
  patient_name: string;
  reason: string;
  priority: "high" | "medium" | "low";
};

export default function OutreachTaskList() {
  const [tasks, setTasks] = useState<OutreachTask[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/health-worker/outreach-tasks`)
      .then(res => res.json())
      .then(data => {
        setTasks(data.tasks || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading && tasks.length === 0) return null;

  return (
    <div className="ot-shell">
      <div className="ot-header">
        <Bell size={14} className="pulse" />
        <span>Proactive Outreach Tasks</span>
      </div>

      <div className="ot-list">
        {tasks.map((task, i) => (
          <div key={i} className={`ot-item ot-item--${task.priority}`}>
            <div className="ot-icon">
              {task.type === "vitals_reminder" ? <Activity size={14} /> : <AlertCircle size={14} />}
            </div>
            <div className="ot-info">
              <div className="ot-patient">{task.patient_name}</div>
              <div className="ot-reason">{task.reason}</div>
            </div>
            <button className="ot-action-btn">Follow up</button>
          </div>
        ))}

        {tasks.length === 0 && (
          <div className="ot-empty">No pending outreach tasks.</div>
        )}
      </div>

      <style jsx>{`
        .ot-shell {
          background: rgba(24, 24, 27, 0.4);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 12px;
          overflow: hidden;
          margin-bottom: 20px;
        }
        .ot-header {
          padding: 10px 16px;
          background: rgba(147, 197, 253, 0.05);
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 13px;
          font-weight: 600;
          color: #93c5fd;
          border-bottom: 1px solid rgba(147, 197, 253, 0.1);
        }
        .ot-list {
          padding: 8px;
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .ot-item {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 10px;
          border-radius: 8px;
          background: rgba(255,255,255,0.02);
          border: 1px solid rgba(255,255,255,0.05);
        }
        .ot-item--high { border-color: rgba(248, 113, 113, 0.2); background: rgba(248, 113, 113, 0.02); }
        .ot-icon { color: #71717a; }
        .ot-item--high .ot-icon { color: #f87171; }
        .ot-info { flex: 1; }
        .ot-patient { font-size: 13px; font-weight: 500; color: #f4f4f5; }
        .ot-reason { font-size: 11px; color: #a1a1aa; }
        .ot-action-btn {
          font-size: 11px;
          padding: 4px 10px;
          border-radius: 6px;
          background: rgba(255,255,255,0.05);
          border: 1px solid rgba(255,255,255,0.1);
          color: #f4f4f5;
          cursor: pointer;
        }
        .ot-action-btn:hover { background: rgba(255,255,255,0.1); }
        .ot-empty { padding: 20px; text-align: center; color: #71717a; font-size: 12px; }
        @keyframes pulse {
          0% { opacity: 1; }
          50% { opacity: 0.5; }
          100% { opacity: 1; }
        }
        .pulse { animation: pulse 2s infinite; }
      `}</style>
    </div>
  );
}
