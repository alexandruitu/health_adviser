import type { ReadinessDay } from "../api";

// ── Color scale ───────────────────────────────────────────────────────────────
export function readinessColor(score: number): string {
  if (score >= 85) return "#10b981";   // Peak     – emerald
  if (score >= 70) return "#34d399";   // High     – light green
  if (score >= 55) return "#f59e0b";   // Moderate – amber
  if (score >= 40) return "#f97316";   // Low      – orange
  return "#ef4444";                    // Recovery – red
}

// ── Plain-English insights ────────────────────────────────────────────────────
function hrvInsight(d: ReadinessDay): string | null {
  if (!d.hrv_val || !d.hrv_baseline) return null;
  const pct = Math.round(((d.hrv_val - d.hrv_baseline) / d.hrv_baseline) * 100);
  if (pct >= 15)  return `${pct}% above your 30-day baseline — strong recovery signal`;
  if (pct >= 5)   return `Slightly elevated vs baseline — well recovered`;
  if (pct >= -5)  return `At baseline (${d.hrv_val} ms) — normal recovery`;
  if (pct >= -15) return `${Math.abs(pct)}% below baseline — some residual fatigue`;
  return `${Math.abs(pct)}% below baseline (${d.hrv_val} ms vs ${d.hrv_baseline} ms) — body still recovering`;
}

function sleepInsight(d: ReadinessDay): string | null {
  if (!d.sleep_raw || !d.sleep_baseline) return null;
  const diff = Math.round(d.sleep_raw - d.sleep_baseline);
  if (diff >= 8)  return `Score ${d.sleep_raw} — well above your usual ${d.sleep_baseline}`;
  if (diff >= 0)  return `Score ${d.sleep_raw} — on par with your average (${d.sleep_baseline})`;
  if (diff >= -8) return `Score ${d.sleep_raw} — slightly below your usual ${d.sleep_baseline}`;
  return `Score ${d.sleep_raw} — notably below your usual ${d.sleep_baseline}`;
}

function batteryInsight(d: ReadinessDay): string | null {
  if (d.battery_val == null) return null;
  if (d.battery_val >= 60) return `+${d.battery_val} pts recharged — excellent overnight recovery`;
  if (d.battery_val >= 40) return `+${d.battery_val} pts recharged — adequate recovery`;
  if (d.battery_val >= 20) return `Only +${d.battery_val} pts — sleep didn't fully recharge you`;
  return `+${d.battery_val} pts — very low overnight recovery`;
}

function tsbInsight(d: ReadinessDay): string | null {
  if (d.tsb == null) return null;
  if (d.tsb >= 10)  return `TSB ${d.tsb > 0 ? "+" : ""}${d.tsb} — well rested, low accumulated load`;
  if (d.tsb >= 0)   return `TSB +${d.tsb} — slightly fresh, good form`;
  if (d.tsb >= -15) return `TSB ${d.tsb} — neutral zone, manageable fatigue`;
  if (d.tsb >= -30) return `TSB ${d.tsb} — moderate fatigue from recent training block`;
  return `TSB ${d.tsb} — significant fatigue, prioritise recovery`;
}

function recommendation(score: number): string {
  if (score >= 85) return "✅ Ready for high-intensity or race-effort training";
  if (score >= 70) return "🟢 Good for quality work — threshold or tempo";
  if (score >= 55) return "🟡 Stick to aerobic or technique-focused sessions";
  if (score >= 40) return "🟠 Active recovery only — easy movement, no load";
  return "🔴 Rest day — let your body fully recover";
}

// ── Sub-components ────────────────────────────────────────────────────────────
function ComponentBar({
  value, label, color, hint,
}: { value?: number | null; label: string; color: string; hint?: string | null }) {
  if (value == null) return null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.72rem" }}>
        <span style={{ color: "#94a3b8", width: "5.5rem", flexShrink: 0, fontWeight: 600 }}>
          {label}
        </span>
        <div style={{ flex: 1, height: "7px", borderRadius: "4px", background: "#1e2130", overflow: "hidden" }}>
          <div style={{
            width: `${Math.min(100, value)}%`, height: "100%",
            borderRadius: "4px", background: color, transition: "width 0.7s ease",
          }} />
        </div>
        <span style={{ color, width: "2.2rem", textAlign: "right", fontWeight: 700 }}>
          {Math.round(value)}
        </span>
      </div>
      {hint && (
        <div style={{ fontSize: "0.67rem", color: "#475569", paddingLeft: "6rem" }}>
          {hint}
        </div>
      )}
    </div>
  );
}

// ── Main exported card ────────────────────────────────────────────────────────
export function ReadinessCard({
  today,
  period,
}: {
  today?: ReadinessDay;
  period?: ReadinessDay[];
}) {
  const series = period ?? [];
  if (!today && !series.length) return null;

  const score    = today?.readiness ?? 0;
  const color    = readinessColor(score);
  const label    = today?.label ?? "—";
  const avgScore = series.length > 1
    ? Math.round(series.reduce((s, d) => s + d.readiness, 0) / series.length)
    : null;

  return (
    <div style={{
      background: "linear-gradient(135deg, #1a1d27 0%, #1e2233 100%)",
      border: `1px solid ${color}44`,
      borderRadius: "1rem",
      padding: "1.25rem 1.5rem",
      display: "grid",
      gridTemplateColumns: "auto 1fr",
      gap: "1.75rem",
      alignItems: "start",
    }}>

      {/* ── Left: score dial ── */}
      <div style={{
        display: "flex", flexDirection: "column",
        alignItems: "center", gap: "0.15rem", minWidth: "7.5rem",
      }}>
        <div style={{
          fontSize: "0.6rem", fontWeight: 700, color: "#475569",
          textTransform: "uppercase", letterSpacing: "0.12em",
        }}>
          Readiness
        </div>
        <div style={{
          fontSize: "4rem", fontWeight: 800, lineHeight: 1,
          color, textShadow: `0 0 28px ${color}55`,
        }}>
          {Math.round(score)}
        </div>
        <div style={{
          fontSize: "0.78rem", fontWeight: 700, color,
          border: `1px solid ${color}55`, borderRadius: "999px",
          padding: "0.2rem 0.85rem",
        }}>
          {label}
        </div>
        {avgScore != null && series.length > 1 && (
          <div style={{ fontSize: "0.62rem", color: "#475569", marginTop: "0.3rem", textAlign: "center" }}>
            avg {avgScore}<br />{series.length} nights
          </div>
        )}
      </div>

      {/* ── Right: recommendation + bars + training load ── */}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>

        {/* Training recommendation */}
        <div style={{
          fontSize: "0.78rem", color: "#cbd5e1", fontWeight: 500,
          paddingBottom: "0.6rem", borderBottom: "1px solid #2a2d3a",
        }}>
          {recommendation(score)}
        </div>

        {/* Component bars */}
        <ComponentBar
          value={today?.hrv_score}
          label="HRV (40%)"
          color="#8b5cf6"
          hint={today ? hrvInsight(today) : null}
        />
        <ComponentBar
          value={today?.sleep_score}
          label="Sleep (35%)"
          color="#0ea5e9"
          hint={today ? sleepInsight(today) : null}
        />
        <ComponentBar
          value={today?.battery_score}
          label="Battery (25%)"
          color="#10b981"
          hint={today ? batteryInsight(today) : null}
        />

        {/* Training load footer */}
        {today?.tsb != null && (
          <div style={{
            fontSize: "0.68rem", color: "#475569",
            paddingTop: "0.4rem", borderTop: "1px solid #2a2d3a",
          }}>
            <span style={{ color: "#64748b" }}>Training load · </span>
            {tsbInsight(today)}
            <span style={{ color: "#374151", marginLeft: "0.75rem" }}>
              ATL {today.atl} · CTL {today.ctl}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
