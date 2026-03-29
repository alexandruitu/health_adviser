import { useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from "recharts";

interface Series {
  key: string;
  color: string;
  name?: string;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type ChartRow = Record<string, any>;

interface RefLine {
  y: number;
  label?: string;
  color?: string;
}

interface ChartPanelProps {
  title: string;
  data: ChartRow[];
  dateKey?: string;
  series: Series[];
  unit?: string;
  height?: number;
  loading?: boolean;
  chartType?: "line" | "area" | "bar";
  syncId?: string;
  /** Force the X-axis to span this range even if data starts/ends later */
  start?: string;
  end?: string;
  /** Override automatic Y-axis domain */
  yDomain?: [number, number];
  /** Extra horizontal reference lines (in addition to auto avg lines) */
  referenceLines?: RefLine[];
}

const CHART_STYLE = {
  background: "rgba(20, 23, 35, 0.55)",
  backdropFilter: "blur(16px)",
  WebkitBackdropFilter: "blur(16px)",
  border: "1px solid rgba(255,255,255,0.07)",
  borderRadius: "0.75rem",
  padding: "1.25rem",
};

function formatDate(d: string, showYear: boolean = false): string {
  if (!d) return "";
  const s = String(d);
  if (s.length < 10) return s;
  // Format: "MM-DD" or "MM-DD\nYY"
  const month = s.slice(5, 7);
  const day = s.slice(8, 10);
  const year = s.slice(2, 4); // "2026" → "26"
  return showYear ? `${month}-${day}\n${year}` : `${month}-${day}`;
}

// Custom tooltip: shows "No data" for avg-filled gaps
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function CustomTooltip({ active, payload, label, unit, series }: any) {
  if (!active || !payload || payload.length === 0) return null;

  const row = payload[0]?.payload ?? {};
  const isMulti = series.length > 1;

  return (
    <div style={{
      backgroundColor: "#1a1d27",
      border: "1px solid #2a2d3a",
      borderRadius: "0.5rem",
      padding: "8px 10px",
      fontSize: "0.8rem",
      color: "#e2e8f0",
    }}>
      <div style={{ color: "#94a3b8", marginBottom: 4 }}>{label}</div>
      {payload.map((entry: any) => {
        const seriesKey = entry.dataKey as string;
        const noData = row[`_noData_${seriesKey}`] === true;
        const seriesDef = series.find((s: Series) => s.key === seriesKey);
        const color = seriesDef?.color ?? entry.color;
        const displayName = seriesDef?.name ?? seriesKey;
        return (
          <div key={seriesKey} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", backgroundColor: color, flexShrink: 0 }} />
            {isMulti && <span style={{ color: "#94a3b8", marginRight: 2 }}>{displayName}:</span>}
            {noData
              ? <span style={{ color: "#64748b", fontStyle: "italic" }}>No data</span>
              : <span style={{ fontWeight: 500 }}>{Number(entry.value).toFixed(1)}{unit ? `\u2009${unit}` : ""}</span>
            }
          </div>
        );
      })}
    </div>
  );
}

export function ChartPanel({
  title,
  data,
  dateKey = "date",
  series,
  unit,
  height = 280,
  loading = false,
  chartType = "line",
  syncId,
  start,
  end,
  yDomain: yDomainProp,
  referenceLines: extraRefLines = [],
}: ChartPanelProps) {
  const [hiddenKeys, setHiddenKeys] = useState<Set<string>>(new Set());

  const toggleSeries = (key: string) =>
    setHiddenKeys((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });

  // Check if data spans multiple years
  const years = new Set<string>();
  data.forEach((row) => {
    const d = String(row[dateKey]);
    if (d.length >= 4) years.add(d.slice(0, 4));
  });
  const multiYear = years.size > 1;

  // Build clean numeric rows (real data only)
  const allClean: ChartRow[] = data.map((row) => {
    const out: ChartRow = { [dateKey]: formatDate(String(row[dateKey]), multiYear) };
    series.forEach(({ key }) => {
      const v = row[key];
      out[key] = v != null && !isNaN(Number(v)) ? Number(v) : null;
    });
    return out;
  });

  // Keep only rows with at least one real value
  const withData = allClean.filter((row) =>
    series.some(({ key }) => row[key] != null)
  );

  const hasData = withData.length > 0;

  // Compute per-series averages from real data only
  const avgs: Record<string, number | null> = {};
  let yMin = Infinity;
  let yMax = -Infinity;
  series.forEach(({ key }) => {
    const vals = withData.flatMap((r) => r[key] != null ? [r[key] as number] : []);
    if (vals.length > 0) {
      avgs[key] = vals.reduce((a, b) => a + b, 0) / vals.length;
      yMin = Math.min(yMin, ...vals);
      yMax = Math.max(yMax, ...vals);
    } else {
      avgs[key] = null;
    }
  });

  // Inject empty boundary rows so the X-axis spans start→end
  const emptyRow = (dateStr: string): ChartRow => {
    const r: ChartRow = { [dateKey]: formatDate(dateStr, multiYear) };
    series.forEach(({ key }) => { r[key] = null; });
    return r;
  };
  const withBoundaries = [...withData];
  if (start) {
    const s = formatDate(start);
    if (withBoundaries.length === 0 || withBoundaries[0][dateKey] > s)
      withBoundaries.unshift(emptyRow(start));
  }
  if (end) {
    const e = formatDate(end);
    if (withBoundaries.length === 0 || withBoundaries[withBoundaries.length - 1][dateKey] < e)
      withBoundaries.push(emptyRow(end));
  }

  // Fill nulls with the series average and tag them as _noData_
  const filledData: ChartRow[] = withBoundaries.map((row) => {
    const out = { ...row };
    series.forEach(({ key }) => {
      if (out[key] == null && avgs[key] != null) {
        out[key] = avgs[key];
        out[`_noData_${key}`] = true;
      }
    });
    return out;
  });

  // Y domain padded from real data range (or overridden by prop)
  const pad = yMin === yMax ? 1 : (yMax - yMin) * 0.04;
  const yDomainAuto: [number, number] = hasData
    ? [Math.floor(yMin - pad), Math.ceil(yMax + pad)]
    : [0, 100];
  const yDomain = yDomainProp ?? yDomainAuto;

  const rightMargin = series.length === 1 ? 80 : 90;

  // Average reference lines for every series
  const avgLines = series
    .filter(({ key }) => avgs[key] != null)
    .map(({ key, color, name }) => {
      const avg = avgs[key]!;
      return (
        <ReferenceLine
          key={`avg_${key}`}
          y={avg}
          stroke={color}
          strokeDasharray="5 3"
          strokeWidth={1}
          strokeOpacity={0.6}
          label={{
            value: `avg ${avg.toFixed(1)}${unit ? "\u2009" + unit : ""}`,
            position: "right" as const,
            fill: color,
            fontSize: 10,
            opacity: 0.85,
            dx: 4,
          }}
          name={`avg ${name ?? key}`}
        />
      );
    });

  // Extra static reference lines (e.g. readiness bands)
  const extraLines = extraRefLines.map((rl, i) => (
    <ReferenceLine
      key={`ref_${i}`}
      y={rl.y}
      stroke={rl.color ?? "#ffffff33"}
      strokeDasharray="4 4"
      strokeWidth={1}
      label={rl.label ? {
        value: rl.label,
        position: "insideTopRight" as const,
        fill: rl.color ?? "#94a3b8",
        fontSize: 9,
        opacity: 0.7,
        dx: -4,
      } : undefined}
    />
  ));

  const renderChart = () => {
    const common = {
      data: filledData,
      syncId,
      margin: { top: 4, right: rightMargin, left: -16, bottom: multiYear ? 24 : 0 },
    };
    const axisProps = {
      stroke: "#2a2d3a",
      tick: { fill: "#64748b", fontSize: 11 },
    };
    const grid = <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3a" />;
    const xAxis = (
      <XAxis dataKey={dateKey} {...axisProps} interval="preserveStartEnd" minTickGap={40} />
    );
    const yAxis = (
      <YAxis
        {...axisProps}
        tickFormatter={(v) => `${v}${unit ? " " + unit : ""}`}
        width={60}
        domain={yDomain}
      />
    );
    const tooltip = (
      <Tooltip
        content={<CustomTooltip unit={unit} series={series} />}
        cursor={{ stroke: "#4a5568", strokeWidth: 1 }}
      />
    );
    if (chartType === "area") {
      return (
        <AreaChart {...common}>
          {grid}{xAxis}{yAxis}{tooltip}
          {series.map((s) => (
            <Area
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.name ?? s.key}
              stroke={s.color}
              strokeWidth={1.5}
              fill={s.color}
              fillOpacity={0.07}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 0 }}
              connectNulls
              hide={hiddenKeys.has(s.key)}
            />
          ))}
          {avgLines}{extraLines}
        </AreaChart>
      );
    }
    if (chartType === "bar") {
      return (
        <BarChart {...common}>
          {grid}{xAxis}{yAxis}{tooltip}
          {series.map((s) => (
            <Bar key={s.key} dataKey={s.key} name={s.name ?? s.key} fill={s.color} radius={[2, 2, 0, 0]} hide={hiddenKeys.has(s.key)} />
          ))}
          {avgLines}{extraLines}
        </BarChart>
      );
    }
    // line
    return (
      <LineChart {...common}>
        {grid}{xAxis}{yAxis}{tooltip}
        {series.map((s) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.name ?? s.key}
            stroke={s.color}
            strokeWidth={1.5}
            strokeOpacity={0.75}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 0 }}
            connectNulls
            hide={hiddenKeys.has(s.key)}
          />
        ))}
        {avgLines}{extraLines}
      </LineChart>
    );
  };

  const customLegend = series.length > 1 && (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", justifyContent: "center", marginTop: "0.6rem" }}>
      {series.map((s) => {
        const hidden = hiddenKeys.has(s.key);
        return (
          <button
            key={s.key}
            onClick={() => toggleSeries(s.key)}
            style={{
              display: "flex", alignItems: "center", gap: "0.3rem",
              padding: "0.2rem 0.6rem",
              borderRadius: "1rem",
              border: `1px solid ${hidden ? "#2a2d3a" : s.color + "55"}`,
              background: hidden ? "transparent" : s.color + "15",
              cursor: "pointer",
              opacity: hidden ? 0.4 : 1,
              transition: "all 0.15s",
            }}
          >
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: s.color, flexShrink: 0, display: "inline-block" }} />
            <span style={{ fontSize: "0.72rem", color: hidden ? "#475569" : "#94a3b8", fontWeight: 500 }}>
              {s.name ?? s.key}
            </span>
          </button>
        );
      })}
    </div>
  );

  return (
    <div style={CHART_STYLE}>
      <div className="text-sm font-medium mb-3" style={{ color: "#94a3b8" }}>{title}</div>
      {loading ? (
        <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center", color: "#64748b", fontSize: "0.85rem" }}>
          Loading…
        </div>
      ) : !hasData ? (
        <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center", color: "#64748b", fontSize: "0.85rem" }}>
          No data in selected range
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          {renderChart()}
        </ResponsiveContainer>
      )}
      {!loading && hasData && customLegend}
    </div>
  );
}
