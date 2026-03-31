import { useState } from "react";
import { Target, Trash2, Plus, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { api } from "../api";
import type { Goal, PMCProjection } from "../api";

interface GoalTrackerProps {
  goals: Goal[];
  projection: PMCProjection | null;
  onGoalsChange: () => void;
}

function daysUntil(dateStr: string): number {
  const target = new Date(dateStr + "T00:00:00");
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - now.getTime()) / 86400000);
}

function projectedCTLAt(projection: PMCProjection | null, dateStr: string): number | null {
  if (!projection) return null;
  const pt = projection.projection.find(p => p.date === dateStr);
  if (pt) return pt.maintain_ctl;
  // Interpolate: find last point before or at date
  const pts = projection.projection.filter(p => p.date <= dateStr);
  if (pts.length) return pts[pts.length - 1].maintain_ctl;
  return projection.current_ctl;
}

export function GoalTracker({ goals, projection, onGoalsChange }: GoalTrackerProps) {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [eventDate, setEventDate] = useState("");
  const [targetCTL, setTargetCTL] = useState("");
  const [saving, setSaving] = useState(false);

  const today = new Date().toISOString().slice(0, 10);
  const minDate = new Date();
  minDate.setDate(minDate.getDate() + 1);
  const minDateStr = minDate.toISOString().slice(0, 10);

  async function handleAdd() {
    if (!name.trim() || !eventDate) return;
    setSaving(true);
    try {
      await api.goalsCreate(
        name.trim(),
        eventDate,
        targetCTL ? parseFloat(targetCTL) : undefined,
      );
      setName(""); setEventDate(""); setTargetCTL("");
      setAdding(false);
      onGoalsChange();
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number) {
    await api.goalsDelete(id);
    onGoalsChange();
  }

  const inputStyle: React.CSSProperties = {
    background: "rgba(99,102,241,0.08)", border: "1px solid rgba(99,102,241,0.2)",
    borderRadius: "0.4rem", padding: "0.35rem 0.6rem",
    fontSize: "0.78rem", color: "#e2e8f0", outline: "none",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Target size={13} style={{ color: "#6366f1" }} />
          <span style={{ fontSize: "0.7rem", fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            Goals & Events
          </span>
        </div>
        {!adding && (
          <button
            onClick={() => setAdding(true)}
            style={{
              display: "flex", alignItems: "center", gap: "0.3rem",
              fontSize: "0.72rem", color: "#6366f1", background: "rgba(99,102,241,0.1)",
              border: "1px solid rgba(99,102,241,0.25)", borderRadius: "0.375rem",
              padding: "0.25rem 0.6rem", cursor: "pointer", fontWeight: 600,
            }}
          >
            <Plus size={11} /> Add goal
          </button>
        )}
      </div>

      {/* Add form */}
      {adding && (
        <div style={{
          background: "rgba(99,102,241,0.05)", border: "1px solid rgba(99,102,241,0.15)",
          borderRadius: "0.6rem", padding: "0.75rem", display: "flex", flexDirection: "column", gap: "0.5rem",
        }}>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <input
              style={{ ...inputStyle, flex: "1 1 140px" }}
              placeholder="Event name (e.g. Marathon)"
              value={name}
              onChange={e => setName(e.target.value)}
            />
            <input
              type="date"
              style={{ ...inputStyle, flex: "0 0 140px" }}
              min={minDateStr}
              value={eventDate}
              onChange={e => setEventDate(e.target.value)}
            />
            <input
              type="number"
              style={{ ...inputStyle, flex: "0 0 100px" }}
              placeholder="Target CTL"
              value={targetCTL}
              min={0}
              max={200}
              onChange={e => setTargetCTL(e.target.value)}
            />
          </div>
          <div style={{ display: "flex", gap: "0.4rem" }}>
            <button
              onClick={handleAdd}
              disabled={saving || !name.trim() || !eventDate}
              style={{
                fontSize: "0.75rem", fontWeight: 600, padding: "0.3rem 0.8rem",
                borderRadius: "0.375rem", cursor: saving || !name.trim() || !eventDate ? "default" : "pointer",
                background: saving || !name.trim() || !eventDate ? "rgba(99,102,241,0.2)" : "linear-gradient(135deg, #6366f1, #8b5cf6)",
                color: saving || !name.trim() || !eventDate ? "#475569" : "#fff",
                border: "1px solid rgba(99,102,241,0.3)",
              }}
            >
              {saving ? "Saving…" : "Save"}
            </button>
            <button
              onClick={() => { setAdding(false); setName(""); setEventDate(""); setTargetCTL(""); }}
              style={{
                fontSize: "0.75rem", color: "#64748b", background: "transparent",
                border: "none", cursor: "pointer", padding: "0.3rem 0.5rem",
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Goals list */}
      {goals.length === 0 && !adding && (
        <div style={{ fontSize: "0.75rem", color: "#475569", padding: "0.5rem 0" }}>
          No goals set. Add a race or event to track your CTL trajectory.
        </div>
      )}

      {goals.map(goal => {
        const days = daysUntil(goal.event_date);
        const projCTL = projectedCTLAt(projection, goal.event_date);
        const currentCTL = projection?.current_ctl ?? null;

        let status: "ahead" | "on-track" | "behind" | "unknown" = "unknown";
        let statusColor = "#64748b";
        let StatusIcon = Minus;

        if (goal.target_ctl != null && projCTL != null) {
          const gap = projCTL - goal.target_ctl;
          if (gap >= 2) { status = "ahead"; statusColor = "#10b981"; StatusIcon = TrendingUp; }
          else if (gap >= -3) { status = "on-track"; statusColor = "#6366f1"; StatusIcon = Minus; }
          else { status = "behind"; statusColor = "#ef4444"; StatusIcon = TrendingDown; }
        }

        const isPast = days < 0;

        return (
          <div key={goal.id} style={{
            background: "rgba(99,102,241,0.04)", border: "1px solid rgba(99,102,241,0.12)",
            borderRadius: "0.6rem", padding: "0.65rem 0.85rem",
            display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem",
            opacity: isPast ? 0.5 : 1,
          }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem", flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <span style={{ fontSize: "0.82rem", fontWeight: 600, color: "#e2e8f0" }}>{goal.name}</span>
                {!isPast && status !== "unknown" && (
                  <span style={{
                    display: "flex", alignItems: "center", gap: "0.2rem",
                    fontSize: "0.62rem", fontWeight: 700, color: statusColor,
                    background: `${statusColor}15`, border: `1px solid ${statusColor}30`,
                    borderRadius: "0.25rem", padding: "0.1rem 0.35rem",
                    textTransform: "uppercase",
                  }}>
                    <StatusIcon size={9} /> {status}
                  </span>
                )}
              </div>
              <div style={{ display: "flex", gap: "1rem", fontSize: "0.7rem", color: "#64748b" }}>
                <span>{goal.event_date}</span>
                <span>{isPast ? `${Math.abs(days)}d ago` : `${days}d away`}</span>
                {currentCTL != null && <span>CTL now: <span style={{ color: "#3b82f6" }}>{currentCTL}</span></span>}
                {goal.target_ctl != null && <span>Target: <span style={{ color: "#a78bfa" }}>{goal.target_ctl}</span></span>}
                {projCTL != null && !isPast && goal.target_ctl != null && (
                  <span>Projected: <span style={{ color: statusColor }}>{projCTL.toFixed(1)}</span></span>
                )}
              </div>
            </div>
            <button
              onClick={() => handleDelete(goal.id)}
              style={{ color: "#475569", background: "transparent", border: "none", cursor: "pointer", padding: "0.25rem", flexShrink: 0 }}
              title="Remove goal"
            >
              <Trash2 size={13} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
