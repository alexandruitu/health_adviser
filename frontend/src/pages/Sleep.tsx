import { useState, useCallback } from "react";
import { ChartPanel } from "../components/ChartPanel";
import { DateRangePicker } from "../components/DateRangePicker";
import { AdviserPanel } from "../components/AdviserPanel";
import { ReadinessCard } from "../components/ReadinessCard";
import { useApi } from "../hooks/useApi";
import { api } from "../api";
import type { SleepWellnessDay } from "../api";

const DEFAULT_START = `${new Date().getFullYear()}-01-01`;
const DEFAULT_END = new Date().toISOString().slice(0, 10);

function WellnessCard({
  label, value, unit, color, icon,
}: {
  label: string; value: number | undefined | null; unit: string; color: string; icon: string;
}) {
  // Don't render the card at all if there's no data
  if (value == null) return null;
  const display = typeof value === "number" && value % 1 !== 0 ? value.toFixed(1) : String(value);
  return (
    <div style={{
      backgroundColor: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: "0.75rem",
      padding: "0.875rem 1.1rem", display: "flex", flexDirection: "column", gap: "0.25rem",
    }}>
      <div style={{ fontSize: "0.7rem", color: "#64748b", fontWeight: 600, letterSpacing: "0.04em" }}>
        {icon} {label}
      </div>
      <div style={{ fontSize: "1.4rem", fontWeight: 700, color, lineHeight: 1.1 }}>
        {display}
        <span style={{ fontSize: "0.75rem", fontWeight: 500, color: "#64748b", marginLeft: "0.25rem" }}>{unit}</span>
      </div>
    </div>
  );
}

/** Compute average of each wellness metric over all rows in the selected range.
 *  Returns null for metrics with no data (so cards can be hidden). */
function avgWellness(data: SleepWellnessDay[]): Record<string, number | null> {
  if (!data.length) return {};
  const keys = Object.keys(data[0]).filter(k => k !== "date");
  const result: Record<string, number | null> = {};
  for (const key of keys) {
    const vals = data.map(d => (d as Record<string, number | null>)[key]).filter((v): v is number => v != null);
    result[key] = vals.length > 0 ? Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 10) / 10 : null;
  }
  return result;
}

export function Sleep() {
  const [start, setStart] = useState(DEFAULT_START);
  const [end, setEnd] = useState(DEFAULT_END);

  const { data: sleep, loading } = useApi(() => api.sleep({ start, end }), [start, end]);
  const { data: wellness, loading: wLoading } = useApi(() => api.sleepWellness({ start, end }), [start, end]);
  const { data: readinessData } = useApi(() => api.readiness({ start, end }), [start, end]);

  const data = sleep ?? [];
  const wellnessData = wellness ?? [];
  const readinessSeries = readinessData ?? [];
  const todayReadiness = readinessSeries.length ? readinessSeries[readinessSeries.length - 1] : undefined;
  const avg = avgWellness(wellnessData);
  const nightCount = wellnessData.length;
  const isOneNight = nightCount === 1;

  // For AdviserPanel we still want the latest night
  const latest = wellnessData.length ? wellnessData[wellnessData.length - 1] : undefined;

  const bbColor = (v?: number | null) => v == null ? "#6366f1" : v >= 40 ? "#10b981" : v >= 20 ? "#f59e0b" : "#ef4444";
  const bbVal = avg.GarminBodyBatteryDuringSleep ?? avg.GarminBodyBatteryChange ?? null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-semibold" style={{ color: "#e2e8f0" }}>Sleep</h1>
        <DateRangePicker start={start} end={end} onChange={(s, e) => { setStart(s); setEnd(e); }} />
      </div>

      <AdviserPanel
        tab="sleep"
        start={start}
        end={end}
        gatherData={useCallback(() => {
          if (!data.length) return {};
          const summary: Record<string, unknown> = { period: `${start} to ${end}`, nights: data.length };
          for (const m of ["total_sleep_hours", "Deep", "REM", "Core", "Awake"]) {
            const vals = data.map(d => (d as Record<string, number | undefined>)[m]).filter(v => v != null).map(Number);
            if (vals.length > 0) {
              summary[m] = { avg: +(vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2), min: +Math.min(...vals).toFixed(2), max: +Math.max(...vals).toFixed(2), count: vals.length };
            }
          }
          if (latest) summary.latest_night_wellness = latest;
          summary.recent_7_nights = data.slice(-7);
          return summary;
        }, [data, latest, start, end])}
      />

      {/* ── Readiness Index ── */}
      {readinessSeries.length > 0 && (
        <ReadinessCard today={todayReadiness} period={readinessSeries} />
      )}

      {/* ── Readiness trend chart ── */}
      {readinessSeries.length > 1 && (
        <ChartPanel
          title="Readiness Index trend"
          data={readinessSeries}
          dateKey="date"
          series={[
            { key: "readiness",     color: "#10b981", name: "Readiness" },
            { key: "hrv_score",     color: "#8b5cf6", name: "HRV score" },
            { key: "sleep_score",   color: "#0ea5e9", name: "Sleep score" },
            { key: "battery_score", color: "#34d399", name: "Battery score" },
          ]}
          unit=""
          chartType="line"
          loading={false}
          start={start} end={end}
          yDomain={[0, 100]}
          referenceLines={[
            { y: 85, label: "Peak",     color: "#10b98166" },
            { y: 70, label: "High",     color: "#34d39966" },
            { y: 55, label: "Moderate", color: "#f59e0b66" },
            { y: 40, label: "Low",      color: "#f9731666" },
          ]}
        />
      )}

      {/* ── Garmin sleep wellness cards (avg over selected range) ── */}
      {(wellnessData.length > 0 || wLoading) && (
        <div>
          <div style={{ fontSize: "0.7rem", fontWeight: 700, color: "#475569", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "0.6rem" }}>
            {isOneNight ? "Last night · Garmin" : `Avg over ${nightCount} nights · Garmin`}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: "0.5rem" }}>
            <WellnessCard label="Sleep Score"     value={avg.GarminSleepScore}             unit="/ 100" color="#8b5cf6" icon="🌙" />
            <WellnessCard label="Overnight HR"    value={avg.GarminSleepHR}                unit="bpm"   color="#ef4444" icon="❤️" />
            <WellnessCard label="Avg Respiration" value={avg.GarminSleepRespiration}       unit="brpm"  color="#0ea5e9" icon="🫁" />
            <WellnessCard label="Low Respiration" value={avg.GarminSleepRespirationLow}    unit="brpm"  color="#38bdf8" icon="💨" />
            <WellnessCard label="Restless"         value={avg.GarminSleepRestless}          unit="times" color="#f59e0b" icon="😤" />
            <WellnessCard label="Sleep Stress"     value={avg.GarminAvgSleepStress}         unit="score" color="#f97316" icon="🧠" />
            <WellnessCard label="Battery +"        value={bbVal}                            unit="pts"   color={bbColor(bbVal)}    icon="⚡" />
            <WellnessCard label="Skin Temp Δ"      value={avg.GarminSkinTempChange}         unit="°C"    color="#a78bfa" icon="🌡️" />
          </div>
        </div>
      )}

      {/* ── Main sleep charts ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartPanel
          title="Total sleep duration"
          data={data}
          dateKey="night"
          series={[{ key: "total_sleep_hours", color: "#8b5cf6" }]}
          unit="hrs"
          chartType="bar"
          loading={loading}
          syncId="sleep"
          start={start} end={end}
        />
        <ChartPanel
          title="Sleep stages breakdown"
          data={data}
          dateKey="night"
          series={[
            { key: "Deep",  color: "#1d4ed8", name: "Deep" },
            { key: "REM",   color: "#7c3aed", name: "REM" },
            { key: "Core",  color: "#0891b2", name: "Core" },
            { key: "Awake", color: "#dc2626", name: "Awake" },
          ]}
          unit="hrs"
          chartType="area"
          loading={loading}
          syncId="sleep"
          start={start} end={end}
        />
        <ChartPanel
          title="Deep sleep"
          data={data}
          dateKey="night"
          series={[{ key: "Deep", color: "#1d4ed8" }]}
          unit="hrs"
          chartType="area"
          loading={loading}
          start={start} end={end}
        />
        <ChartPanel
          title="REM sleep"
          data={data}
          dateKey="night"
          series={[{ key: "REM", color: "#7c3aed" }]}
          unit="hrs"
          chartType="area"
          loading={loading}
          start={start} end={end}
        />
      </div>

      {/* ── Garmin wellness trend charts ── */}
      {wellnessData.length > 0 && (
        <>
          <div style={{ fontSize: "0.7rem", fontWeight: 700, color: "#475569", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            Garmin Sleep Wellness Trends
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <ChartPanel
              title="Sleep Score"
              data={wellnessData}
              dateKey="date"
              series={[{ key: "GarminSleepScore", color: "#8b5cf6", name: "Score" }]}
              unit="/ 100"
              chartType="area"
              loading={wLoading}
              start={start} end={end}
            />
            <ChartPanel
              title="Overnight Heart Rate"
              data={wellnessData}
              dateKey="date"
              series={[{ key: "GarminSleepHR", color: "#ef4444", name: "Avg overnight HR" }]}
              unit="bpm"
              chartType="line"
              loading={wLoading}
              start={start} end={end}
            />
            <ChartPanel
              title="Sleep Respiration"
              data={wellnessData}
              dateKey="date"
              series={[
                { key: "GarminSleepRespiration",    color: "#0ea5e9", name: "Avg" },
                { key: "GarminSleepRespirationLow", color: "#38bdf8", name: "Lowest" },
              ]}
              unit="brpm"
              chartType="area"
              loading={wLoading}
              start={start} end={end}
            />
            <ChartPanel
              title="Restless Moments"
              data={wellnessData}
              dateKey="date"
              series={[{ key: "GarminSleepRestless", color: "#f59e0b", name: "Restless" }]}
              unit="times"
              chartType="bar"
              loading={wLoading}
              start={start} end={end}
            />
            <ChartPanel
              title="Body Battery Charged During Sleep"
              data={wellnessData}
              dateKey="date"
              series={[
                { key: "GarminBodyBatteryDuringSleep", color: "#6366f1", name: "Battery +" },
                { key: "GarminBodyBatteryChange",      color: "#818cf8", name: "Battery (old)" },
              ]}
              unit="pts"
              chartType="bar"
              loading={wLoading}
              start={start} end={end}
            />
            <ChartPanel
              title="Sleep Stress"
              data={wellnessData}
              dateKey="date"
              series={[{ key: "GarminAvgSleepStress", color: "#f97316", name: "Avg Sleep Stress" }]}
              unit="score"
              chartType="line"
              loading={wLoading}
              start={start} end={end}
            />
          </div>
        </>
      )}

      {/* Sleep stats table */}
      <div className="rounded-xl p-4" style={{ backgroundColor: "#1a1d27", border: "1px solid #2a2d3a" }}>
        <div className="text-sm font-medium mb-3" style={{ color: "#94a3b8" }}>Recent nights</div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs" style={{ borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ color: "#64748b", borderBottom: "1px solid #2a2d3a" }}>
                <th className="text-left py-2 pr-4">Night</th>
                <th className="text-right py-2 pr-4">Total</th>
                <th className="text-right py-2 pr-4">Deep</th>
                <th className="text-right py-2 pr-4">REM</th>
                <th className="text-right py-2 pr-4">Core</th>
                <th className="text-right py-2 pr-3">Awake</th>
                <th className="text-right py-2 pr-3">Score</th>
                <th className="text-right py-2 pr-3">HR</th>
                <th className="text-right py-2 pr-3">Resp</th>
                <th className="text-right py-2">Battery+</th>
              </tr>
            </thead>
            <tbody>
              {[...data].reverse().slice(0, 60).map((s, i) => {
                const total = s.total_sleep_hours;
                const good = total != null && total >= 7;
                // Find matching wellness row
                const w = wellnessData.find(r => r.date === s.night);
                return (
                  <tr key={i} style={{ borderBottom: "1px solid #1e2130", color: "#e2e8f0" }}>
                    <td className="py-1.5 pr-4">{s.night}</td>
                    <td className="py-1.5 pr-4 text-right font-medium" style={{ color: good ? "#10b981" : total != null && total < 6 ? "#ef4444" : "#e2e8f0" }}>
                      {total?.toFixed(1) ?? "—"}h
                    </td>
                    <td className="py-1.5 pr-4 text-right">{s.Deep?.toFixed(1) ?? "—"}h</td>
                    <td className="py-1.5 pr-4 text-right">{s.REM?.toFixed(1) ?? "—"}h</td>
                    <td className="py-1.5 pr-4 text-right">{s.Core?.toFixed(1) ?? "—"}h</td>
                    <td className="py-1.5 pr-3 text-right">{s.Awake?.toFixed(1) ?? "—"}h</td>
                    <td className="py-1.5 pr-3 text-right" style={{ color: w?.GarminSleepScore != null ? "#8b5cf6" : "#374151" }}>
                      {w?.GarminSleepScore ?? "—"}
                    </td>
                    <td className="py-1.5 pr-3 text-right">{w?.GarminSleepHR != null ? `${w.GarminSleepHR}` : "—"}</td>
                    <td className="py-1.5 pr-3 text-right">{w?.GarminSleepRespiration != null ? `${w.GarminSleepRespiration}` : "—"}</td>
                    <td className="py-1.5 text-right" style={{ color: (w?.GarminBodyBatteryDuringSleep ?? w?.GarminBodyBatteryChange) != null ? bbColor(w?.GarminBodyBatteryDuringSleep ?? w?.GarminBodyBatteryChange) : "#374151" }}>
                      {(w?.GarminBodyBatteryDuringSleep ?? w?.GarminBodyBatteryChange) != null ? `+${w?.GarminBodyBatteryDuringSleep ?? w?.GarminBodyBatteryChange}` : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
