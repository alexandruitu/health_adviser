import { useState, useCallback } from "react";
import { ChartPanel } from "../components/ChartPanel";
import { DateRangePicker } from "../components/DateRangePicker";
import { AdviserPanel } from "../components/AdviserPanel";
import { useApi } from "../hooks/useApi";
import { api } from "../api";

const DEFAULT_START = `${new Date().getFullYear()}-01-01`;
const DEFAULT_END = new Date().toISOString().slice(0, 10);

export function Body() {
  const [start, setStart] = useState(DEFAULT_START);
  const [end, setEnd] = useState(DEFAULT_END);

  const { data: daily, loading } = useApi(
    () => api.daily({
      start, end,
      metrics: "BodyMass,BodyMassIndex,BodyFatPercentage,LeanBodyMass,VO2Max,VO2MaxCycling",
    }),
    [start, end]
  );

  const data = daily ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-semibold" style={{ color: "#e2e8f0" }}>Body</h1>
        <DateRangePicker start={start} end={end} onChange={(s, e) => { setStart(s); setEnd(e); }} />
      </div>

      <AdviserPanel
        tab="body composition"
        start={start}
        end={end}
        gatherData={useCallback(() => {
          if (!data.length) return {};
          const metrics = ["BodyMass", "BodyFatPercentage", "BodyMassIndex", "LeanBodyMass", "VO2Max", "VO2MaxCycling"];
          const summary: Record<string, unknown> = { period: `${start} to ${end}`, days: data.length };
          for (const m of metrics) {
            const vals = data.map(d => d[m]).filter(v => v != null).map(Number);
            if (vals.length > 0) {
              summary[m] = { avg: +(vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1), min: +Math.min(...vals).toFixed(1), max: +Math.max(...vals).toFixed(1), latest: +vals[vals.length - 1].toFixed(1), count: vals.length };
            }
          }
          summary.recent_7d = data.slice(-7);
          return summary;
        }, [data, start, end])}
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartPanel
          title="Body weight"
          data={data.filter(d => d.BodyMass != null)}
          series={[{ key: "BodyMass", color: "#f59e0b" }]}
          unit="kg"
          chartType="line"
          loading={loading}
          syncId="body"
          start={start} end={end}
        />
        <ChartPanel
          title="Body fat %"
          data={data.filter(d => d.BodyFatPercentage != null)}
          series={[{ key: "BodyFatPercentage", color: "#f97316" }]}
          unit="%"
          chartType="area"
          loading={loading}
          syncId="body"
          start={start} end={end}
        />
        <ChartPanel
          title="BMI"
          data={data.filter(d => d.BodyMassIndex != null)}
          series={[{ key: "BodyMassIndex", color: "#84cc16" }]}
          unit="kg/m²"
          chartType="line"
          loading={loading}
          start={start} end={end}
        />
        <ChartPanel
          title="Lean body mass"
          data={data.filter(d => d.LeanBodyMass != null)}
          series={[{ key: "LeanBodyMass", color: "#06b6d4" }]}
          unit="kg"
          chartType="area"
          loading={loading}
          start={start} end={end}
        />
        <ChartPanel
          title="VO₂ Max · Running"
          data={data.filter(d => d.VO2Max != null)}
          series={[{ key: "VO2Max", color: "#6366f1" }]}
          unit="mL/kg/min"
          chartType="line"
          loading={loading}
          start={start} end={end}
        />
        <ChartPanel
          title="VO₂ Max · Cycling"
          data={data.filter(d => d.VO2MaxCycling != null)}
          series={[{ key: "VO2MaxCycling", color: "#8b5cf6" }]}
          unit="mL/kg/min"
          chartType="line"
          loading={loading}
          start={start} end={end}
        />
      </div>
    </div>
  );
}
