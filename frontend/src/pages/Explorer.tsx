import { useState } from "react";
import { ChartPanel } from "../components/ChartPanel";
import { DateRangePicker } from "../components/DateRangePicker";
import { useApi } from "../hooks/useApi";
import { api } from "../api";

const DEFAULT_START = `${new Date().getFullYear()}-01-01`;
const DEFAULT_END = new Date().toISOString().slice(0, 10);

const RESAMPLE_OPTIONS = [
  { label: "Raw (hourly)", value: "1h" },
  { label: "Daily", value: "1D" },
  { label: "Weekly", value: "1W" },
  { label: "Monthly", value: "1ME" },
];

export function Explorer() {
  const [start, setStart] = useState(DEFAULT_START);
  const [end, setEnd] = useState(DEFAULT_END);
  const [metric, setMetric] = useState("HeartRate");
  const [resample, setResample] = useState("1D");

  const { data: metrics } = useApi(() => api.availableMetrics(), []);
  const { data: series, loading } = useApi(
    () => api.metricSeries(metric, { start, end, resample }),
    [metric, start, end, resample]
  );
  const { data: stats } = useApi(
    () => api.metricStats(metric, { start, end }),
    [metric, start, end]
  );

  const data = series ?? [];
  const dateKey = data[0] && "date" in data[0] ? "date" : Object.keys(data[0] ?? {})[0];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-semibold" style={{ color: "#e2e8f0" }}>Metric Explorer</h1>
        <DateRangePicker start={start} end={end} onChange={(s, e) => { setStart(s); setEnd(e); }} />
      </div>

      <div className="flex gap-3 flex-wrap items-center">
        <select
          value={metric}
          onChange={(e) => setMetric(e.target.value)}
          className="px-3 py-1.5 rounded-md text-sm"
          style={{ backgroundColor: "#2a2d3a", color: "#e2e8f0", border: "1px solid #3a3d4a" }}
        >
          {(metrics ?? []).map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>

        <div className="flex gap-1">
          {RESAMPLE_OPTIONS.map((o) => (
            <button
              key={o.value}
              onClick={() => setResample(o.value)}
              className="px-3 py-1 rounded-md text-xs font-medium"
              style={{
                backgroundColor: resample === o.value ? "#6366f1" : "#2a2d3a",
                color: resample === o.value ? "#fff" : "#94a3b8",
                border: "1px solid #3a3d4a",
                cursor: "pointer",
              }}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>

      {/* Stats bar */}
      {stats && (
        <div className="grid grid-cols-4 md:grid-cols-8 gap-2">
          {[
            { label: "Count", value: stats.count.toLocaleString() },
            { label: "Mean",  value: `${stats.mean} ${stats.unit}` },
            { label: "Median",value: `${stats.median} ${stats.unit}` },
            { label: "StdDev",value: `±${stats.std}` },
            { label: "Min",   value: `${stats.min} ${stats.unit}` },
            { label: "Max",   value: `${stats.max} ${stats.unit}` },
            { label: "Q25",   value: `${stats.q25}` },
            { label: "Q75",   value: `${stats.q75}` },
          ].map((s) => (
            <div key={s.label} className="rounded-lg p-2 text-center" style={{ backgroundColor: "#1a1d27", border: "1px solid #2a2d3a" }}>
              <div className="text-xs" style={{ color: "#64748b" }}>{s.label}</div>
              <div className="text-sm font-medium mt-0.5" style={{ color: "#e2e8f0" }}>{s.value}</div>
            </div>
          ))}
        </div>
      )}

      <ChartPanel
        title={`${metric} · ${resample}`}
        data={data}
        dateKey={dateKey}
        series={[{ key: "value_num", color: "#6366f1" }]}
        unit={stats?.unit}
        chartType="area"
        height={320}
        loading={loading}
      />
    </div>
  );
}
