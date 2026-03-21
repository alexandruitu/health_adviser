interface CardProps {
  title: string;
  value: string | number | null;
  unit?: string;
  subtitle?: string;
  color?: string;
  icon?: React.ReactNode;
}

export function Card({ title, value, unit, subtitle, color = "#6366f1", icon }: CardProps) {
  return (
    <div className="rounded-xl p-4 flex flex-col gap-1" style={{ backgroundColor: "#1a1d27", border: "1px solid #2a2d3a" }}>
      <div className="flex items-center gap-2 text-sm" style={{ color: "#64748b" }}>
        {icon && <span style={{ color }}>{icon}</span>}
        {title}
      </div>
      <div className="flex items-baseline gap-1 mt-1">
        <span className="text-2xl font-bold" style={{ color: value == null ? "#64748b" : "#e2e8f0" }}>
          {value == null ? "—" : value}
        </span>
        {unit && value != null && (
          <span className="text-sm" style={{ color: "#64748b" }}>{unit}</span>
        )}
      </div>
      {subtitle && <div className="text-xs" style={{ color: "#64748b" }}>{subtitle}</div>}
    </div>
  );
}
