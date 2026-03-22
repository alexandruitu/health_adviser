import { useState } from "react";

interface CardProps {
  title: string;
  value: string | number | null;
  unit?: string;
  subtitle?: string;
  color?: string;
  icon?: React.ReactNode;
}

export function Card({ title, value, unit, subtitle, color = "#6366f1", icon }: CardProps) {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        backgroundColor: "#1a1d27",
        border: "1px solid #2a2d3a",
        borderRadius: "0.75rem",
        padding: "1rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.25rem",
        position: "relative",
        overflow: "hidden",
        transition: "box-shadow 0.25s ease, transform 0.2s ease",
        boxShadow: hovered ? `0 0 0 1px ${color}55, 0 4px 24px ${color}33` : "none",
        transform: hovered ? "translateY(-2px)" : "translateY(0)",
        cursor: "default",
      }}
    >
      {/* Top accent bar */}
      <div
        style={{
          position: "absolute",
          top: 0, left: 0, right: 0,
          height: "3px",
          background: `linear-gradient(90deg, ${color}cc, ${color}44)`,
          borderRadius: "0.75rem 0.75rem 0 0",
        }}
      />

      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.875rem", color: "#64748b" }}>
        {icon && <span style={{ color }}>{icon}</span>}
        {title}
      </div>

      <div style={{ display: "flex", alignItems: "baseline", gap: "0.25rem", marginTop: "0.25rem" }}>
        <span style={{ fontSize: "1.5rem", fontWeight: 700, color: value == null ? "#64748b" : "#e2e8f0" }}>
          {value == null ? "—" : value}
        </span>
        {unit && value != null && (
          <span style={{ fontSize: "0.875rem", color: "#64748b" }}>{unit}</span>
        )}
      </div>

      {subtitle && (
        <div style={{ fontSize: "0.75rem", color: "#64748b" }}>{subtitle}</div>
      )}
    </div>
  );
}
