import { useState } from "react";
import { ChartPanel } from "../components/ChartPanel";
import { DateRangePicker } from "../components/DateRangePicker";
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
      metrics: "BodyMass,BodyMassIndex,BodyFatPercentage,LeanBodyMass,VO2Max",
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

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartPanel
          title="Body weight"
          data={data.filter(d => d.BodyMass != null)}
          series={[{ key: "BodyMass", color: "#f59e0b" }]}
          unit="kg"
          chartType="line"
          loading={loading}
          syncId="body"
        />
        <ChartPanel
          title="Body fat %"
          data={data.filter(d => d.BodyFatPercentage != null)}
          series={[{ key: "BodyFatPercentage", color: "#f97316" }]}
          unit="%"
          chartType="area"
          loading={loading}
          syncId="body"
        />
        <ChartPanel
          title="BMI"
          data={data.filter(d => d.BodyMassIndex != null)}
          series={[{ key: "BodyMassIndex", color: "#84cc16" }]}
          unit="kg/m²"
          chartType="line"
          loading={loading}
        />
        <ChartPanel
          title="Lean body mass"
          data={data.filter(d => d.LeanBodyMass != null)}
          series={[{ key: "LeanBodyMass", color: "#06b6d4" }]}
          unit="kg"
          chartType="area"
          loading={loading}
        />
        <ChartPanel
          title="VO₂ Max"
          data={data.filter(d => d.VO2Max != null)}
          series={[{ key: "VO2Max", color: "#6366f1" }]}
          unit="mL/kg/min"
          chartType="line"
          loading={loading}
        />
      </div>
    </div>
  );
}
