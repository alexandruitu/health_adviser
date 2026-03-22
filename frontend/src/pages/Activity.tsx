import { useState, useMemo } from "react";
import {
  ResponsiveContainer, ComposedChart, BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine, ReferenceArea, Area,
} from "recharts";
import { useApi } from "../hooks/useApi";
import { api } from "../api";
import type { Resolution } from "../api";

// ─── constants ────────────────────────────────────────────────────────────────

const RUN_COLOR   = "#6366f1";
const BIKE_COLOR  = "#f59e0b";
const CTL_COLOR   = "#3b82f6";
const ATL_COLOR   = "#ef4444";
const TSB_COLOR   = "#10b981";
const HRV_COLOR   = "#8b5cf6";

const YEAR_COLORS: Record<string, string> = {
  "2018": "#475569", "2019": "#64748b", "2020": "#3b82f6",
  "2021": "#6366f1", "2022": "#8b5cf6", "2023": "#06b6d4",
  "2024": "#10b981", "2025": "#f59e0b", "2026": "#ef4444",
};

const SURFACE = { backgroundColor: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: "0.75rem" };
const TOOLTIP_STYLE = { backgroundColor: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: "0.5rem", color: "#e2e8f0", fontSize: "0.75rem" };
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const fmtTip = (v: any, name?: string): [string, string] => [v != null ? `${Number(v).toFixed(1)}` : "—", name ?? ""];
const axisProps = { stroke: "#2a2d3a", tick: { fill: "#64748b", fontSize: 11 } };
const grid = <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3a" />;

// ─── date helpers ─────────────────────────────────────────────────────────────

const today = new Date().toISOString().slice(0, 10);

function daysAgo(n: number) {
  const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().slice(0, 10);
}

const ytdStart = `${new Date().getFullYear()}-01-01`;

const DEFAULTS: Record<Resolution, { start: string; end: string }> = {
  week:  { start: daysAgo(16 * 7), end: today },
  month: { start: ytdStart,         end: today },
  year:  { start: "2018-01-01",     end: today },
};

function fmtPeriod(p: string, res: Resolution): string {
  if (res === "year") return p;
  if (res === "month") {
    const [y, m] = p.split("-");
    return new Date(+y, +m - 1).toLocaleString("en", { month: "short", year: "2-digit" });
  }
  // week: "YYYY-MM-DD" → "Jan 6"
  const d = new Date(p + "T12:00:00");
  return d.toLocaleString("en", { month: "short", day: "numeric" });
}

// ─── small reusable components ────────────────────────────────────────────────

function Pill({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} style={{
      padding: "0.25rem 0.75rem", borderRadius: "0.375rem", fontSize: "0.75rem",
      fontWeight: 600, cursor: "pointer", border: "1px solid #3a3d4a",
      backgroundColor: active ? "#6366f1" : "#2a2d3a",
      color: active ? "#fff" : "#94a3b8",
    }}>{label}</button>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <div style={{ color: "#94a3b8", fontSize: "0.75rem", fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase" as const, marginBottom: "0.75rem" }}>{children}</div>;
}

function StatBadge({ label, value, unit, color }: { label: string; value: string | number | null; unit?: string; color?: string }) {
  return (
    <div style={{ ...SURFACE, padding: "0.75rem 1rem" }}>
      <div style={{ color: "#64748b", fontSize: "0.7rem", marginBottom: "0.2rem" }}>{label}</div>
      <span style={{ color: value == null ? "#64748b" : (color ?? "#e2e8f0"), fontSize: "1.25rem", fontWeight: 700 }}>
        {value ?? "—"}
      </span>
      {unit && value != null && <span style={{ color: "#64748b", fontSize: "0.7rem", marginLeft: "0.25rem" }}>{unit}</span>}
    </div>
  );
}

function Spinner() {
  return <div style={{ height: 220, display: "flex", alignItems: "center", justifyContent: "center", color: "#64748b" }}>Loading…</div>;
}

// ─── main component ───────────────────────────────────────────────────────────

export function Activity() {
  const [res, setRes]       = useState<Resolution>("month");
  const [range, setRange]   = useState(DEFAULTS.month);
  const [volMetric, setVM]  = useState<"min" | "km">("min");
  const [yoySports, setYoYSports] = useState<Set<"running" | "cycling">>(new Set(["running"]));
  const [yoyMetric, setYM]        = useState<"min" | "km">("min");
  const [hiddenYears, setHY]      = useState<Set<string>>(new Set());
  const [panelYear, setPanelYear] = useState<string>(String(new Date().getFullYear()));
  const PANEL_YEARS = Object.keys(YEAR_COLORS).filter(y => parseInt(y) >= 2019).sort();

  function selectPanelYear(y: string) {
    setPanelYear(y);
    const isCurrentYear = y === String(new Date().getFullYear());
    setRange({ start: `${y}-01-01`, end: isCurrentYear ? today : `${y}-12-31` });
    if (res !== "month") setRes("month");
  }

  function toggleSport(s: "running" | "cycling") {
    setYoYSports(prev => {
      const next = new Set(prev);
      if (next.has(s) && next.size === 1) return prev; // keep at least one
      next.has(s) ? next.delete(s) : next.add(s);
      return next;
    });
  }

  function switchRes(r: Resolution) {
    setRes(r);
    setRange(DEFAULTS[r]);
  }

  const { start, end } = range;

  // ── data fetching ──
  const { data: volRaw,  loading: volLoading  } = useApi(() => api.trainingVolume(res, start, end), [res, start, end]);
  const { data: pmcRaw,  loading: pmcLoading  } = useApi(() => api.trainingPMC(start, end), [start, end]);
  const { data: yoyRunRaw } = useApi(() => api.trainingYoY("running"), []);
  const { data: yoyCycRaw } = useApi(() => api.trainingYoY("cycling"), []);
  const { data: hrvRaw,  loading: hrvLoading  } = useApi(() => api.trainingHRV(start, end), [start, end]);
  const { data: insRaw,  loading: insLoading  } = useApi(() => api.trainingStravaInsights(res, start, end), [res, start, end]);
  const { data: hrZoneRaw } = useApi(() => api.trainingHRZones(start, end), [start, end]);
  const { data: runPRRaw  } = useApi(() => api.trainingRecords("running"), []);
  const { data: cycPRRaw  } = useApi(() => api.trainingRecords("cycling"), []);

  // ── format volume labels ──
  const volData = useMemo(() =>
    (volRaw ?? []).map(r => ({ ...r, label: fmtPeriod(r.period, res) })),
    [volRaw, res]
  );

  // ── PMC: only show 1-in-N points for readability based on range ──
  const pmcData = useMemo(() => {
    const raw = pmcRaw ?? [];
    const step = res === "week" ? 1 : res === "month" ? 3 : 7;
    const sampled = raw.filter((_, i) => i % step === 0);
    // Always include the last point so the displayed value matches the header badge
    if (raw.length && sampled[sampled.length - 1] !== raw[raw.length - 1]) {
      sampled.push(raw[raw.length - 1]);
    }
    return sampled.map(r => ({ ...r, label: r.date.slice(5) }));
  }, [pmcRaw, res]);

  // ── YoY: merge run + cycling into one dataset with prefixed keys ──
  const yoyYears = useMemo(() => {
    const all = new Set([...(yoyRunRaw?.years ?? []), ...(yoyCycRaw?.years ?? [])]);
    return [...all].filter(y => parseInt(y) >= 2019).sort();
  }, [yoyRunRaw, yoyCycRaw]);

  const yoyData = useMemo(() => {
    const runByLabel = Object.fromEntries((yoyRunRaw?.data ?? []).map((r: Record<string, unknown>) => [r.label, r]));
    const cycByLabel = Object.fromEntries((yoyCycRaw?.data ?? []).map((r: Record<string, unknown>) => [r.label, r]));
    const labels = (yoyRunRaw?.data ?? yoyCycRaw?.data ?? []).map((r: Record<string, unknown>) => r.label as string);
    return labels.map((label: string) => {
      const row: Record<string, unknown> = { label };
      yoyYears.forEach(y => {
        row[`run_min_${y}`] = (runByLabel[label] as Record<string, unknown>)?.[`min_${y}`] ?? 0;
        row[`run_km_${y}`]  = (runByLabel[label] as Record<string, unknown>)?.[`km_${y}`]  ?? 0;
        row[`cyc_min_${y}`] = (cycByLabel[label] as Record<string, unknown>)?.[`min_${y}`] ?? 0;
        row[`cyc_km_${y}`]  = (cycByLabel[label] as Record<string, unknown>)?.[`km_${y}`]  ?? 0;
      });
      return row;
    });
  }, [yoyRunRaw, yoyCycRaw, yoyYears]);

  const yoyKey = (y: string, sport: "running" | "cycling") =>
    sport === "running" ? `run_${yoyMetric}_${y}` : `cyc_${yoyMetric}_${y}`;

  // ── HRV data ──
  const hrvData = hrvRaw ?? [];

  // ── Strava insights ──
  const insData = useMemo(() =>
    (insRaw ?? []).map(r => ({ ...r, label: fmtPeriod(r.period, res) })),
    [insRaw, res]
  );
  const hasInsights = insData.some(r => r.run_elevation_m > 0 || r.cyc_elevation_m > 0);


  const insRunElev  = insData.reduce((s, r) => s + (r.run_elevation_m ?? 0), 0);
  const insCycElev  = insData.reduce((s, r) => s + (r.cyc_elevation_m ?? 0), 0);
  const avgRunHR      = insData.filter(r => r.run_avg_hr > 0).reduce((s, r, _i, a) => s + r.run_avg_hr / a.length, 0);
  const avgRunPace    = insData.filter(r => r.run_avg_pace > 0).reduce((s, r, _i, a) => s + r.run_avg_pace / a.length, 0);
  const totalSuffer   = insData.reduce((s, r) => s + (r.run_suffer ?? 0) + (r.cyc_suffer ?? 0), 0);

  // ── summary stats from volData ──
  const totalRunMin  = volData.reduce((s, r) => s + (r.running_min ?? 0), 0);
  const totalCycMin  = volData.reduce((s, r) => s + (r.cycling_min ?? 0), 0);
  const totalRunKm   = volData.reduce((s, r) => s + (r.running_km ?? 0), 0);
  const totalCycKm   = volData.reduce((s, r) => s + (r.cycling_km ?? 0), 0);
  const runSessions  = volData.reduce((s, r) => s + (r.running_sessions ?? 0), 0);
  const cycSessions  = volData.reduce((s, r) => s + (r.cycling_sessions ?? 0), 0);
  const longestRun   = Math.max(0, ...volData.map(r => r.longest_run_min ?? 0));
  const longestRide  = Math.max(0, ...volData.map(r => r.longest_ride_min ?? 0));
  const totalRunElev = volData.reduce((s, r) => s + (r.running_elev_m ?? 0), 0);
  const totalCycElev = volData.reduce((s, r) => s + (r.cycling_elev_m ?? 0), 0);
  const latestCTL    = pmcData.length ? pmcData[pmcData.length - 1].ctl : null;
  const latestTSB    = pmcData.length ? pmcData[pmcData.length - 1].tsb : null;
  const latestDate   = pmcData.length ? pmcData[pmcData.length - 1].date : null;


  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>

      {/* ── Header controls ── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.75rem" }}>
        <h1 style={{ color: "#e2e8f0", fontSize: "1.25rem", fontWeight: 600, margin: 0 }}>Activity</h1>

        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
          {/* Resolution pills */}
          <div style={{ display: "flex", gap: "0.25rem", backgroundColor: "#13151f", padding: "0.25rem", borderRadius: "0.5rem", border: "1px solid #2a2d3a" }}>
            {(["week", "month", "year"] as Resolution[]).map(r => (
              <Pill key={r} label={r === "week" ? "W" : r === "month" ? "M" : "Y"} active={res === r} onClick={() => switchRes(r)} />
            ))}
          </div>
          {/* Date range */}
          <input type="date" value={start} max={end}
            onChange={e => {
              const v = e.target.value;
              setRange(r => ({ start: v > r.end ? r.end : v, end: r.end }));
            }}
            style={{ backgroundColor: "#2a2d3a", color: "#94a3b8", border: "1px solid #3a3d4a", borderRadius: "0.375rem", padding: "0.25rem 0.5rem", fontSize: "0.75rem" }} />
          <span style={{ color: "#64748b" }}>→</span>
          <input type="date" value={end} min={start} max={today}
            onChange={e => {
              const v = e.target.value > today ? today : e.target.value;
              setRange(r => ({ start: r.start, end: v < r.start ? r.start : v }));
            }}
            style={{ backgroundColor: "#2a2d3a", color: "#94a3b8", border: "1px solid #3a3d4a", borderRadius: "0.375rem", padding: "0.25rem 0.5rem", fontSize: "0.75rem" }} />
        </div>
      </div>

      {/* ── Summary cards ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "0.625rem" }}>
        <StatBadge label="Running sessions" value={runSessions} color={RUN_COLOR} />
        <StatBadge label="Running time" value={`${(totalRunMin / 60).toFixed(1)}`} unit="h" color={RUN_COLOR} />
        <StatBadge label="Running distance" value={totalRunKm.toFixed(0)} unit="km" color={RUN_COLOR} />
        <StatBadge label="Run elevation" value={totalRunElev > 0 ? Math.round(totalRunElev).toLocaleString() : null} unit="m" color={RUN_COLOR} />
        <StatBadge label="Longest run" value={longestRun > 0 ? `${(longestRun / 60).toFixed(1)}` : null} unit="h" color={RUN_COLOR} />
        <StatBadge label="Cycling sessions" value={cycSessions} color={BIKE_COLOR} />
        <StatBadge label="Cycling time" value={`${(totalCycMin / 60).toFixed(1)}`} unit="h" color={BIKE_COLOR} />
        <StatBadge label="Cycling distance" value={totalCycKm.toFixed(0)} unit="km" color={BIKE_COLOR} />
        <StatBadge label="Cyc elevation" value={totalCycElev > 0 ? Math.round(totalCycElev).toLocaleString() : null} unit="m" color={BIKE_COLOR} />
        <StatBadge label="Longest ride" value={longestRide > 0 ? `${(longestRide / 60).toFixed(1)}` : null} unit="h" color={BIKE_COLOR} />
      </div>

      {/* ── A: Volume chart ── */}
      <div style={{ ...SURFACE, padding: "1.25rem" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
          <SectionTitle>Training Volume — Running vs Cycling</SectionTitle>
          <div style={{ display: "flex", gap: "0.25rem" }}>
            <Pill label="Time" active={volMetric === "min"} onClick={() => setVM("min")} />
            <Pill label="km" active={volMetric === "km"} onClick={() => setVM("km")} />
          </div>
        </div>
        {volLoading ? <Spinner /> : volData.length === 0 || (runSessions + cycSessions === 0) ? (
          <div style={{ height: 240, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", color: "#64748b", gap: "0.5rem" }}>
            <div style={{ fontSize: "1.25rem" }}>—</div>
            <div style={{ fontSize: "0.8rem" }}>No workouts recorded in this period</div>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={volData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              {grid}
              <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" />
              <YAxis {...axisProps} tickFormatter={v => volMetric === "min" ? `${(v/60).toFixed(0)}h` : `${v}km`} />
              <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v, name) => [
                v == null || !Number.isFinite(Number(v)) ? "—" : volMetric === "min" ? `${(Number(v)/60).toFixed(1)}h` : `${Number(v).toFixed(0)}km`,
                name === (volMetric === "min" ? "running_min" : "running_km") ? "Running" : "Cycling"
              ]} />
              <Legend wrapperStyle={{ fontSize: 11, color: "#64748b" }}
                formatter={n => n.includes("run") ? "Running" : "Cycling"} />
              <Bar dataKey={volMetric === "min" ? "running_min" : "running_km"}
                name={volMetric === "min" ? "running_min" : "running_km"}
                fill={RUN_COLOR} radius={[3, 3, 0, 0]} maxBarSize={24} />
              <Bar dataKey={volMetric === "min" ? "cycling_min" : "cycling_km"}
                name={volMetric === "min" ? "cycling_min" : "cycling_km"}
                fill={BIKE_COLOR} radius={[3, 3, 0, 0]} maxBarSize={24} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* ── B: PMC ── */}

      <div style={{ ...SURFACE, padding: "1.25rem" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
          <SectionTitle>Performance Management — Fitness / Fatigue / Form</SectionTitle>
          <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
            {latestDate && (
              <span style={{ fontSize: "0.65rem", color: "#475569" }}>{latestDate.slice(5)}</span>
            )}
            <span style={{ fontSize: "0.7rem", color: "#64748b" }}>
              CTL (fitness) <span style={{ color: latestCTL != null ? CTL_COLOR : "#64748b" }}>{latestCTL ?? "—"}</span>
            </span>
            <span style={{ fontSize: "0.7rem", color: "#64748b" }}>
              TSB (form) <span style={{ color: latestTSB != null ? (latestTSB >= 0 ? TSB_COLOR : "#f97316") : "#64748b" }}>{latestTSB ?? "—"}</span>
            </span>
          </div>
        </div>
        <div style={{ fontSize: "0.65rem", color: "#64748b", marginBottom: "0.5rem" }}>
          Banister TRIMP model · HR-weighted load · ATL τ=7d · CTL τ=42d · rest HR 50 bpm · max HR 185 bpm
        </div>
        {/* TSB zone legend */}
        <div style={{ display: "flex", gap: "1rem", fontSize: "0.6rem", color: "#64748b", marginBottom: "0.75rem" }}>
          <span><span style={{ display: "inline-block", width: 10, height: 10, background: "rgba(239,68,68,0.15)", borderRadius: 2, marginRight: 4 }} />Danger &lt; −30</span>
          <span><span style={{ display: "inline-block", width: 10, height: 10, background: "rgba(251,146,60,0.12)", borderRadius: 2, marginRight: 4 }} />Build −10 to −30</span>
          <span><span style={{ display: "inline-block", width: 10, height: 10, background: "rgba(16,185,129,0.15)", borderRadius: 2, marginRight: 4 }} />Race-ready +5 to +25</span>
        </div>
        {pmcLoading ? <Spinner /> : (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={pmcData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              {grid}
              <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" />
              <YAxis {...axisProps} />
              <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v, n) => [
                typeof v === "number" ? v.toFixed(1) : v,
                ({ ctl: "Fitness (CTL)", atl: "Fatigue (ATL)", tsb: "Form (TSB)" } as Record<string, string>)[String(n)] ?? String(n)
              ]} />
              <Legend wrapperStyle={{ fontSize: 11, color: "#64748b" }}
                formatter={(n: string) => ({ ctl: "Fitness (CTL)", atl: "Fatigue (ATL)", tsb: "Form (TSB)" } as Record<string, string>)[n] ?? n} />
              {/* TSB zone bands */}
              <ReferenceArea y1={-30} y2={-200} fill="rgba(239,68,68,0.08)" ifOverflow="hidden" />
              <ReferenceArea y1={-10} y2={-30}  fill="rgba(251,146,60,0.07)" ifOverflow="hidden" />
              <ReferenceArea y1={5}   y2={25}   fill="rgba(16,185,129,0.10)" ifOverflow="hidden" />
              {/* Zone boundary lines */}
              <ReferenceLine y={0}   stroke="#2a2d3a" strokeDasharray="4 4" />
              <ReferenceLine y={-10} stroke="#f97316" strokeDasharray="3 3" strokeOpacity={0.4}
                label={{ value: "−10", position: "right", fill: "#f97316", fontSize: 9, opacity: 0.7 }} />
              <ReferenceLine y={-30} stroke="#ef4444" strokeDasharray="3 3" strokeOpacity={0.4}
                label={{ value: "−30", position: "right", fill: "#ef4444", fontSize: 9, opacity: 0.7 }} />
              <ReferenceLine y={5}   stroke="#10b981" strokeDasharray="3 3" strokeOpacity={0.4}
                label={{ value: "+5", position: "right", fill: "#10b981", fontSize: 9, opacity: 0.7 }} />
              <ReferenceLine y={25}  stroke="#10b981" strokeDasharray="3 3" strokeOpacity={0.4}
                label={{ value: "+25", position: "right", fill: "#10b981", fontSize: 9, opacity: 0.7 }} />
              <Line type="monotone" dataKey="ctl" name="ctl" stroke={CTL_COLOR} dot={false} strokeWidth={2} />
              <Line type="monotone" dataKey="atl" name="atl" stroke={ATL_COLOR} dot={false} strokeWidth={2} />
              <Line type="monotone" dataKey="tsb" name="tsb" stroke={TSB_COLOR} dot={false} strokeWidth={1.5} strokeDasharray="4 2" />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* ── D+E: Running & Cycling side-by-side ── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>

        {/* Running panel */}
        <div style={{ ...SURFACE, padding: "1.25rem" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
            <SectionTitle>🏃 Running</SectionTitle>
            <div style={{ display: "flex", gap: "0.25rem", flexWrap: "wrap" }}>
              {PANEL_YEARS.map(y => (
                <button key={y} onClick={() => selectPanelYear(y)} style={{
                  padding: "0.15rem 0.5rem", borderRadius: "0.375rem", fontSize: "0.7rem",
                  fontWeight: 600, cursor: "pointer", border: "1px solid",
                  borderColor: panelYear === y ? (YEAR_COLORS[y] ?? "#6366f1") : "#2a2d3a",
                  color: panelYear === y ? (YEAR_COLORS[y] ?? "#6366f1") : "#64748b",
                  background: panelYear === y ? `${YEAR_COLORS[y] ?? "#6366f1"}18` : "transparent",
                }}>{y}</button>
              ))}
            </div>
          </div>
          {volLoading ? <Spinner /> : (
            <>
              <ResponsiveContainer width="100%" height={160}>
                <BarChart data={volData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                  {grid}
                  <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" />
                  <YAxis {...axisProps} tickFormatter={v => volMetric === "min" ? `${(v/60).toFixed(0)}h` : `${v}km`} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [
                    v == null || !Number.isFinite(Number(v)) ? "—" : volMetric === "min" ? `${(Number(v)/60).toFixed(1)}h` : `${Number(v).toFixed(0)}km`, "Running"
                  ]} />
                  <Bar dataKey={volMetric === "min" ? "running_min" : "running_km"}
                    fill={RUN_COLOR} radius={[3, 3, 0, 0]} maxBarSize={20} />
                </BarChart>
              </ResponsiveContainer>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", marginTop: "0.75rem" }}>
                <StatBadge label="Sessions" value={runSessions} color={RUN_COLOR} />
                <StatBadge label="Total km" value={totalRunKm.toFixed(0)} unit="km" color={RUN_COLOR} />
                <StatBadge label="Total time" value={`${(totalRunMin/60).toFixed(1)}`} unit="h" color={RUN_COLOR} />
                <StatBadge label="Longest" value={longestRun > 0 ? `${(longestRun/60).toFixed(1)}` : null} unit="h" color={RUN_COLOR} />
              </div>
            </>
          )}
        </div>

        {/* Cycling panel */}
        <div style={{ ...SURFACE, padding: "1.25rem" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
            <SectionTitle>🚴 Cycling</SectionTitle>
            <div style={{ display: "flex", gap: "0.25rem", flexWrap: "wrap" }}>
              {PANEL_YEARS.map(y => (
                <button key={y} onClick={() => selectPanelYear(y)} style={{
                  padding: "0.15rem 0.5rem", borderRadius: "0.375rem", fontSize: "0.7rem",
                  fontWeight: 600, cursor: "pointer", border: "1px solid",
                  borderColor: panelYear === y ? (YEAR_COLORS[y] ?? "#f59e0b") : "#2a2d3a",
                  color: panelYear === y ? (YEAR_COLORS[y] ?? "#f59e0b") : "#64748b",
                  background: panelYear === y ? `${YEAR_COLORS[y] ?? "#f59e0b"}18` : "transparent",
                }}>{y}</button>
              ))}
            </div>
          </div>
          {volLoading ? <Spinner /> : (
            <>
              <ResponsiveContainer width="100%" height={160}>
                <BarChart data={volData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                  {grid}
                  <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" />
                  <YAxis {...axisProps} tickFormatter={v => volMetric === "min" ? `${(v/60).toFixed(0)}h` : `${v}km`} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [
                    v == null || !Number.isFinite(Number(v)) ? "—" : volMetric === "min" ? `${(Number(v)/60).toFixed(1)}h` : `${Number(v).toFixed(0)}km`, "Cycling"
                  ]} />
                  <Bar dataKey={volMetric === "min" ? "cycling_min" : "cycling_km"}
                    fill={BIKE_COLOR} radius={[3, 3, 0, 0]} maxBarSize={20} />
                </BarChart>
              </ResponsiveContainer>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", marginTop: "0.75rem" }}>
                <StatBadge label="Sessions" value={cycSessions} color={BIKE_COLOR} />
                <StatBadge label="Total km" value={totalCycKm.toFixed(0)} unit="km" color={BIKE_COLOR} />
                <StatBadge label="Total time" value={`${(totalCycMin/60).toFixed(1)}`} unit="h" color={BIKE_COLOR} />
                <StatBadge label="Longest" value={longestRide > 0 ? `${(longestRide/60).toFixed(1)}` : null} unit="h" color={BIKE_COLOR} />
              </div>
            </>
          )}
        </div>
      </div>

      {/* ── J: Year-over-Year ── */}
      <div style={{ ...SURFACE, padding: "1.25rem" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem", flexWrap: "wrap", gap: "0.5rem" }}>
          <SectionTitle>Year-over-Year Comparison</SectionTitle>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <div style={{ display: "flex", gap: "0.25rem" }}>
              <Pill label="Running" active={yoySports.has("running")} onClick={() => toggleSport("running")} />
              <Pill label="Cycling" active={yoySports.has("cycling")} onClick={() => toggleSport("cycling")} />
            </div>
            <div style={{ display: "flex", gap: "0.25rem" }}>
              <Pill label="Time" active={yoyMetric === "min"} onClick={() => setYM("min")} />
              <Pill label="km" active={yoyMetric === "km"} onClick={() => setYM("km")} />
            </div>
            <div style={{ display: "flex", gap: "0.25rem", flexWrap: "wrap" }}>
              {yoyYears.map(y => (
                <button key={y} onClick={() => setHY(prev => {
                  const next = new Set(prev);
                  next.has(y) ? next.delete(y) : next.add(y);
                  return next;
                })} style={{
                  padding: "0.2rem 0.55rem", borderRadius: "0.375rem", fontSize: "0.7rem",
                  fontWeight: 600, cursor: "pointer", border: "1px solid",
                  borderColor: hiddenYears.has(y) ? "#2a2d3a" : (YEAR_COLORS[y] ?? "#94a3b8"),
                  color: hiddenYears.has(y) ? "#475569" : (YEAR_COLORS[y] ?? "#94a3b8"),
                  background: hiddenYears.has(y) ? "transparent" : `${YEAR_COLORS[y] ?? "#94a3b8"}18`,
                  transition: "all 0.15s",
                }}>{y}</button>
              ))}
            </div>
          </div>
        </div>
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={yoyData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
            {grid}
            <XAxis dataKey="label" {...axisProps} />
            <YAxis {...axisProps} tickFormatter={v => yoyMetric === "min" ? `${(v/60).toFixed(0)}h` : `${v}km`} />
            <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v, name) => [
              yoyMetric === "min" ? `${(Number(v)/60).toFixed(1)}h` : `${Number(v).toFixed(0)}km`,
              String(name),
            ]} />
            <Legend wrapperStyle={{ fontSize: 11, color: "#64748b" }} />
            {yoyYears.filter(y => !hiddenYears.has(y)).flatMap(y =>
              (["running", "cycling"] as const)
                .filter(s => yoySports.has(s))
                .map(s => (
                  <Line key={`${s}_${y}`} type="monotone"
                    dataKey={yoyKey(y, s)} name={`${s === "running" ? "🏃" : "🚴"} ${y}`}
                    stroke={YEAR_COLORS[y] ?? "#94a3b8"}
                    strokeWidth={y === "2025" || y === "2026" ? 2.5 : 1.5}
                    strokeDasharray={s === "cycling" ? "5 3" : undefined}
                    dot={false} connectNulls />
                ))
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* ── Strava Insights ── */}
      {(hasInsights || insLoading) && (<>

        {/* Strava summary stats */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.625rem" }}>
          <StatBadge label="Run elevation" value={insRunElev > 0 ? Math.round(insRunElev).toLocaleString() : null} unit="m" color={RUN_COLOR} />
          <StatBadge label="Cyc elevation" value={insCycElev > 0 ? Math.round(insCycElev).toLocaleString() : null} unit="m" color={BIKE_COLOR} />
          <StatBadge label="Avg run HR" value={avgRunHR > 0 ? Math.round(avgRunHR) : null} unit="bpm" color="#ef4444" />
          <StatBadge label="Avg run pace" value={avgRunPace > 0 ? `${Math.floor(avgRunPace)}:${String(Math.round((avgRunPace % 1) * 60)).padStart(2, "0")}` : null} unit="/km" color={RUN_COLOR} />
          <StatBadge label="Relative effort" value={totalSuffer > 0 ? Math.round(totalSuffer) : null} color="#f97316" />
        </div>

        {/* Elevation chart */}
        <div style={{ ...SURFACE, padding: "1.25rem" }}>
          <SectionTitle>🏔️ Elevation Gain</SectionTitle>
          {insLoading ? <Spinner /> : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={insData} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
                {grid}
                <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" />
                <YAxis {...axisProps} tickFormatter={v => `${v}m`} />
                <Tooltip contentStyle={TOOLTIP_STYLE}
                  formatter={(v, name) => [`${Number(v).toFixed(0)} m`, name === "run_elevation_m" ? "Running" : "Cycling"]} />
                <Legend wrapperStyle={{ fontSize: 11, color: "#64748b" }}
                  formatter={n => n === "run_elevation_m" ? "Running" : "Cycling"} />
                <Bar dataKey="run_elevation_m" name="run_elevation_m" fill={RUN_COLOR} radius={[3,3,0,0]} maxBarSize={24} stackId="a" />
                <Bar dataKey="cyc_elevation_m" name="cyc_elevation_m" fill={BIKE_COLOR} radius={[3,3,0,0]} maxBarSize={24} stackId="a" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* HR + Pace side by side */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>

          {/* Avg HR */}
          <div style={{ ...SURFACE, padding: "1.25rem" }}>
            <SectionTitle>❤️ Average Heart Rate</SectionTitle>
            {insLoading ? <Spinner /> : (
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={insData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                  {grid}
                  <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" />
                  <YAxis {...axisProps} unit=" bpm" domain={["auto", "auto"]} />
                  <Tooltip contentStyle={TOOLTIP_STYLE}
                    formatter={(v, name) => [`${Number(v).toFixed(0)} bpm`, name === "run_avg_hr" ? "Running" : "Cycling"]} />
                  <Legend wrapperStyle={{ fontSize: 11, color: "#64748b" }}
                    formatter={n => n === "run_avg_hr" ? "Running" : "Cycling"} />
                  <Line type="monotone" dataKey="run_avg_hr" name="run_avg_hr"
                    stroke={RUN_COLOR} strokeWidth={2} dot={false} connectNulls />
                  <Line type="monotone" dataKey="cyc_avg_hr" name="cyc_avg_hr"
                    stroke={BIKE_COLOR} strokeWidth={2} dot={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Pace trend */}
          <div style={{ ...SURFACE, padding: "1.25rem" }}>
            <SectionTitle>⚡ Running Pace</SectionTitle>
            <div style={{ fontSize: "0.65rem", color: "#64748b", marginBottom: "0.5rem" }}>avg min/km · lower = faster</div>
            {insLoading ? <Spinner /> : (
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={insData.filter(r => r.run_avg_pace > 0)} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
                  {grid}
                  <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" />
                  <YAxis {...axisProps} reversed
                    tickFormatter={v => `${Math.floor(v)}:${String(Math.round((v%1)*60)).padStart(2,"0")}`}
                    domain={["auto", "auto"]} />
                  <Tooltip contentStyle={TOOLTIP_STYLE}
                    formatter={v => [`${Math.floor(Number(v))}:${String(Math.round((Number(v)%1)*60)).padStart(2,"0")} /km`, "Avg pace"]} />
                  <Line type="monotone" dataKey="run_avg_pace" name="run_avg_pace"
                    stroke={RUN_COLOR} strokeWidth={2} dot={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Relative effort */}
        <div style={{ ...SURFACE, padding: "1.25rem" }}>
          <SectionTitle>💪 Relative Effort (Strava Suffer Score)</SectionTitle>
          <div style={{ fontSize: "0.65rem", color: "#64748b", marginBottom: "0.5rem" }}>
            Strava's HR-based effort metric · higher = harder training block
          </div>
          {insLoading ? <Spinner /> : (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={insData} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
                {grid}
                <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" />
                <YAxis {...axisProps} />
                <Tooltip contentStyle={TOOLTIP_STYLE}
                  formatter={(v, name) => [Number(v).toFixed(0), name === "run_suffer" ? "Running" : "Cycling"]} />
                <Legend wrapperStyle={{ fontSize: 11, color: "#64748b" }}
                  formatter={n => n === "run_suffer" ? "Running" : "Cycling"} />
                <Bar dataKey="run_suffer" name="run_suffer" fill={RUN_COLOR} radius={[3,3,0,0]} maxBarSize={24} stackId="s" />
                <Bar dataKey="cyc_suffer" name="cyc_suffer" fill={BIKE_COLOR} radius={[3,3,0,0]} maxBarSize={24} stackId="s" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Cadence */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
          <div style={{ ...SURFACE, padding: "1.25rem" }}>
            <SectionTitle>🦵 Running Cadence</SectionTitle>
            <div style={{ fontSize: "0.65rem", color: "#64748b", marginBottom: "0.5rem" }}>avg steps/min · 170–180 = optimal</div>
            {insLoading ? <Spinner /> : (
              <ResponsiveContainer width="100%" height={160}>
                <LineChart data={insData.filter(r => r.run_avg_cadence > 0)} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                  {grid}
                  <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" />
                  <YAxis {...axisProps} unit=" spm" domain={["auto", "auto"]} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} formatter={v => [`${Number(v).toFixed(0)} spm`, "Cadence"]} />
                  <ReferenceLine y={175} stroke="#10b981" strokeDasharray="4 2" label={{ value: "175", fill: "#10b981", fontSize: 10 }} />
                  <Line type="monotone" dataKey="run_avg_cadence" stroke={RUN_COLOR} strokeWidth={2} dot={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
          <div style={{ ...SURFACE, padding: "1.25rem" }}>
            <SectionTitle>🚴 Cycling Cadence</SectionTitle>
            <div style={{ fontSize: "0.65rem", color: "#64748b", marginBottom: "0.5rem" }}>avg rpm · 85–95 = optimal</div>
            {insLoading ? <Spinner /> : (
              <ResponsiveContainer width="100%" height={160}>
                <LineChart data={insData.filter(r => r.cyc_avg_cadence > 0)} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                  {grid}
                  <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" />
                  <YAxis {...axisProps} unit=" rpm" domain={["auto", "auto"]} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} formatter={v => [`${Number(v).toFixed(0)} rpm`, "Cadence"]} />
                  <ReferenceLine y={90} stroke="#10b981" strokeDasharray="4 2" label={{ value: "90", fill: "#10b981", fontSize: 10 }} />
                  <Line type="monotone" dataKey="cyc_avg_cadence" stroke={BIKE_COLOR} strokeWidth={2} dot={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

      </>)}

      {/* ── HR Zones ── */}
      {hrZoneRaw && hrZoneRaw.some(z => z.run_count + z.cyc_count > 0) && (
        <div style={{ ...SURFACE, padding: "1.25rem" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
            <SectionTitle>❤️ HR Zone Distribution</SectionTitle>
            <span style={{ fontSize: "0.65rem", color: "#64748b" }}>based on avg HR per activity · Z1 &lt;60% → Z5 &gt;90% HRmax</span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={hrZoneRaw} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3a" />
              <XAxis dataKey="zone" {...axisProps} tick={{ fill: "#64748b", fontSize: 10 }} />
              <YAxis {...axisProps} label={{ value: "activities", angle: -90, position: "insideLeft", fill: "#64748b", fontSize: 10, dx: -4 }} />
              <Tooltip contentStyle={TOOLTIP_STYLE}
                formatter={(v, name) => [v, name === "run_count" ? "Running" : "Cycling"]}
                labelFormatter={l => {
                  const z = hrZoneRaw?.find(x => x.zone === l);
                  return z ? `${l} (${z.hr_min}–${z.hr_max} bpm)` : l;
                }} />
              <Legend wrapperStyle={{ fontSize: 11, color: "#64748b" }}
                formatter={n => n === "run_count" ? "Running" : "Cycling"} />
              <Bar dataKey="run_count" name="run_count" fill={RUN_COLOR} radius={[3,3,0,0]} maxBarSize={40} />
              <Bar dataKey="cyc_count" name="cyc_count" fill={BIKE_COLOR} radius={[3,3,0,0]} maxBarSize={40} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ── Personal Records ── */}
      {(runPRRaw?.length || cycPRRaw?.length) ? (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
          {[{ label: "🏃 Running PRs", data: runPRRaw }, { label: "🚴 Cycling PRs", data: cycPRRaw }].map(({ label, data: prs }) => (
            <div key={label} style={{ ...SURFACE, padding: "1.25rem" }}>
              <SectionTitle>{label}</SectionTitle>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {(prs ?? []).map(pr => (
                  <div key={pr.type} style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                    padding: "0.4rem 0.75rem", backgroundColor: "#13151f", borderRadius: "0.5rem" }}>
                    <span style={{ color: "#94a3b8", fontSize: "0.75rem" }}>{pr.type}</span>
                    <div style={{ textAlign: "right" }}>
                      <span style={{ color: "#e2e8f0", fontWeight: 700, fontSize: "0.9rem" }}>{pr.value}</span>
                      <span style={{ color: "#64748b", fontSize: "0.7rem", marginLeft: "0.25rem" }}>{pr.unit}</span>
                      <div style={{ color: "#475569", fontSize: "0.65rem" }}>{pr.date}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : null}

    </div>
  );
}
