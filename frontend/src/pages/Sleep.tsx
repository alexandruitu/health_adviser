import { useState } from "react";
import { ChartPanel } from "../components/ChartPanel";
import { DateRangePicker } from "../components/DateRangePicker";
import { useApi } from "../hooks/useApi";
import { api } from "../api";

const DEFAULT_START = `${new Date().getFullYear()}-01-01`;
const DEFAULT_END = new Date().toISOString().slice(0, 10);

export function Sleep() {
  const [start, setStart] = useState(DEFAULT_START);
  const [end, setEnd] = useState(DEFAULT_END);

  const { data: sleep, loading } = useApi(() => api.sleep({ start, end }), [start, end]);
  const data = sleep ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-semibold" style={{ color: "#e2e8f0" }}>Sleep</h1>
        <DateRangePicker start={start} end={end} onChange={(s, e) => { setStart(s); setEnd(e); }} />
      </div>

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
        />
        <ChartPanel
          title="Deep sleep"
          data={data}
          dateKey="night"
          series={[{ key: "Deep", color: "#1d4ed8" }]}
          unit="hrs"
          chartType="area"
          loading={loading}
        />
        <ChartPanel
          title="REM sleep"
          data={data}
          dateKey="night"
          series={[{ key: "REM", color: "#7c3aed" }]}
          unit="hrs"
          chartType="area"
          loading={loading}
        />
      </div>

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
                <th className="text-right py-2">Awake</th>
              </tr>
            </thead>
            <tbody>
              {[...data].reverse().slice(0, 60).map((s, i) => {
                const total = s.total_sleep_hours;
                const good = total != null && total >= 7;
                return (
                  <tr key={i} style={{ borderBottom: "1px solid #1e2130", color: "#e2e8f0" }}>
                    <td className="py-1.5 pr-4">{s.night}</td>
                    <td className="py-1.5 pr-4 text-right font-medium" style={{ color: good ? "#10b981" : total != null && total < 6 ? "#ef4444" : "#e2e8f0" }}>
                      {total?.toFixed(1) ?? "—"}h
                    </td>
                    <td className="py-1.5 pr-4 text-right">{s.Deep?.toFixed(1) ?? "—"}h</td>
                    <td className="py-1.5 pr-4 text-right">{s.REM?.toFixed(1) ?? "—"}h</td>
                    <td className="py-1.5 pr-4 text-right">{s.Core?.toFixed(1) ?? "—"}h</td>
                    <td className="py-1.5 text-right">{s.Awake?.toFixed(1) ?? "—"}h</td>
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
