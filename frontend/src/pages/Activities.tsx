import { useState, useMemo, useRef } from "react";
import { Sparkles, X, Search } from "lucide-react";
import { useApi } from "../hooks/useApi";
import { api } from "../api";
import type { ActivityRecord, AISearchResult } from "../api";

const SURFACE = { backgroundColor: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: "0.75rem" };
const RUN_COLOR = "#6366f1";
const BIKE_COLOR = "#f59e0b";
const today = new Date().toISOString().slice(0, 10);
const ytdStart = `${new Date().getFullYear()}-01-01`;

function fmt(v: number | null, unit: string, decimals = 1): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${v.toFixed(decimals)} ${unit}`;
}
function fmtPace(v: number | null): string {
  if (v == null || !Number.isFinite(v) || v <= 0) return "—";
  return `${Math.floor(v)}:${String(Math.round((v % 1) * 60)).padStart(2, "0")}`;
}
function fmtDur(min: number | null): string {
  if (min == null || !Number.isFinite(min)) return "—";
  const h = Math.floor(min / 60), m = Math.round(min % 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

type SortKey = keyof ActivityRecord | "pace_min_km";
type SortDir = "asc" | "desc";

const COLUMNS: { key: SortKey; label: string; width?: string }[] = [
  { key: "date",         label: "Date",       width: "90px" },
  { key: "type",         label: "Sport",      width: "80px" },
  { key: "name",         label: "Name",       width: "180px" },
  { key: "distance_km",  label: "Dist (km)",  width: "80px" },
  { key: "duration_min", label: "Time",       width: "70px" },
  { key: "pace_min_km",  label: "Pace",       width: "70px" },
  { key: "avg_hr",       label: "Avg HR",     width: "70px" },
  { key: "elevation_m",  label: "Elev (m)",   width: "70px" },
  { key: "suffer_score", label: "Effort",     width: "60px" },
  { key: "avg_cadence",  label: "Cadence",    width: "70px" },
  { key: "avg_watts",    label: "Watts",      width: "60px" },
];

export function Activities() {
  const [sport, setSport]   = useState("all");
  const [start, setStart]   = useState(ytdStart);
  const [end, setEnd]       = useState(today);
  const [search, setSearch] = useState("");
  const [page, setPage]     = useState(1);
  const [sortBy, setSortBy] = useState<SortKey>("date");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  // AI search state
  const [aiQuery, setAiQuery] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResult, setAiResult] = useState<AISearchResult | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);
  const aiInputRef = useRef<HTMLInputElement>(null);

  async function runAiSearch() {
    const q = aiQuery.trim();
    if (!q) return;
    setAiLoading(true);
    setAiError(null);
    setAiResult(null);
    try {
      const result = await api.aiSearch(q);
      setAiResult(result);
    } catch (e) {
      setAiError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setAiLoading(false);
    }
  }

  function clearAiSearch() {
    setAiQuery("");
    setAiResult(null);
    setAiError(null);
  }

  const PAGE_SIZE = 50;

  const { data, loading } = useApi(() => api.activitiesList({
    sport: sport === "all" ? undefined : sport,
    start, end,
    sort_by: sortBy as string,
    sort_dir: sortDir,
    page, page_size: PAGE_SIZE,
    search: search || undefined,
  }), [sport, start, end, search, page, sortBy, sortDir]);

  const records: ActivityRecord[] = data?.records ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  function toggleSort(key: SortKey) {
    if (sortBy === key) {
      setSortDir(d => d === "desc" ? "asc" : "desc");
    } else {
      setSortBy(key);
      setSortDir("desc");
    }
    setPage(1);
  }

  function renderCell(r: ActivityRecord, key: SortKey) {
    const color = r.type?.includes("Cycling") ? BIKE_COLOR : RUN_COLOR;
    switch (key) {
      case "date":         return <span style={{ color: "#94a3b8" }}>{r.date}</span>;
      case "type":         return <span style={{ color, fontWeight: 600, fontSize: "0.7rem" }}>{r.type?.replace("HKWorkoutActivityType", "") || "—"}</span>;
      case "name":         return <span style={{ color: "#e2e8f0", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.name || <span style={{ color: "#475569" }}>—</span>}</span>;
      case "distance_km":  return <span style={{ color: "#e2e8f0" }}>{fmt(r.distance_km, "", 1).trim() || "—"}</span>;
      case "duration_min": return <span style={{ color: "#e2e8f0" }}>{fmtDur(r.duration_min)}</span>;
      case "pace_min_km":  return <span style={{ color: "#e2e8f0" }}>{r.type?.includes("Cycling") ? fmt(r.distance_km && r.duration_min ? 60 / (r.duration_min / r.distance_km!) : null, "km/h", 1) : fmtPace(r.pace_min_km)}</span>;
      case "avg_hr":       return <span style={{ color: r.avg_hr ? "#ef4444" : "#475569" }}>{r.avg_hr ? `${Math.round(r.avg_hr)}` : "—"}</span>;
      case "elevation_m":  return <span style={{ color: "#e2e8f0" }}>{r.elevation_m ? Math.round(r.elevation_m) : "—"}</span>;
      case "suffer_score": return <span style={{ color: "#f97316" }}>{r.suffer_score ? Math.round(r.suffer_score) : "—"}</span>;
      case "avg_cadence":  return <span style={{ color: "#e2e8f0" }}>{r.avg_cadence ? Math.round(r.avg_cadence) : "—"}</span>;
      case "avg_watts":    return <span style={{ color: "#e2e8f0" }}>{r.avg_watts ? Math.round(r.avg_watts) : "—"}</span>;
      default:             return "—";
    }
  }

  const sportCounts = useMemo(() => {
    const run = records.filter(r => r.type?.includes("Running")).length;
    const cyc = records.filter(r => r.type?.includes("Cycling")).length;
    return { run, cyc, other: records.length - run - cyc };
  }, [records]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.75rem" }}>
        <h1 style={{ color: "#e2e8f0", fontSize: "1.25rem", fontWeight: 600, margin: 0 }}>Activities</h1>
        <span style={{ color: "#64748b", fontSize: "0.75rem" }}>{total.toLocaleString()} activities</span>
      </div>

      {/* AI Search */}
      <div style={{
        ...SURFACE,
        padding: "0.75rem 1rem",
        display: "flex",
        gap: "0.6rem",
        alignItems: "center",
        background: "rgba(99,102,241,0.04)",
        border: "1px solid rgba(99,102,241,0.15)",
      }}>
        <Sparkles size={14} style={{ color: "#818cf8", flexShrink: 0 }} />
        <input
          ref={aiInputRef}
          value={aiQuery}
          onChange={e => setAiQuery(e.target.value)}
          onKeyDown={e => e.key === "Enter" && runAiSearch()}
          placeholder="Ask AI: &quot;my fastest 5 runs this year&quot;, &quot;rides over 100km&quot;, &quot;longest run in 2025&quot;..."
          style={{
            flex: 1,
            backgroundColor: "transparent",
            color: "#e2e8f0",
            border: "none",
            outline: "none",
            fontSize: "0.82rem",
            padding: "0.25rem 0",
          }}
        />
        {aiQuery && !aiLoading && (
          <button onClick={clearAiSearch} style={{ background: "none", border: "none", cursor: "pointer", padding: 0, display: "flex" }}>
            <X size={14} style={{ color: "#64748b" }} />
          </button>
        )}
        <button
          onClick={runAiSearch}
          disabled={aiLoading || !aiQuery.trim()}
          style={{
            background: aiLoading ? "rgba(99,102,241,0.3)" : "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
            color: "#fff",
            border: "none",
            borderRadius: "0.375rem",
            padding: "0.35rem 0.85rem",
            fontSize: "0.75rem",
            fontWeight: 600,
            cursor: aiLoading ? "wait" : "pointer",
            display: "flex",
            alignItems: "center",
            gap: "0.35rem",
            flexShrink: 0,
          }}
        >
          <Search size={12} />
          {aiLoading ? "Searching..." : "Search"}
        </button>
      </div>

      {/* AI Search Results */}
      {aiError && (
        <div style={{ ...SURFACE, padding: "0.75rem 1rem", borderColor: "#ef4444", color: "#f87171", fontSize: "0.8rem" }}>
          {aiError}
        </div>
      )}
      {aiResult && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {/* Summary + filters badge */}
          <div style={{
            ...SURFACE,
            padding: "0.85rem 1rem",
            background: "rgba(99,102,241,0.06)",
            border: "1px solid rgba(99,102,241,0.15)",
          }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem" }}>
              <div>
                <div style={{ color: "#e2e8f0", fontSize: "0.82rem", marginBottom: "0.25rem" }}>{aiResult.summary}</div>
                <div style={{ color: "#64748b", fontSize: "0.7rem" }}>
                  {aiResult.total} matching {aiResult.total === 1 ? "activity" : "activities"}
                  {Object.keys(aiResult.filters).length > 0 && (
                    <span> · Filters: {Object.entries(aiResult.filters).map(([k, v]) => `${k}=${v}`).join(", ")}</span>
                  )}
                </div>
              </div>
              <button onClick={clearAiSearch} style={{
                background: "#2a2d3a", border: "1px solid #3a3d4a", borderRadius: "0.375rem",
                padding: "0.25rem 0.65rem", fontSize: "0.72rem", color: "#94a3b8", cursor: "pointer",
              }}>
                Clear
              </button>
            </div>
          </div>

          {/* AI Results table */}
          <div style={{ ...SURFACE, overflow: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.78rem" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #2a2d3a" }}>
                  {COLUMNS.map(col => (
                    <th key={col.key} style={{
                      padding: "0.6rem 0.75rem", textAlign: "left",
                      color: "#64748b", fontWeight: 600, fontSize: "0.7rem",
                      letterSpacing: "0.04em", whiteSpace: "nowrap", minWidth: col.width,
                    }}>
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {aiResult.records.length === 0 ? (
                  <tr><td colSpan={COLUMNS.length} style={{ padding: "2rem", textAlign: "center", color: "#64748b" }}>No matching activities</td></tr>
                ) : aiResult.records.map((r, i) => (
                  <tr key={i} style={{
                    borderBottom: "1px solid #1e2130",
                    backgroundColor: i % 2 === 0 ? "transparent" : "#161822",
                  }}>
                    {COLUMNS.map(col => (
                      <td key={col.key} style={{ padding: "0.45rem 0.75rem", verticalAlign: "middle", maxWidth: col.width }}>
                        {renderCell(r, col.key)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Filters */}
      {!aiResult && <div style={{ ...SURFACE, padding: "1rem", display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
        {/* Sport */}
        <div style={{ display: "flex", gap: "0.25rem" }}>
          {(["all", "Running", "Cycling"] as const).map(s => (
            <button key={s} onClick={() => { setSport(s); setPage(1); }} style={{
              padding: "0.25rem 0.65rem", borderRadius: "0.375rem", fontSize: "0.72rem", fontWeight: 600,
              cursor: "pointer", border: "1px solid #3a3d4a",
              backgroundColor: sport === s ? (s === "Running" ? RUN_COLOR : s === "Cycling" ? BIKE_COLOR : "#6366f1") : "#2a2d3a",
              color: sport === s ? "#fff" : "#94a3b8",
            }}>{s === "all" ? "All" : s}</button>
          ))}
        </div>

        {/* Search */}
        <input
          value={search} onChange={e => { setSearch(e.target.value); setPage(1); }}
          placeholder="Search activity name…"
          style={{ backgroundColor: "#2a2d3a", color: "#e2e8f0", border: "1px solid #3a3d4a", borderRadius: "0.375rem", padding: "0.3rem 0.65rem", fontSize: "0.75rem", width: "180px" }}
        />

        {/* Date range */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <input type="date" value={start} max={end} onChange={e => { setStart(e.target.value); setPage(1); }}
            style={{ backgroundColor: "#2a2d3a", color: "#94a3b8", border: "1px solid #3a3d4a", borderRadius: "0.375rem", padding: "0.25rem 0.5rem", fontSize: "0.75rem" }} />
          <span style={{ color: "#64748b" }}>→</span>
          <input type="date" value={end} min={start} max={today} onChange={e => { setEnd(e.target.value); setPage(1); }}
            style={{ backgroundColor: "#2a2d3a", color: "#94a3b8", border: "1px solid #3a3d4a", borderRadius: "0.375rem", padding: "0.25rem 0.5rem", fontSize: "0.75rem" }} />
        </div>

        {/* Quick presets */}
        <div style={{ display: "flex", gap: "0.25rem", marginLeft: "auto" }}>
          {[
            { label: "YTD", s: ytdStart, e: today },
            { label: "2025", s: "2025-01-01", e: "2025-12-31" },
            { label: "2024", s: "2024-01-01", e: "2024-12-31" },
            { label: "All",  s: "2012-01-01", e: today },
          ].map(p => (
            <button key={p.label} onClick={() => { setStart(p.s); setEnd(p.e); setPage(1); }} style={{
              padding: "0.2rem 0.55rem", borderRadius: "0.375rem", fontSize: "0.7rem", fontWeight: 600,
              cursor: "pointer", border: "1px solid #3a3d4a",
              backgroundColor: start === p.s && end === p.e ? "#6366f1" : "#2a2d3a",
              color: start === p.s && end === p.e ? "#fff" : "#94a3b8",
            }}>{p.label}</button>
          ))}
        </div>
      </div>}

      {/* Table */}
      {!aiResult && <div style={{ ...SURFACE, overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.78rem" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #2a2d3a" }}>
              {COLUMNS.map(col => (
                <th key={col.key} onClick={() => toggleSort(col.key)}
                  style={{
                    padding: "0.6rem 0.75rem", textAlign: "left", cursor: "pointer",
                    color: sortBy === col.key ? "#e2e8f0" : "#64748b",
                    fontWeight: 600, fontSize: "0.7rem", letterSpacing: "0.04em",
                    whiteSpace: "nowrap", minWidth: col.width,
                    userSelect: "none",
                    backgroundColor: sortBy === col.key ? "#1e2130" : "transparent",
                  }}>
                  {col.label} {sortBy === col.key ? (sortDir === "desc" ? "↓" : "↑") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={COLUMNS.length} style={{ padding: "2rem", textAlign: "center", color: "#64748b" }}>Loading…</td></tr>
            ) : records.length === 0 ? (
              <tr><td colSpan={COLUMNS.length} style={{ padding: "2rem", textAlign: "center", color: "#64748b" }}>No activities found</td></tr>
            ) : records.map((r, i) => (
              <tr key={i} style={{
                borderBottom: "1px solid #1e2130",
                backgroundColor: i % 2 === 0 ? "transparent" : "#161822",
              }}>
                {COLUMNS.map(col => (
                  <td key={col.key} style={{ padding: "0.45rem 0.75rem", verticalAlign: "middle", maxWidth: col.width }}>
                    {renderCell(r, col.key)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>}

      {/* Pagination */}
      {!aiResult && totalPages > 1 && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "0.5rem" }}>
          <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} style={{
            padding: "0.25rem 0.75rem", borderRadius: "0.375rem", fontSize: "0.75rem",
            backgroundColor: "#2a2d3a", color: page === 1 ? "#475569" : "#94a3b8",
            border: "1px solid #3a3d4a", cursor: page === 1 ? "not-allowed" : "pointer",
          }}>← Prev</button>
          <span style={{ color: "#64748b", fontSize: "0.75rem" }}>
            Page {page} of {totalPages} · {total.toLocaleString()} total
          </span>
          <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages} style={{
            padding: "0.25rem 0.75rem", borderRadius: "0.375rem", fontSize: "0.75rem",
            backgroundColor: "#2a2d3a", color: page === totalPages ? "#475569" : "#94a3b8",
            border: "1px solid #3a3d4a", cursor: page === totalPages ? "not-allowed" : "pointer",
          }}>Next →</button>
        </div>
      )}
    </div>
  );
}
