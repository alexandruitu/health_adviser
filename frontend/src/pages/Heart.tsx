import { useState } from "react";
import { ChartPanel } from "../components/ChartPanel";
import { DateRangePicker } from "../components/DateRangePicker";
import { useApi } from "../hooks/useApi";
import { api } from "../api";

const DEFAULT_START = `${new Date().getFullYear()}-01-01`;
const DEFAULT_END   = new Date().toISOString().slice(0, 10);

// Blood pressure data only exists Oct–Dec 2024
const BP_START = "2024-10-01";
const BP_END   = "2024-12-31";

export function Heart() {
  const [start, setStart] = useState(DEFAULT_START);
  const [end,   setEnd]   = useState(DEFAULT_END);

  const { data: daily, loading } = useApi(
    () => api.daily({
      start, end,
      metrics: "HeartRate_mean,HeartRate_min,HeartRate_max,RestingHeartRate,HeartRateVariabilitySDNN,WalkingHeartRateAverage",
    }),
    [start, end]
  );

  const { data: bpData, loading: bpLoading } = useApi(
    () => api.daily({ start: BP_START, end: BP_END, metrics: "BloodPressureSystolic,BloodPressureDiastolic" }),
    []
  );

  const data = daily ?? [];
  const bp   = (bpData ?? []).filter((d: Record<string, unknown>) => d.BloodPressureSystolic != null);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-semibold" style={{ color: "#e2e8f0" }}>Heart</h1>
        <DateRangePicker start={start} end={end} onChange={(s, e) => { setStart(s); setEnd(e); }} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartPanel
          title="Heart rate — daily mean / min / max"
          data={data}
          series={[
            { key: "HeartRate_mean", color: "#f43f5e", name: "Mean" },
            { key: "HeartRate_max",  color: "#f97316", name: "Max"  },
            { key: "HeartRate_min",  color: "#10b981", name: "Min"  },
          ]}
          unit="bpm"
          chartType="line"
          loading={loading}
          syncId="heart"
        />
        <ChartPanel
          title="Resting heart rate"
          data={data}
          series={[{ key: "RestingHeartRate", color: "#f43f5e" }]}
          unit="bpm"
          chartType="area"
          loading={loading}
          syncId="heart"
        />
        <ChartPanel
          title="Heart rate variability (SDNN)"
          data={data}
          series={[{ key: "HeartRateVariabilitySDNN", color: "#10b981" }]}
          unit="ms"
          chartType="area"
          loading={loading}
        />
        <ChartPanel
          title="Walking heart rate average"
          data={data}
          series={[{ key: "WalkingHeartRateAverage", color: "#6366f1" }]}
          unit="bpm"
          chartType="line"
          loading={loading}
        />
        <ChartPanel
          title="Blood pressure · Oct–Dec 2024"
          data={bp}
          series={[
            { key: "BloodPressureSystolic",  color: "#ef4444", name: "Systolic"  },
            { key: "BloodPressureDiastolic", color: "#f97316", name: "Diastolic" },
          ]}
          unit="mmHg"
          chartType="line"
          loading={bpLoading}
        />
      </div>
    </div>
  );
}
