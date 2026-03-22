import { useState } from "react";
import { ChartPanel } from "../components/ChartPanel";
import { DateRangePicker } from "../components/DateRangePicker";
import { useApi } from "../hooks/useApi";
import { api } from "../api";

const DEFAULT_START = "2025-11-01";
const DEFAULT_END = "2025-12-31";

export function Glucose({ embedded }: { embedded?: boolean } = {}) {
  const [start, setStart] = useState(DEFAULT_START);
  const [end, setEnd] = useState(DEFAULT_END);

  const { data: dailySeries, loading: dailyLoading } = useApi(
    () => api.daily({ start, end, metrics: "BloodGlucose_mean,BloodGlucose_min,BloodGlucose_max" }),
    [start, end]
  );

  const { data: rawSeries, loading: rawLoading } = useApi(
    () => api.metricSeries("BloodGlucose", { start, end, resample: "1h" }),
    [start, end]
  );

  const daily = dailySeries ?? [];
  const hourly = rawSeries ?? [];

  return (
    <div className="flex flex-col gap-6">
      {!embedded && (
        <div className="flex items-center justify-between flex-wrap gap-3">
          <h1 className="text-xl font-semibold" style={{ color: "#e2e8f0" }}>Blood Glucose</h1>
        </div>
      )}
      <div className="flex items-center justify-end flex-wrap gap-3">
        <DateRangePicker start={start} end={end} onChange={(s, e) => { setStart(s); setEnd(e); }} />
      </div>

      <div className="rounded-lg px-3 py-2 text-xs" style={{ backgroundColor: "#1e2d1e", border: "1px solid #166534", color: "#86efac" }}>
        Data source: LinX CGM (MicroTech Medical) · Nov–Dec 2025 · 21,294 readings
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartPanel
          title="Blood glucose — daily mean / min / max"
          data={daily}
          series={[
            { key: "BloodGlucose_mean", color: "#f59e0b", name: "Mean" },
            { key: "BloodGlucose_min",  color: "#10b981", name: "Min" },
            { key: "BloodGlucose_max",  color: "#ef4444", name: "Max" },
          ]}
          unit="mg/dL"
          chartType="line"
          loading={dailyLoading}
          syncId="glucose"
        />
        <ChartPanel
          title="Blood glucose — hourly average"
          data={hourly}
          series={[{ key: "value_num", color: "#f59e0b" }]}
          unit="mg/dL"
          chartType="area"
          loading={rawLoading}
          syncId="glucose"
        />
      </div>

      {/* Reference ranges */}
      <div className="rounded-xl p-4" style={{ backgroundColor: "#1a1d27", border: "1px solid #2a2d3a" }}>
        <div className="text-sm font-medium mb-3" style={{ color: "#94a3b8" }}>Reference ranges</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          {[
            { label: "Hypoglycemia",   range: "< 70",    color: "#ef4444" },
            { label: "Normal fasting", range: "70–99",   color: "#10b981" },
            { label: "Pre-diabetic",   range: "100–125", color: "#f59e0b" },
            { label: "Diabetic",       range: "> 126",   color: "#f97316" },
          ].map((r) => (
            <div key={r.label} className="rounded-lg p-3" style={{ backgroundColor: "#2a2d3a" }}>
              <div style={{ color: r.color }} className="font-semibold">{r.range} mg/dL</div>
              <div style={{ color: "#64748b" }}>{r.label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
