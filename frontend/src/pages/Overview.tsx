import { useState, useMemo } from "react";
import { Heart, Footprints, Flame, Moon, Weight, Activity, Wind, Dumbbell } from "lucide-react";
import { Card } from "../components/Card";
import { ChartPanel } from "../components/ChartPanel";
import { useApi } from "../hooks/useApi";
import { api } from "../api";

const DATA_YEARS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026];
const CURRENT_YEAR = new Date().getFullYear();

const PILL_ACTIVE   = { backgroundColor: "#6366f1", color: "#fff", border: "1px solid #6366f1" };
const PILL_INACTIVE = { backgroundColor: "transparent", color: "#64748b", border: "1px solid #2a2d3a" };

// ── helpers ──────────────────────────────────────────────────────────────────
function avg(arr: (number | undefined | null)[]): number | null {
  const vals = arr.filter((v): v is number => v != null && !isNaN(v));
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
}
function latest(arr: (number | undefined | null)[]): number | null {
  for (let i = arr.length - 1; i >= 0; i--) {
    const v = arr[i];
    if (v != null && !isNaN(v)) return v;
  }
  return null;
}
function fmt1(v: number | null): string | null {
  return v != null ? v.toFixed(1) : null;
}
function fmtInt(v: number | null): string | null {
  return v != null ? Math.round(v).toLocaleString() : null;
}

export function Overview() {
  const [year, setYear] = useState(CURRENT_YEAR);

  const start = `${year}-01-01`;
  const end   = `${year}-12-31`;

  const { data: daily, loading: dailyLoading } = useApi(
    () => api.daily({
      start, end,
      metrics: "StepCount,ActiveEnergyBurned,RestingHeartRate,HeartRateVariabilitySDNN,HRV_Apple,HRV_Garmin,BodyMass,BodyFatPercentage,VO2Max,VO2MaxCycling",
    }),
    [start, end]
  );
  const { data: sleep } = useApi(() => api.sleep({ start, end }), [start, end]);
  const { data: workouts } = useApi(() => api.workouts({ start, end }), [start, end]);

  const dailyData = daily ?? [];
  const sleepData = sleep ?? [];

  // ── compute card values from year-filtered data ───────────────────────────
  const stats = useMemo(() => {
    const steps   = dailyData.map(r => r.StepCount);
    const energy  = dailyData.map(r => r.ActiveEnergyBurned);
    const rhr     = dailyData.map(r => r.RestingHeartRate);
    const hrv        = dailyData.map(r => r.HeartRateVariabilitySDNN);
    const hrvApple   = dailyData.map(r => (r as Record<string, unknown>).HRV_Apple as number | undefined);
    const hrvGarmin  = dailyData.map(r => (r as Record<string, unknown>).HRV_Garmin as number | undefined);
    const weight  = dailyData.map(r => r.BodyMass);
    const fat     = dailyData.map(r => r.BodyFatPercentage);
    const vo2     = dailyData.map(r => r.VO2Max);
    const vo2cyc  = dailyData.map(r => (r as Record<string, unknown>).VO2MaxCycling as number | undefined);
    const slp     = sleepData.map(r => r.total_sleep_hours);
    const deep    = sleepData.map(r => (r as Record<string, unknown>).Deep as number | undefined);
    const rem     = sleepData.map(r => (r as Record<string, unknown>).REM as number | undefined);
    const core    = sleepData.map(r => (r as Record<string, unknown>).Core as number | undefined);
    return {
      avgSteps:    fmtInt(avg(steps)),
      avgEnergy:   fmt1(avg(energy)),
      avgRHR:      fmt1(avg(rhr)),
      avgHRV:      fmt1(avg(hrv)),
      avgHRVApple: fmt1(avg(hrvApple)),
      avgHRVGarmin:fmt1(avg(hrvGarmin)),
      avgSleep:    fmt1(avg(slp)),
      avgDeep:     fmt1(avg(deep)),
      avgREM:      fmt1(avg(rem)),
      avgCore:     fmt1(avg(core)),
      latestWeight:fmt1(latest(weight)),
      avgWeight:   fmt1(avg(weight)),
      latestFat:   fmt1(latest(fat)),
      avgFat:      fmt1(avg(fat)),
      latestVO2:   fmt1(latest(vo2)),
      latestVO2Cyc:fmt1(latest(vo2cyc)),
      sessions:    workouts?.length?.toString() ?? null,
    };
  }, [dailyData, sleepData, workouts]);

  return (
    <div className="flex flex-col gap-6">

      {/* Header + year toggles */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.75rem" }}>
        <h1 className="text-xl font-semibold" style={{ color: "#e2e8f0" }}>Overview</h1>
        <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
          {DATA_YEARS.map(y => (
            <button
              key={y}
              onClick={() => setYear(y)}
              style={{
                ...(y === year ? PILL_ACTIVE : PILL_INACTIVE),
                padding: "0.2rem 0.65rem",
                borderRadius: "0.4rem",
                fontSize: "0.72rem",
                fontWeight: y === year ? 600 : 400,
                cursor: "pointer",
                transition: "all 0.15s",
              }}
            >
              {y}
            </button>
          ))}
        </div>
      </div>

      {/* Summary cards — year-filtered averages */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card
          title="Daily steps"
          value={stats.avgSteps}
          subtitle={`avg · ${year}`}
          icon={<Footprints size={14} />}
          color="#6366f1"
        />
        <Card
          title="Resting HR"
          value={stats.avgRHR}
          unit="bpm"
          subtitle={`avg · ${year}`}
          icon={<Heart size={14} />}
          color="#f43f5e"
        />
        <Card
          title="HRV · Apple Health"
          value={stats.avgHRVApple}
          unit="ms"
          subtitle={`avg · ${year}`}
          icon={<Activity size={14} />}
          color="#10b981"
        />
        <Card
          title="HRV · Garmin"
          value={stats.avgHRVGarmin}
          unit="ms"
          subtitle={`avg · ${year}`}
          icon={<Activity size={14} />}
          color="#06b6d4"
        />
        <Card
          title="Sleep"
          value={stats.avgSleep}
          unit="hrs"
          subtitle={`avg · ${year}`}
          icon={<Moon size={14} />}
          color="#8b5cf6"
        />
        <Card
          title="Deep sleep"
          value={stats.avgDeep}
          unit="hrs"
          subtitle={`avg · ${year}`}
          icon={<Moon size={14} />}
          color="#4f46e5"
        />
        <Card
          title="REM sleep"
          value={stats.avgREM}
          unit="hrs"
          subtitle={`avg · ${year}`}
          icon={<Moon size={14} />}
          color="#7c3aed"
        />
        <Card
          title="Core sleep"
          value={stats.avgCore}
          unit="hrs"
          subtitle={`avg · ${year}`}
          icon={<Moon size={14} />}
          color="#a855f7"
        />
        <Card
          title="Weight"
          value={stats.avgWeight}
          unit="kg"
          subtitle={`avg · ${year}  ·  latest ${stats.latestWeight ?? "—"} kg`}
          icon={<Weight size={14} />}
          color="#f59e0b"
        />
        <Card
          title="Body fat"
          value={stats.avgFat}
          unit="%"
          subtitle={`avg · ${year}  ·  latest ${stats.latestFat ?? "—"}%`}
          icon={<Weight size={14} />}
          color="#f97316"
        />
        <Card
          title="VO₂ Max · Run"
          value={stats.latestVO2}
          unit="mL/kg/min"
          subtitle={`latest · ${year} · Garmin`}
          icon={<Wind size={14} />}
          color="#06b6d4"
        />
        <Card
          title="VO₂ Max · Cycling"
          value={stats.latestVO2Cyc}
          unit="mL/kg/min"
          subtitle={`latest · ${year} · Garmin`}
          icon={<Wind size={14} />}
          color="#0ea5e9"
        />
        <Card
          title="Workouts"
          value={stats.sessions}
          subtitle={`sessions · ${year}`}
          icon={<Dumbbell size={14} />}
          color="#84cc16"
        />
        <Card
          title="Active energy"
          value={stats.avgEnergy}
          unit="kcal"
          subtitle={`avg · ${year}`}
          icon={<Flame size={14} />}
          color="#ef4444"
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartPanel
          title={`Daily steps (${year})`}
          data={dailyData}
          series={[{ key: "StepCount", color: "#6366f1" }]}
          unit="steps"
          chartType="bar"
          loading={dailyLoading}
          syncId="overview"
        />
        <ChartPanel
          title={`Active energy (${year})`}
          data={dailyData}
          series={[{ key: "ActiveEnergyBurned", color: "#ef4444" }]}
          unit="kcal"
          chartType="area"
          loading={dailyLoading}
          syncId="overview"
        />
        <ChartPanel
          title={`Resting heart rate (${year})`}
          data={dailyData}
          series={[{ key: "RestingHeartRate", color: "#f43f5e" }]}
          unit="bpm"
          chartType="line"
          loading={dailyLoading}
        />
        <ChartPanel
          title={`HRV — SDNN (${year})`}
          data={dailyData}
          series={[
            { key: "HRV_Apple",  color: "#10b981", name: "Apple Watch" },
            { key: "HRV_Garmin", color: "#06b6d4", name: "Garmin" },
          ]}
          unit="ms"
          chartType="area"
          loading={dailyLoading}
        />
        <ChartPanel
          title={`Sleep duration (${year})`}
          data={sleepData}
          dateKey="night"
          series={[{ key: "total_sleep_hours", color: "#8b5cf6" }]}
          unit="hrs"
          chartType="bar"
        />
        <ChartPanel
          title={`Body weight (${year})`}
          data={dailyData}
          series={[{ key: "BodyMass", color: "#f59e0b" }]}
          unit="kg"
          chartType="line"
          loading={dailyLoading}
        />
      </div>
    </div>
  );
}
