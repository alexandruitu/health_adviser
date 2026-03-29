import { useState, useEffect, useRef } from "react";

interface CardProps {
  title: string;
  value: string | number | null;
  unit?: string;
  subtitle?: string;
  color?: string;
  icon?: React.ReactNode;
}

// ── count-up hook ─────────────────────────────────────────────────────────────
// Parses any formatted string value ("29,646" / "51.8" / "57.0"),
// animates from 0 → target over `duration` ms, returns display string.
function useCountUp(value: string | number | null, duration = 700): string | null {
  const [display, setDisplay] = useState<string | null>(null);
  const rafRef  = useRef<number | null>(null);
  const prevRef = useRef<number>(0);

  useEffect(() => {
    if (value == null) { setDisplay(null); return; }

    // Parse: strip commas, cast to float
    const raw    = String(value).replace(/,/g, "");
    const target = parseFloat(raw);
    if (isNaN(target)) { setDisplay(String(value)); return; }

    // Detect decimal places from original string so we format consistently
    const dotIdx   = raw.indexOf(".");
    const decimals = dotIdx === -1 ? 0 : raw.length - dotIdx - 1;
    const useLocale = String(value).includes(","); // e.g. "29,646"

    const format = (n: number): string => {
      if (useLocale) return Math.round(n).toLocaleString();
      return n.toFixed(decimals);
    };

    const start    = performance.now();
    const from     = prevRef.current;
    prevRef.current = target;

    const tick = (now: number) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      // Ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(format(from + (target - from) * eased));
      if (progress < 1) rafRef.current = requestAnimationFrame(tick);
    };

    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(tick);

    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [value, duration]);

  return display;
}

// ── component ─────────────────────────────────────────────────────────────────
export function Card({ title, value, unit, subtitle, color = "#6366f1", icon }: CardProps) {
  const [hovered, setHovered] = useState(false);
  const animated = useCountUp(value);

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: "rgba(20, 23, 35, 0.55)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        border: `1px solid ${hovered ? color + "55" : "rgba(255,255,255,0.07)"}`,
        borderRadius: "0.75rem",
        padding: "1rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.25rem",
        position: "relative",
        overflow: "hidden",
        transition: "box-shadow 0.25s ease, transform 0.2s ease, border-color 0.25s ease",
        boxShadow: hovered ? `0 0 0 1px ${color}33, 0 8px 32px ${color}22` : "0 2px 12px rgba(0,0,0,0.3)",
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
          {value == null ? "—" : (animated ?? value)}
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
