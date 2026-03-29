import { useState, useCallback } from "react";
import { ChartPanel } from "../components/ChartPanel";
import { DateRangePicker } from "../components/DateRangePicker";
import { AdviserPanel } from "../components/AdviserPanel";
import { useApi } from "../hooks/useApi";
import { api } from "../api";

const DEFAULT_START = "2018-01-01";
const DEFAULT_END   = new Date().toISOString().slice(0, 10);

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function hasData(data: Record<string, any>[], keys: string[]): boolean {
  return data.some((row) =>
    keys.some((k) => row[k] != null && !isNaN(Number(row[k])))
  );
}

export function Heart() {
  const [start, setStart] = useState(DEFAULT_START);
  const [end,   setEnd]   = useState(DEFAULT_END);

  const { data: daily, loading } = useApi(
    () => api.daily({
      start, end,
      metrics: [
        "HeartRate_mean", "HeartRate_min", "HeartRate_max",
        "RestingHeartRate",
        "HeartRateVariabilitySDNN",
        "WalkingHeartRateAverage",
        "BloodPressureSystolic", "BloodPressureDiastolic",
        "OxygenSaturation",
        "RespiratoryRate",
      ].join(","),
    }),
    [start, end]
  );

  const data = daily ?? [];

  const panels = [
    {
      title: "Heart rate — daily mean / min / max",
      series: [
        { key: "HeartRate_mean", color: "#f43f5e", name: "Mean" },
        { key: "HeartRate_max",  color: "#f97316", name: "Max"  },
        { key: "HeartRate_min",  color: "#10b981", name: "Min"  },
      ],
      unit: "bpm",
      chartType: "line" as const,
      syncId: "heart",
    },
    {
      title: "Resting heart rate",
      series: [{ key: "RestingHeartRate", color: "#f43f5e" }],
      unit: "bpm",
      chartType: "area" as const,
      syncId: "heart",
    },
    {
      title: "Heart rate variability (SDNN)",
      series: [{ key: "HeartRateVariabilitySDNN", color: "#10b981" }],
      unit: "ms",
      chartType: "area" as const,
    },
    {
      title: "Walking heart rate average",
      series: [{ key: "WalkingHeartRateAverage", color: "#6366f1" }],
      unit: "bpm",
      chartType: "line" as const,
    },
    {
      title: "Blood pressure",
      series: [
        { key: "BloodPressureSystolic",  color: "#ef4444", name: "Systolic"  },
        { key: "BloodPressureDiastolic", color: "#f97316", name: "Diastolic" },
      ],
      unit: "mmHg",
      chartType: "line" as const,
    },
    {
      title: "Blood oxygen (SpO₂)",
      series: [{ key: "OxygenSaturation", color: "#06b6d4", name: "SpO₂" }],
      unit: "%",
      chartType: "area" as const,
    },
    {
      title: "Respiratory rate",
      series: [{ key: "RespiratoryRate", color: "#8b5cf6", name: "Breaths/min" }],
      unit: "br/min",
      chartType: "area" as const,
    },
  ];

  // After loading, only show panels that have at least one non-null value
  const visiblePanels = loading
    ? panels
    : panels.filter((p) => hasData(data, p.series.map((s) => s.key)));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-semibold" style={{ color: "#e2e8f0" }}>Heart</h1>
        <DateRangePicker start={start} end={end} onChange={(s, e) => { setStart(s); setEnd(e); }} />
      </div>

      <AdviserPanel
        tab="heart"
        start={start}
        end={end}
        gatherData={useCallback(() => {
          if (!data.length) return {};
          // Compute summary stats for the adviser
          const metrics = ["HeartRate_mean", "HeartRate_max", "HeartRate_min", "RestingHeartRate", "HeartRateVariabilitySDNN", "WalkingHeartRateAverage", "BloodPressureSystolic", "BloodPressureDiastolic", "OxygenSaturation", "RespiratoryRate"];
          const summary: Record<string, unknown> = { period: `${start} to ${end}`, days: data.length };
          for (const m of metrics) {
            const vals = data.map(d => d[m]).filter(v => v != null).map(Number);
            if (vals.length > 0) {
              summary[m] = { avg: +(vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1), min: +Math.min(...vals).toFixed(1), max: +Math.max(...vals).toFixed(1), count: vals.length };
            }
          }
          // Include recent 7 days of raw data for trend context
          summary.recent_7d = data.slice(-7);
          return summary;
        }, [data, start, end])}
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {visiblePanels.map((p) => (
          <ChartPanel
            key={p.title}
            title={p.title}
            data={data}
            series={p.series}
            unit={p.unit}
            chartType={p.chartType}
            height={300}
            loading={loading}
            syncId={"syncId" in p ? (p as { syncId?: string }).syncId : undefined}
            start={start}
            end={end}
          />
        ))}
      </div>
    </div>
  );
}
