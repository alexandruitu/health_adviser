import { useState, useRef, useEffect } from "react";
import {
  AreaChart, Area, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import { api } from "../api";
import type { BiomarkerUpload, BiomarkerReading, ExtractedMarker, BiomarkersExtracted } from "../api";

// ─── constants ────────────────────────────────────────────────────────────────

const CAT_LABELS: Record<string, string> = {
  hematology:        "Hematology",
  cardiovascular:    "Cardiovascular",
  glucose_metabolism:"Glucose & Metabolism",
  liver:             "Liver",
  kidney:            "Kidney",
  thyroid:           "Thyroid",
  inflammation:      "Inflammation",
  vitamins_minerals: "Vitamins & Minerals",
  hormones:          "Hormones",
  performance:       "Performance",
  coagulation:       "Coagulation",
  urine:             "Urine",
  other:             "Other",
};

const CAT_COLORS: Record<string, string> = {
  hematology:        "#ef4444",
  cardiovascular:    "#f97316",
  glucose_metabolism:"#eab308",
  liver:             "#84cc16",
  kidney:            "#06b6d4",
  thyroid:           "#8b5cf6",
  inflammation:      "#ec4899",
  vitamins_minerals: "#10b981",
  hormones:          "#6366f1",
  performance:       "#f59e0b",
  coagulation:       "#14b8a6",
  urine:             "#64748b",
  other:             "#94a3b8",
};

const STATUS_COLOR: Record<string, string> = {
  low:           "#3b82f6",
  normal:        "#10b981",
  high:          "#f97316",
  critical_low:  "#1d4ed8",
  critical_high: "#dc2626",
};

function statusLabel(s: string) {
  return s === "critical_low" ? "Critically Low"
    : s === "critical_high" ? "Critically High"
    : s.charAt(0).toUpperCase() + s.slice(1);
}

// ─── helpers ──────────────────────────────────────────────────────────────────

function fmtDate(s: string | null) {
  if (!s) return "—";
  try { return new Date(s).toLocaleDateString("en", { year: "numeric", month: "short", day: "numeric" }); }
  catch { return s; }
}

function fmtVal(v: number, unit: string) {
  const s = v % 1 === 0 ? v.toString() : v.toFixed(2).replace(/\.?0+$/, "");
  return `${s} ${unit}`;
}

function pctInRange(value: number, min: number | null, max: number | null): number | null {
  if (min == null || max == null) return null;
  const range = max - min;
  if (range <= 0) return null;
  return Math.max(0, Math.min(100, ((value - min) / range) * 100));
}

// ─── sub-components ───────────────────────────────────────────────────────────

function GaugeBar({ value, min, max, status }: {
  value: number; min: number | null; max: number | null; status: string;
}) {
  const pct = pctInRange(value, min, max);
  const color = STATUS_COLOR[status] ?? "#64748b";
  if (pct == null || min == null || max == null) {
    return <div style={{ fontSize: "0.7rem", color: "#64748b" }}>No reference range</div>;
  }
  // Extend bar slightly beyond range to show out-of-range markers
  const displayPct = Math.max(2, Math.min(98, pct));
  return (
    <div style={{ marginTop: "0.35rem" }}>
      <div style={{
        position: "relative", height: "6px", borderRadius: "3px",
        backgroundColor: "#1e2130", overflow: "visible",
      }}>
        {/* Normal band */}
        <div style={{
          position: "absolute", left: "10%", right: "10%", top: 0, bottom: 0,
          backgroundColor: "#10b98118", borderRadius: "3px",
        }} />
        {/* Value indicator */}
        <div style={{
          position: "absolute", top: "-3px",
          left: `${displayPct}%`, transform: "translateX(-50%)",
          width: "12px", height: "12px", borderRadius: "50%",
          backgroundColor: color, border: "2px solid #0f1117",
          boxShadow: `0 0 6px ${color}80`,
        }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: "4px", fontSize: "0.65rem", color: "#475569" }}>
        <span>{min}</span>
        <span>{max}</span>
      </div>
    </div>
  );
}

function MarkerCard({ m, onClick }: { m: BiomarkerReading; onClick: () => void }) {
  const color = STATUS_COLOR[m.status] ?? "#64748b";
  const catColor = CAT_COLORS[m.category] ?? "#64748b";
  return (
    <div
      onClick={onClick}
      style={{
        backgroundColor: "#1a1d27", border: `1px solid #2a2d3a`,
        borderLeft: `3px solid ${catColor}`,
        borderRadius: "0.5rem", padding: "0.75rem",
        cursor: "pointer", transition: "border-color 0.15s",
      }}
      onMouseEnter={e => (e.currentTarget.style.borderColor = catColor)}
      onMouseLeave={e => (e.currentTarget.style.borderColor = "#2a2d3a")}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
        <div>
          <div style={{ fontSize: "0.78rem", fontWeight: 600, color: "#cbd5e1", lineHeight: 1.2 }}>
            {m.marker_canonical}
          </div>
          <div style={{ fontSize: "0.65rem", color: "#475569", marginTop: "2px" }}>{fmtDate(m.test_date)}</div>
        </div>
        <div style={{ textAlign: "right", flexShrink: 0 }}>
          <div style={{ fontSize: "0.85rem", fontWeight: 700, color }}>{fmtVal(m.value, m.unit)}</div>
          <div style={{
            fontSize: "0.6rem", fontWeight: 600, marginTop: "2px",
            color, backgroundColor: `${color}18`, borderRadius: "0.2rem",
            padding: "1px 5px", border: `1px solid ${color}30`,
          }}>{statusLabel(m.status)}</div>
        </div>
      </div>
      <GaugeBar value={m.value} min={m.ref_min} max={m.ref_max} status={m.status} />
    </div>
  );
}

// ─── Trend modal ──────────────────────────────────────────────────────────────

function TrendModal({ marker, all, onClose }: {
  marker: string; all: BiomarkerReading[]; onClose: () => void;
}) {
  const series = all.filter(r => r.marker_canonical === marker).sort((a, b) => a.test_date.localeCompare(b.test_date));
  if (!series.length) return null;

  const latest = series[series.length - 1];
  const color = STATUS_COLOR[latest.status] ?? "#6366f1";
  const refMin = latest.ref_min;
  const refMax = latest.ref_max;

  const chartData = series.map(r => ({ date: fmtDate(r.test_date), value: r.value, lab: r.lab_name }));

  return (
    <div
      onClick={e => e.target === e.currentTarget && onClose()}
      style={{
        position: "fixed", inset: 0, backgroundColor: "#000a",
        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100,
      }}
    >
      <div style={{
        backgroundColor: "#13151f", border: "1px solid #2a2d3a",
        borderRadius: "1rem", padding: "1.5rem", width: "min(700px, 95vw)",
        maxHeight: "85vh", overflow: "auto",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
          <div>
            <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "#e2e8f0" }}>{marker}</div>
            <div style={{ fontSize: "0.75rem", color: "#64748b" }}>
              {series.length} measurement{series.length > 1 ? "s" : ""} · Unit: {latest.unit}
              {refMin != null && refMax != null ? ` · Ref: ${refMin}–${refMax}` : ""}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", color: "#64748b", fontSize: "1.25rem", cursor: "pointer" }}
          >✕</button>
        </div>

        {/* Latest value */}
        <div style={{
          backgroundColor: "#1a1d27", borderRadius: "0.5rem", padding: "0.75rem 1rem",
          display: "flex", gap: "2rem", marginBottom: "1rem",
          border: `1px solid ${color}30`,
        }}>
          <div>
            <div style={{ fontSize: "0.65rem", color: "#64748b", marginBottom: "2px" }}>LATEST VALUE</div>
            <div style={{ fontSize: "1.5rem", fontWeight: 700, color }}>{fmtVal(latest.value, latest.unit)}</div>
          </div>
          <div>
            <div style={{ fontSize: "0.65rem", color: "#64748b", marginBottom: "2px" }}>STATUS</div>
            <div style={{ fontSize: "1rem", fontWeight: 600, color }}>{statusLabel(latest.status)}</div>
          </div>
          <div>
            <div style={{ fontSize: "0.65rem", color: "#64748b", marginBottom: "2px" }}>DATE</div>
            <div style={{ fontSize: "1rem", color: "#94a3b8" }}>{fmtDate(latest.test_date)}</div>
          </div>
        </div>

        {/* Chart — only if multiple points */}
        {series.length >= 2 && (
          <div style={{ height: 200, marginBottom: "1rem" }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="bmGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={color} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={color} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3a" />
                <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 11 }} />
                <YAxis tick={{ fill: "#64748b", fontSize: 11 }} domain={["auto", "auto"]} />
                <Tooltip
                  contentStyle={{ backgroundColor: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: "0.5rem" }}
                  labelStyle={{ color: "#94a3b8" }}
                  itemStyle={{ color }}
                  formatter={(v: number) => [`${v} ${latest.unit}`, marker]}
                />
                {refMin != null && <ReferenceLine y={refMin} stroke="#10b98160" strokeDasharray="4 4" label={{ value: "Min", fill: "#10b981", fontSize: 10 }} />}
                {refMax != null && <ReferenceLine y={refMax} stroke="#f9731660" strokeDasharray="4 4" label={{ value: "Max", fill: "#f97316", fontSize: 10 }} />}
                <Area type="monotone" dataKey="value" stroke={color} fill="url(#bmGrad)" strokeWidth={2} dot={{ fill: color, r: 4 }} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* All readings table */}
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.78rem" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #2a2d3a" }}>
              {["Date", "Value", "Reference", "Status", "Lab"].map(h => (
                <th key={h} style={{ padding: "0.4rem 0.6rem", textAlign: "left", color: "#64748b", fontWeight: 600 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...series].reverse().map((r, i) => (
              <tr key={i} style={{ borderBottom: "1px solid #1e2130" }}>
                <td style={{ padding: "0.4rem 0.6rem", color: "#94a3b8" }}>{fmtDate(r.test_date)}</td>
                <td style={{ padding: "0.4rem 0.6rem", color: STATUS_COLOR[r.status] ?? "#e2e8f0", fontWeight: 600 }}>{fmtVal(r.value, r.unit)}</td>
                <td style={{ padding: "0.4rem 0.6rem", color: "#64748b" }}>
                  {r.ref_min != null && r.ref_max != null ? `${r.ref_min}–${r.ref_max}` : r.ref_max != null ? `< ${r.ref_max}` : r.ref_min != null ? `> ${r.ref_min}` : "—"}
                </td>
                <td style={{ padding: "0.4rem 0.6rem" }}>
                  <span style={{ color: STATUS_COLOR[r.status] ?? "#64748b", fontWeight: 600 }}>{statusLabel(r.status)}</span>
                </td>
                <td style={{ padding: "0.4rem 0.6rem", color: "#475569" }}>{r.lab_name || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Review modal ─────────────────────────────────────────────────────────────

function ReviewModal({ extracted, onConfirm, onCancel }: {
  extracted: BiomarkersExtracted;
  onConfirm: (e: BiomarkersExtracted) => void;
  onCancel: () => void;
}) {
  const [testDate, setTestDate] = useState(extracted.test_date || "");
  const [labName, setLabName]   = useState(extracted.lab_name || "");
  const [markers, setMarkers]   = useState<ExtractedMarker[]>(extracted.markers);
  const [saving, setSaving]     = useState(false);

  function removeMarker(i: number) {
    setMarkers(m => m.filter((_, idx) => idx !== i));
  }

  async function handleConfirm() {
    setSaving(true);
    onConfirm({ ...extracted, test_date: testDate || null, lab_name: labName || null, markers });
  }

  const byCategory = markers.reduce<Record<string, ExtractedMarker[]>>((acc, m) => {
    (acc[m.category] ??= []).push(m); return acc;
  }, {});

  return (
    <div style={{
      position: "fixed", inset: 0, backgroundColor: "#000b",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100,
    }}>
      <div style={{
        backgroundColor: "#13151f", border: "1px solid #2a2d3a", borderRadius: "1rem",
        padding: "1.5rem", width: "min(900px, 96vw)", maxHeight: "90vh",
        display: "flex", flexDirection: "column", gap: "1rem",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "#e2e8f0" }}>Review Extracted Results</div>
            <div style={{ fontSize: "0.75rem", color: "#64748b" }}>
              {markers.length} markers from <span style={{ color: "#94a3b8" }}>{extracted.filename}</span>
            </div>
          </div>
          <button onClick={onCancel} style={{ background: "none", border: "none", color: "#64748b", fontSize: "1.25rem", cursor: "pointer" }}>✕</button>
        </div>

        {/* Metadata row */}
        <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: "4px", flex: 1, minWidth: "160px" }}>
            <span style={{ fontSize: "0.65rem", fontWeight: 600, color: "#64748b", textTransform: "uppercase" }}>Test Date</span>
            <input
              type="date" value={testDate} onChange={e => setTestDate(e.target.value)}
              style={{ backgroundColor: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: "0.375rem",
                padding: "0.4rem 0.6rem", color: "#e2e8f0", fontSize: "0.85rem" }}
            />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "4px", flex: 2, minWidth: "200px" }}>
            <span style={{ fontSize: "0.65rem", fontWeight: 600, color: "#64748b", textTransform: "uppercase" }}>Lab / Hospital</span>
            <input
              type="text" value={labName} onChange={e => setLabName(e.target.value)}
              placeholder="e.g. Hiperdia, Synevo…"
              style={{ backgroundColor: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: "0.375rem",
                padding: "0.4rem 0.6rem", color: "#e2e8f0", fontSize: "0.85rem" }}
            />
          </label>
        </div>

        {/* Markers table — scrollable */}
        <div style={{ overflowY: "auto", flex: 1, border: "1px solid #2a2d3a", borderRadius: "0.5rem" }}>
          {Object.entries(byCategory).map(([cat, ms]) => (
            <div key={cat}>
              <div style={{
                padding: "0.4rem 0.75rem", fontSize: "0.7rem", fontWeight: 700,
                color: CAT_COLORS[cat] ?? "#94a3b8", backgroundColor: "#0f1117",
                textTransform: "uppercase", letterSpacing: "0.05em", position: "sticky", top: 0,
              }}>
                {CAT_LABELS[cat] ?? cat}
              </div>
              {ms.map((m, i) => {
                const globalIdx = markers.indexOf(m);
                const statusC = STATUS_COLOR[m.status] ?? "#64748b";
                return (
                  <div key={i} style={{
                    display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr auto",
                    gap: "0.5rem", alignItems: "center",
                    padding: "0.4rem 0.75rem", borderBottom: "1px solid #1e2130",
                    fontSize: "0.78rem",
                  }}>
                    <span style={{ color: "#cbd5e1" }}>{m.canonical || m.name}</span>
                    <span style={{ color: statusC, fontWeight: 600 }}>{fmtVal(m.value, m.unit)}</span>
                    <span style={{ color: "#475569" }}>
                      {m.ref_min != null && m.ref_max != null ? `${m.ref_min}–${m.ref_max}` : m.ref_max != null ? `< ${m.ref_max}` : m.ref_min != null ? `> ${m.ref_min}` : "—"}
                    </span>
                    <span style={{
                      color: statusC, fontWeight: 600, fontSize: "0.65rem",
                      backgroundColor: `${statusC}18`, borderRadius: "0.2rem", padding: "2px 6px",
                    }}>{statusLabel(m.status)}</span>
                    <button onClick={() => removeMarker(globalIdx)} style={{
                      background: "none", border: "none", color: "#475569",
                      cursor: "pointer", fontSize: "0.9rem", padding: "2px 4px",
                    }}>✕</button>
                  </div>
                );
              })}
            </div>
          ))}
        </div>

        <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
          <button onClick={onCancel} disabled={saving} style={{
            padding: "0.5rem 1.25rem", borderRadius: "0.375rem", fontSize: "0.85rem",
            fontWeight: 600, cursor: "pointer", backgroundColor: "transparent",
            color: "#64748b", border: "1px solid #2a2d3a",
          }}>Cancel</button>
          <button onClick={handleConfirm} disabled={saving || markers.length === 0} style={{
            padding: "0.5rem 1.25rem", borderRadius: "0.375rem", fontSize: "0.85rem",
            fontWeight: 600, cursor: saving ? "wait" : "pointer",
            backgroundColor: "#6366f1", color: "#fff", border: "none", opacity: saving ? 0.6 : 1,
          }}>{saving ? "Saving…" : `Save ${markers.length} markers`}</button>
        </div>
      </div>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export function Biomarkers({ embedded }: { embedded?: boolean } = {}) {
  const [uploads, setUploads]       = useState<BiomarkerUpload[]>([]);
  const [allData, setAllData]       = useState<BiomarkerReading[]>([]);
  const [loading, setLoading]       = useState(true);
  const [uploading, setUploading]   = useState(false);
  const [uploadErr, setUploadErr]   = useState<string | null>(null);
  const [extracted, setExtracted]   = useState<BiomarkersExtracted | null>(null);
  const [trendMarker, setTrendMarker] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function reload() {
    try {
      const [u, a] = await Promise.all([api.biomarkersUploads(), api.biomarkersAll()]);
      setUploads(u);
      setAllData(a);
    } catch { /* backend may not have data yet */ }
    setLoading(false);
  }

  useEffect(() => { reload(); }, []);

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true); setUploadErr(null);
    try {
      const result = await api.biomarkersUpload(file);
      setExtracted(result);
    } catch (err) {
      setUploadErr(err instanceof Error ? err.message : "Upload failed");
      setTimeout(() => setUploadErr(null), 8000);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function handleConfirm(e: BiomarkersExtracted) {
    await api.biomarkersConfirm(e);
    setExtracted(null);
    await reload();
  }

  async function handleDelete(id: number) {
    if (!confirm("Delete this upload and all its markers?")) return;
    await api.biomarkersDeleteUpload(id);
    await reload();
  }

  // Build latest-value summary from allData
  const latestByMarker = allData.reduce<Record<string, BiomarkerReading>>((acc, r) => {
    const prev = acc[r.marker_canonical];
    if (!prev || r.test_date > prev.test_date) acc[r.marker_canonical] = r;
    return acc;
  }, {});
  const latestList = Object.values(latestByMarker);

  // Group by category
  const byCategory = latestList.reduce<Record<string, BiomarkerReading[]>>((acc, m) => {
    (acc[m.category] ??= []).push(m); return acc;
  }, {});
  const categories = Object.keys(byCategory).sort((a, b) => (CAT_LABELS[a] ?? a).localeCompare(CAT_LABELS[b] ?? b));

  // Status summary counts
  const statusCounts = latestList.reduce<Record<string, number>>((acc, m) => {
    acc[m.status] = (acc[m.status] || 0) + 1; return acc;
  }, {});

  const displayCategory = activeCategory ?? (categories[0] || null);
  const displayMarkers  = displayCategory ? (byCategory[displayCategory] ?? []) : [];

  // Markers with multiple readings (for trend availability)
  const markerCounts = allData.reduce<Record<string, number>>((acc, r) => {
    acc[r.marker_canonical] = (acc[r.marker_canonical] || 0) + 1; return acc;
  }, {});

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {/* ── Header ── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.75rem" }}>
        {!embedded && (
          <div>
            <h1 style={{ fontSize: "1.25rem", fontWeight: 700, color: "#e2e8f0", margin: 0 }}>Biomarkers</h1>
            <p style={{ fontSize: "0.8rem", color: "#64748b", margin: "2px 0 0" }}>
              {latestList.length > 0
                ? `${latestList.length} markers tracked · ${uploads.length} lab report${uploads.length !== 1 ? "s" : ""}`
                : "Upload a lab report PDF to start tracking"}
            </p>
          </div>
        )}
        {embedded && (
          <p style={{ fontSize: "0.8rem", color: "#64748b", margin: 0 }}>
            {latestList.length > 0
              ? `${latestList.length} markers tracked · ${uploads.length} lab report${uploads.length !== 1 ? "s" : ""}`
              : "Upload a lab report PDF to start tracking"}
          </p>
        )}
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          {uploadErr && <span style={{ fontSize: "0.75rem", color: "#ef4444" }}>{uploadErr}</span>}
          <input ref={fileRef} type="file" accept=".pdf" style={{ display: "none" }} onChange={handleFile} />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            style={{
              backgroundColor: uploading ? "#64748b20" : "#6366f118",
              color: uploading ? "#64748b" : "#6366f1",
              border: `1px solid ${uploading ? "#64748b30" : "#6366f140"}`,
              borderRadius: "0.375rem", padding: "0.4rem 1rem",
              fontSize: "0.8rem", fontWeight: 600, cursor: uploading ? "wait" : "pointer",
            }}
          >
            {uploading ? "Analysing PDF…" : "⬆ Upload Lab Report"}
          </button>
        </div>
      </div>

      {loading && <div style={{ color: "#64748b", fontSize: "0.85rem" }}>Loading…</div>}

      {/* ── Status summary bar ── */}
      {latestList.length > 0 && (
        <div style={{
          display: "flex", gap: "0.75rem", flexWrap: "wrap",
          backgroundColor: "#1a1d27", borderRadius: "0.75rem",
          padding: "0.75rem 1.25rem", border: "1px solid #2a2d3a",
        }}>
          {[
            { key: "normal",        label: "Normal" },
            { key: "low",           label: "Low" },
            { key: "high",          label: "High" },
            { key: "critical_low",  label: "Critical Low" },
            { key: "critical_high", label: "Critical High" },
          ].map(({ key, label }) => {
            const n = statusCounts[key] ?? 0;
            if (n === 0) return null;
            const c = STATUS_COLOR[key];
            return (
              <div key={key} style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <div style={{ width: 8, height: 8, borderRadius: "50%", backgroundColor: c }} />
                <span style={{ fontSize: "0.78rem", color: "#94a3b8" }}>
                  <span style={{ fontWeight: 700, color: c }}>{n}</span> {label}
                </span>
              </div>
            );
          })}
          <div style={{ marginLeft: "auto", fontSize: "0.7rem", color: "#475569" }}>
            Latest from {fmtDate(uploads[0]?.test_date ?? null)}
          </div>
        </div>
      )}

      {latestList.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "180px 1fr", gap: "1rem" }}>
          {/* ── Category sidebar ── */}
          <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
            {categories.map(cat => {
              const ms = byCategory[cat];
              const abnormal = ms.filter(m => m.status !== "normal").length;
              const active = displayCategory === cat;
              return (
                <button
                  key={cat}
                  onClick={() => setActiveCategory(cat)}
                  style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "0.4rem 0.75rem", borderRadius: "0.375rem",
                    backgroundColor: active ? `${CAT_COLORS[cat]}18` : "transparent",
                    border: active ? `1px solid ${CAT_COLORS[cat]}40` : "1px solid transparent",
                    color: active ? CAT_COLORS[cat] : "#64748b",
                    cursor: "pointer", fontSize: "0.78rem", fontWeight: active ? 600 : 400,
                    textAlign: "left",
                  }}
                >
                  <span>{CAT_LABELS[cat] ?? cat}</span>
                  <div style={{ display: "flex", gap: "4px", alignItems: "center" }}>
                    {abnormal > 0 && (
                      <span style={{
                        fontSize: "0.6rem", fontWeight: 700,
                        backgroundColor: "#ef444418", color: "#ef4444",
                        borderRadius: "0.2rem", padding: "1px 4px",
                      }}>{abnormal}</span>
                    )}
                    <span style={{ fontSize: "0.65rem", color: "#475569" }}>{ms.length}</span>
                  </div>
                </button>
              );
            })}
          </div>

          {/* ── Marker cards grid ── */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "0.6rem", alignContent: "start" }}>
            {displayMarkers.map(m => (
              <MarkerCard
                key={m.marker_canonical}
                m={m}
                onClick={() => setTrendMarker(m.marker_canonical)}
              />
            ))}
          </div>
        </div>
      )}

      {/* ── Uploads history ── */}
      {uploads.length > 0 && (
        <div style={{ marginTop: "0.5rem" }}>
          <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "#64748b", marginBottom: "0.5rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Uploaded Reports
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
            {uploads.map(u => (
              <div key={u.id} style={{
                display: "flex", alignItems: "center", justifyContent: "space-between",
                backgroundColor: "#1a1d27", borderRadius: "0.5rem",
                padding: "0.6rem 1rem", border: "1px solid #2a2d3a",
                fontSize: "0.78rem", flexWrap: "wrap", gap: "0.5rem",
              }}>
                <div>
                  <span style={{ color: "#cbd5e1", fontWeight: 600 }}>{u.filename}</span>
                  {u.lab_name && <span style={{ color: "#64748b", marginLeft: "0.5rem" }}>· {u.lab_name}</span>}
                </div>
                <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
                  <span style={{ color: "#64748b" }}>Test: <span style={{ color: "#94a3b8" }}>{fmtDate(u.test_date)}</span></span>
                  <span style={{ color: "#475569" }}>{u.records_extracted} markers</span>
                  <button
                    onClick={() => handleDelete(u.id)}
                    style={{ background: "none", border: "none", color: "#475569", cursor: "pointer", fontSize: "0.9rem" }}
                  >🗑</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Empty state ── */}
      {!loading && latestList.length === 0 && (
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
          gap: "1rem", padding: "4rem 2rem", color: "#475569", textAlign: "center",
          backgroundColor: "#1a1d27", borderRadius: "0.75rem", border: "1px dashed #2a2d3a",
        }}>
          <div style={{ fontSize: "2.5rem" }}>🩸</div>
          <div>
            <div style={{ fontSize: "1rem", fontWeight: 600, color: "#64748b", marginBottom: "0.25rem" }}>No lab results yet</div>
            <div style={{ fontSize: "0.82rem" }}>Upload a PDF blood work report to start tracking your biomarkers over time.</div>
          </div>
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            style={{
              backgroundColor: "#6366f1", color: "#fff", border: "none",
              borderRadius: "0.5rem", padding: "0.6rem 1.5rem",
              fontSize: "0.85rem", fontWeight: 600, cursor: "pointer",
            }}
          >Upload Your First Report</button>
        </div>
      )}

      {/* ── Modals ── */}
      {extracted && (
        <ReviewModal
          extracted={extracted}
          onConfirm={handleConfirm}
          onCancel={() => setExtracted(null)}
        />
      )}
      {trendMarker && (
        <TrendModal
          marker={trendMarker}
          all={allData}
          onClose={() => setTrendMarker(null)}
        />
      )}
    </div>
  );
}
