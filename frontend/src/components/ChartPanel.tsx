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
  Legend,
  ReferenceLine,
} from "recharts";

interface Series {
  key: string;
  color: string;
  name?: string;
  type?: "line" | "area" | "bar";
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type ChartRow = Record<string, any>;

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
}

const CHART_STYLE = {
  backgroundColor: "#1a1d27",
  border: "1px solid #2a2d3a",
  borderRadius: "0.75rem",
  padding: "1.25rem",
};

const TOOLTIP_STYLE = {
  backgroundColor: "#1a1d27",
  border: "1px solid #2a2d3a",
  borderRadius: "0.5rem",
  color: "#e2e8f0",
  fontSize: "0.8rem",
};

function formatDate(d: string): string {
  if (!d) return "";
  const s = String(d);
  return s.length >= 10 ? s.slice(5, 10) : s;
}

export function ChartPanel({
  title,
  data,
  dateKey = "date",
  series,
  unit,
  height = 220,
  loading = false,
  chartType = "line",
  syncId,
}: ChartPanelProps) {
  const cleanData: ChartRow[] = data.map((row) => {
    const out: ChartRow = { [dateKey]: formatDate(String(row[dateKey])) };
    series.forEach(({ key }) => {
      const v = row[key];
      out[key] = v != null && !isNaN(Number(v)) ? Number(v) : null;
    });
    return out;
  });

  // Compute mean for each series
  const avgs: Record<string, number | null> = {};
  series.forEach(({ key }) => {
    const vals = cleanData.map((r) => r[key]).filter((v): v is number => v != null);
    avgs[key] = vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  });

  const isSingle = series.length === 1;

  // ReferenceLine elements for each series
  const avgLines = series
    .filter(({ key }) => avgs[key] != null)
    .map(({ key, color, name }) => {
      const avg = avgs[key]!;
      const label = isSingle
        ? {
            value: `avg ${avg.toFixed(1)}${unit ? "\u2009" + unit : ""}`,
            position: "right" as const,
            fill: color,
            fontSize: 10,
            opacity: 0.9,
            dx: 4,
          }
        : undefined;
      return (
        <ReferenceLine
          key={`avg_${key}`}
          y={avg}
          stroke={color}
          strokeDasharray="5 3"
          strokeWidth={1.5}
          strokeOpacity={0.65}
          label={label}
          name={`avg ${name ?? key}`}
        />
      );
    });

  const renderChart = () => {
    const common = {
      data: cleanData,
      syncId,
      margin: { top: 4, right: isSingle ? 56 : 8, left: -16, bottom: 0 },
    };
    const axisProps = {
      stroke: "#2a2d3a",
      tick: { fill: "#64748b", fontSize: 11 },
    };
    const grid = <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3a" />;
    const xAxis = <XAxis dataKey={dateKey} {...axisProps} interval="preserveStartEnd" />;
    const yAxis = <YAxis {...axisProps} tickFormatter={(v) => `${v}${unit ? " " + unit : ""}`} />;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const fmtValue = (v: any): [string, string] => [v != null ? Number(v).toFixed(1) : "—", ""];
    const tooltip = <Tooltip contentStyle={TOOLTIP_STYLE} formatter={fmtValue} />;
    const legend = series.length > 1 ? <Legend wrapperStyle={{ fontSize: 11, color: "#64748b" }} /> : null;

    if (chartType === "area") {
      return (
        <AreaChart {...common}>
          {grid}{xAxis}{yAxis}{tooltip}{legend}
          {series.map((s) => (
            <Area key={s.key} type="monotone" dataKey={s.key} name={s.name ?? s.key}
              stroke={s.color} fill={s.color} fillOpacity={0.15} dot={false} connectNulls />
          ))}
          {avgLines}
        </AreaChart>
      );
    }
    if (chartType === "bar") {
      return (
        <BarChart {...common}>
          {grid}{xAxis}{yAxis}{tooltip}{legend}
          {series.map((s) => (
            <Bar key={s.key} dataKey={s.key} name={s.name ?? s.key} fill={s.color} radius={[2, 2, 0, 0]} />
          ))}
          {avgLines}
        </BarChart>
      );
    }
    return (
      <LineChart {...common}>
        {grid}{xAxis}{yAxis}{tooltip}{legend}
        {series.map((s) => (
          <Line key={s.key} type="monotone" dataKey={s.key} name={s.name ?? s.key}
            stroke={s.color} dot={false} strokeWidth={1.5} connectNulls />
        ))}
        {avgLines}
      </LineChart>
    );
  };

  return (
    <div style={CHART_STYLE}>
      <div className="text-sm font-medium mb-3" style={{ color: "#94a3b8" }}>{title}</div>
      {loading ? (
        <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center", color: "#64748b" }}>
          Loading…
        </div>
      ) : data.length === 0 ? (
        <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center", color: "#64748b" }}>
          No data
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          {renderChart()}
        </ResponsiveContainer>
      )}
    </div>
  );
}
