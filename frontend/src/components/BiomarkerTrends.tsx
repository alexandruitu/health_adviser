import { useState, useEffect, useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import { TrendingUp, TrendingDown, Minus, ChevronDown, ChevronRight } from "lucide-react";
import { api } from "../api";
import type { BiomarkerReading } from "../api";

// ─── constants ──────────────────────────────────────────────────────────────

const CAT_LABELS: Record<string, string> = {
  cardiovascular:    "Cardiovascular",
  glucose_metabolism: "Glucose & Metabolism",
  hematology:        "Hematology",
  liver:             "Liver",
  kidney:            "Kidney",
  inflammation:      "Inflammation",
  vitamins_minerals: "Vitamins & Minerals",
  hormones:          "Hormones",
  performance:       "Performance",
  thyroid:           "Thyroid",
  other:             "Other",
};

const CAT_COLORS: Record<string, string> = {
  cardiovascular:    "#f97316",
  glucose_metabolism: "#eab308",
  hematology:        "#ef4444",
  liver:             "#84cc16",
  kidney:            "#06b6d4",
  inflammation:      "#ec4899",
  vitamins_minerals: "#10b981",
  hormones:          "#6366f1",
  performance:       "#f59e0b",
  thyroid:           "#8b5cf6",
  other:             "#94a3b8",
};

const STATUS_COLOR: Record<string, string> = {
  low:           "#3b82f6",
  normal:        "#10b981",
  high:          "#f97316",
  critical_low:  "#1d4ed8",
  critical_high: "#dc2626",
};

// Key markers to always show expanded (most clinically relevant)
const KEY_MARKERS = new Set([
  "Total Cholesterol", "LDL Cholesterol", "HDL Cholesterol", "Triglycerides",
  "Fasting Blood Glucose", "Hemoglobin", "Hematocrit",
  "White Blood Cells (WBC)", "Red Blood Cells (RBC)", "Platelets",
  "Alanine Aminotransferase (ALT)", "Aspartate Aminotransferase (AST)",
  "Gamma-Glutamyl Transferase (GGT)", "Creatinine", "Uric Acid",
  "Total Bilirubin", "Estimated Glomerular Filtration Rate (eGFR)",
]);

// ─── types ──────────────────────────────────────────────────────────────────

interface MarkerTrend {
  marker: string;
  category: string;
  unit: string;
  ref_min: number | null;
  ref_max: number | null;
  readings: { date: string; value: number; status: string }[];
}

// ─── helpers ────────────────────────────────────────────────────────────────

function fmtDate(s: string) {
  try {
    return new Date(s).toLocaleDateString("en", { year: "numeric", month: "short" });
  } catch { return s; }
}

function fmtVal(v: number) {
  return v % 1 === 0 ? v.toString() : v.toFixed(2).replace(/\.?0+$/, "");
}

function getDelta(readings: { value: number }[]): { pct: number; dir: "up" | "down" | "flat" } | null {
  if (readings.length < 2) return null;
  const prev = readings[readings.length - 2].value;
  const curr = readings[readings.length - 1].value;
  if (prev === 0) return null;
  const pct = ((curr - prev) / Math.abs(prev)) * 100;
  return { pct, dir: Math.abs(pct) < 1 ? "flat" : pct > 0 ? "up" : "down" };
}

// ─── Sparkline ──────────────────────────────────────────────────────────────

function Sparkline({ readings, color, refMin, refMax }: {
  readings: { date: string; value: number }[];
  color: string;
  refMin: number | null;
  refMax: number | null;
}) {
  if (readings.length < 2) return null;
  const data = readings.map(r => ({ d: fmtDate(r.date), v: r.value }));

  return (
    <div style={{ width: 120, height: 36 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
          {refMin != null && <ReferenceLine y={refMin} stroke="#10b98130" strokeDasharray="2 2" />}
          {refMax != null && <ReferenceLine y={refMax} stroke="#f9731630" strokeDasharray="2 2" />}
          <Line type="monotone" dataKey="v" stroke={color} strokeWidth={1.5} dot={{ fill: color, r: 2 }} />
          <Tooltip
            contentStyle={{ backgroundColor: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: "0.375rem", padding: "4px 8px" }}
            labelStyle={{ color: "#94a3b8", fontSize: "0.7rem" }}
            formatter={(v: number) => [fmtVal(v), ""]}
            labelFormatter={(l: string) => l}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Expanded detail chart ──────────────────────────────────────────────────

function DetailChart({ trend }: { trend: MarkerTrend }) {
  const color = CAT_COLORS[trend.category] ?? "#6366f1";
  const data = trend.readings.map(r => ({
    date: fmtDate(r.date),
    value: r.value,
    status: r.status,
  }));

  return (
    <div style={{
      padding: "0.75rem 1rem", borderTop: "1px solid #1e2130",
      display: "grid", gridTemplateColumns: "1fr auto", gap: "1.5rem", alignItems: "start",
    }}>
      {/* Chart */}
      <div style={{ height: 140 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 10 }}>
            <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 10 }} />
            <YAxis tick={{ fill: "#64748b", fontSize: 10 }} domain={["auto", "auto"]} width={50} />
            {trend.ref_min != null && (
              <ReferenceLine y={trend.ref_min} stroke="#10b98150" strokeDasharray="4 4"
                label={{ value: "Min", fill: "#10b981", fontSize: 9, position: "left" }} />
            )}
            {trend.ref_max != null && (
              <ReferenceLine y={trend.ref_max} stroke="#f9731650" strokeDasharray="4 4"
                label={{ value: "Max", fill: "#f97316", fontSize: 9, position: "left" }} />
            )}
            <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2}
              dot={{ fill: color, r: 4, strokeWidth: 2, stroke: "#0f1117" }}
              activeDot={{ r: 6 }}
            />
            <Tooltip
              contentStyle={{ backgroundColor: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: "0.5rem" }}
              labelStyle={{ color: "#94a3b8" }}
              formatter={(v: number) => [`${fmtVal(v)} ${trend.unit}`, trend.marker]}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Year-over-year values table */}
      <div style={{ minWidth: 200 }}>
        <table style={{ borderCollapse: "collapse", fontSize: "0.72rem", width: "100%" }}>
          <thead>
            <tr>
              <th style={{ padding: "3px 8px", color: "#475569", fontWeight: 600, textAlign: "left" }}>Date</th>
              <th style={{ padding: "3px 8px", color: "#475569", fontWeight: 600, textAlign: "right" }}>Value</th>
              <th style={{ padding: "3px 8px", color: "#475569", fontWeight: 600, textAlign: "right" }}>Change</th>
            </tr>
          </thead>
          <tbody>
            {trend.readings.map((r, i) => {
              const prev = i > 0 ? trend.readings[i - 1].value : null;
              const delta = prev != null && prev !== 0 ? ((r.value - prev) / Math.abs(prev)) * 100 : null;
              const sColor = STATUS_COLOR[r.status] ?? "#94a3b8";
              return (
                <tr key={r.date} style={{ borderTop: i > 0 ? "1px solid #1e2130" : "none" }}>
                  <td style={{ padding: "3px 8px", color: "#94a3b8" }}>{fmtDate(r.date)}</td>
                  <td style={{ padding: "3px 8px", color: sColor, fontWeight: 600, textAlign: "right" }}>
                    {fmtVal(r.value)}
                  </td>
                  <td style={{ padding: "3px 8px", textAlign: "right", color: delta == null ? "#475569" : delta > 0 ? "#f97316" : "#10b981" }}>
                    {delta == null ? "—" : `${delta > 0 ? "+" : ""}${delta.toFixed(1)}%`}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Main component ─────────────────────────────────────────────────────────

export function BiomarkerTrends() {
  const [allData, setAllData] = useState<BiomarkerReading[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set(KEY_MARKERS));
  const [filterCat, setFilterCat] = useState<string | null>(null);

  useEffect(() => {
    api.biomarkersAll().then(d => { setAllData(d); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  // Build trends from raw data
  const trends = useMemo(() => {
    const map = new Map<string, MarkerTrend>();
    for (const r of allData) {
      if (!map.has(r.marker_canonical)) {
        map.set(r.marker_canonical, {
          marker: r.marker_canonical,
          category: r.category,
          unit: r.unit,
          ref_min: r.ref_min,
          ref_max: r.ref_max,
          readings: [],
        });
      }
      const t = map.get(r.marker_canonical)!;
      t.readings.push({ date: r.test_date, value: r.value, status: r.status });
      // Update ref range if newer
      if (r.ref_min != null) t.ref_min = r.ref_min;
      if (r.ref_max != null) t.ref_max = r.ref_max;
    }
    // Sort readings by date, only keep markers with 2+ readings
    const result: MarkerTrend[] = [];
    for (const t of map.values()) {
      t.readings.sort((a, b) => a.date.localeCompare(b.date));
      if (t.readings.length >= 2) result.push(t);
    }
    return result;
  }, [allData]);

  // Get unique screening dates
  const screeningDates = useMemo(() => {
    const dates = new Set<string>();
    allData.forEach(r => dates.add(r.test_date));
    return [...dates].sort();
  }, [allData]);

  // Group trends by category
  const byCategory = useMemo(() => {
    const filtered = filterCat ? trends.filter(t => t.category === filterCat) : trends;
    const grouped = new Map<string, MarkerTrend[]>();
    for (const t of filtered) {
      if (!grouped.has(t.category)) grouped.set(t.category, []);
      grouped.get(t.category)!.push(t);
    }
    return [...grouped.entries()].sort((a, b) => (CAT_LABELS[a[0]] ?? a[0]).localeCompare(CAT_LABELS[b[0]] ?? b[0]));
  }, [trends, filterCat]);

  // Count abnormals
  const abnormalCount = trends.filter(t => {
    const latest = t.readings[t.readings.length - 1];
    return latest.status !== "normal";
  }).length;

  // Categories available
  const cats = useMemo(() => {
    const s = new Set(trends.map(t => t.category));
    return [...s].sort((a, b) => (CAT_LABELS[a] ?? a).localeCompare(CAT_LABELS[b] ?? b));
  }, [trends]);

  function toggleExpand(marker: string) {
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(marker) ? next.delete(marker) : next.add(marker);
      return next;
    });
  }

  if (loading) return <div style={{ color: "#64748b", fontSize: "0.85rem" }}>Loading trends...</div>;
  if (trends.length === 0) return <div style={{ color: "#64748b", fontSize: "0.85rem" }}>Need at least 2 screenings for trend analysis.</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {/* Summary bar */}
      <div style={{
        display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "center",
        backgroundColor: "#1a1d27", borderRadius: "0.75rem",
        padding: "0.75rem 1.25rem", border: "1px solid #2a2d3a",
      }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: "0.4rem" }}>
          <span style={{ fontSize: "1.5rem", fontWeight: 700, color: "#e2e8f0" }}>{trends.length}</span>
          <span style={{ fontSize: "0.78rem", color: "#64748b" }}>markers tracked</span>
        </div>
        <div style={{ width: 1, height: 24, backgroundColor: "#2a2d3a" }} />
        <div style={{ display: "flex", alignItems: "baseline", gap: "0.4rem" }}>
          <span style={{ fontSize: "1.5rem", fontWeight: 700, color: "#e2e8f0" }}>{screeningDates.length}</span>
          <span style={{ fontSize: "0.78rem", color: "#64748b" }}>screenings</span>
        </div>
        <div style={{ width: 1, height: 24, backgroundColor: "#2a2d3a" }} />
        {abnormalCount > 0 && (
          <div style={{ display: "flex", alignItems: "baseline", gap: "0.4rem" }}>
            <span style={{ fontSize: "1.5rem", fontWeight: 700, color: "#f97316" }}>{abnormalCount}</span>
            <span style={{ fontSize: "0.78rem", color: "#64748b" }}>out of range</span>
          </div>
        )}
        <div style={{ marginLeft: "auto", fontSize: "0.72rem", color: "#475569" }}>
          {screeningDates.map(d => fmtDate(d)).join("  ·  ")}
        </div>
      </div>

      {/* Category filter pills */}
      <div style={{ display: "flex", gap: "0.3rem", flexWrap: "wrap" }}>
        <button
          onClick={() => setFilterCat(null)}
          style={{
            padding: "0.2rem 0.65rem", borderRadius: "0.375rem", fontSize: "0.72rem", fontWeight: 600,
            cursor: "pointer", border: "1px solid #3a3d4a",
            backgroundColor: !filterCat ? "#6366f1" : "#2a2d3a",
            color: !filterCat ? "#fff" : "#94a3b8",
          }}
        >All</button>
        {cats.map(cat => (
          <button
            key={cat}
            onClick={() => setFilterCat(cat === filterCat ? null : cat)}
            style={{
              padding: "0.2rem 0.65rem", borderRadius: "0.375rem", fontSize: "0.72rem", fontWeight: 600,
              cursor: "pointer",
              border: `1px solid ${cat === filterCat ? CAT_COLORS[cat] + "60" : "#3a3d4a"}`,
              backgroundColor: cat === filterCat ? CAT_COLORS[cat] + "18" : "#2a2d3a",
              color: cat === filterCat ? CAT_COLORS[cat] : "#94a3b8",
            }}
          >{CAT_LABELS[cat] ?? cat}</button>
        ))}
      </div>

      {/* Trends by category */}
      {byCategory.map(([cat, markers]) => (
        <div key={cat} style={{
          backgroundColor: "#1a1d27", borderRadius: "0.75rem",
          border: "1px solid #2a2d3a", overflow: "hidden",
        }}>
          {/* Category header */}
          <div style={{
            padding: "0.55rem 1rem",
            borderBottom: "1px solid #1e2130",
            display: "flex", alignItems: "center", gap: "0.5rem",
          }}>
            <div style={{ width: 3, height: 16, borderRadius: 2, backgroundColor: CAT_COLORS[cat] ?? "#64748b" }} />
            <span style={{ fontSize: "0.8rem", fontWeight: 700, color: CAT_COLORS[cat] ?? "#94a3b8" }}>
              {CAT_LABELS[cat] ?? cat}
            </span>
            <span style={{ fontSize: "0.68rem", color: "#475569" }}>{markers.length} markers</span>
          </div>

          {/* Marker rows */}
          {markers.map(t => {
            const latest = t.readings[t.readings.length - 1];
            const delta = getDelta(t.readings);
            const sColor = STATUS_COLOR[latest.status] ?? "#94a3b8";
            const catColor = CAT_COLORS[t.category] ?? "#6366f1";
            const isExpanded = expanded.has(t.marker);
            const isKey = KEY_MARKERS.has(t.marker);

            return (
              <div key={t.marker}>
                {/* Summary row */}
                <div
                  onClick={() => toggleExpand(t.marker)}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "24px 2fr 100px 80px 120px 70px",
                    gap: "0.5rem",
                    alignItems: "center",
                    padding: "0.5rem 1rem",
                    cursor: "pointer",
                    borderBottom: isExpanded ? "none" : "1px solid #0f1117",
                    backgroundColor: isExpanded ? "#161822" : "transparent",
                    transition: "background-color 0.15s",
                  }}
                  onMouseEnter={e => { if (!isExpanded) e.currentTarget.style.backgroundColor = "#14161e"; }}
                  onMouseLeave={e => { if (!isExpanded) e.currentTarget.style.backgroundColor = "transparent"; }}
                >
                  {/* Expand icon */}
                  <div style={{ color: "#475569" }}>
                    {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  </div>

                  {/* Marker name */}
                  <div>
                    <span style={{
                      fontSize: "0.78rem", fontWeight: isKey ? 600 : 400,
                      color: isKey ? "#e2e8f0" : "#cbd5e1",
                    }}>{t.marker}</span>
                    <span style={{ fontSize: "0.65rem", color: "#475569", marginLeft: "0.4rem" }}>{t.unit}</span>
                  </div>

                  {/* Latest value */}
                  <div style={{ textAlign: "right" }}>
                    <span style={{ fontSize: "0.85rem", fontWeight: 700, color: sColor }}>
                      {fmtVal(latest.value)}
                    </span>
                  </div>

                  {/* Delta */}
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: "0.25rem" }}>
                    {delta ? (
                      <>
                        {delta.dir === "up" ? <TrendingUp size={12} style={{ color: "#f97316" }} /> :
                         delta.dir === "down" ? <TrendingDown size={12} style={{ color: "#10b981" }} /> :
                         <Minus size={12} style={{ color: "#64748b" }} />}
                        <span style={{
                          fontSize: "0.72rem", fontWeight: 600,
                          color: delta.dir === "up" ? "#f97316" : delta.dir === "down" ? "#10b981" : "#64748b",
                        }}>
                          {delta.pct > 0 ? "+" : ""}{delta.pct.toFixed(1)}%
                        </span>
                      </>
                    ) : <span style={{ fontSize: "0.72rem", color: "#475569" }}>—</span>}
                  </div>

                  {/* Sparkline */}
                  <Sparkline readings={t.readings} color={catColor} refMin={t.ref_min} refMax={t.ref_max} />

                  {/* Status badge */}
                  <div style={{ textAlign: "right" }}>
                    <span style={{
                      fontSize: "0.6rem", fontWeight: 600,
                      color: sColor,
                      backgroundColor: `${sColor}15`,
                      borderRadius: "0.2rem",
                      padding: "2px 6px",
                      border: `1px solid ${sColor}25`,
                    }}>
                      {latest.status === "normal" ? "Normal" :
                       latest.status === "high" ? "High" :
                       latest.status === "low" ? "Low" :
                       latest.status === "critical_high" ? "Critical" :
                       latest.status === "critical_low" ? "Critical" : latest.status}
                    </span>
                  </div>
                </div>

                {/* Expanded detail */}
                {isExpanded && <DetailChart trend={t} />}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
