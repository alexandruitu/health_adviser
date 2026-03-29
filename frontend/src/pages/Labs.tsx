import { useState } from "react";
import { Glucose } from "./Glucose";
import { Biomarkers } from "./Biomarkers";
import { BiomarkerTrends } from "../components/BiomarkerTrends";

const TABS = [
  { id: "biomarkers", label: "Blood Tests" },
  { id: "trends",     label: "Trends" },
  { id: "glucose",    label: "Glucose (CGM)" },
];

const PILL_ACTIVE   = { backgroundColor: "#6366f1", color: "#fff", border: "1px solid #6366f1" };
const PILL_INACTIVE = { backgroundColor: "transparent", color: "#64748b", border: "1px solid #2a2d3a" };

export function Labs() {
  const [tab, setTab] = useState("biomarkers");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Header + sub-tab switcher */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.75rem" }}>
        <h1 style={{ fontSize: "1.25rem", fontWeight: 600, color: "#e2e8f0", margin: 0 }}>Labs</h1>
        <div style={{ display: "flex", gap: "0.35rem" }}>
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              style={{
                ...(t.id === tab ? PILL_ACTIVE : PILL_INACTIVE),
                padding: "0.25rem 0.85rem",
                borderRadius: "0.4rem",
                fontSize: "0.78rem",
                fontWeight: t.id === tab ? 600 : 400,
                cursor: "pointer",
                transition: "all 0.15s",
              }}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Sub-page content — strip the inner h1 by letting each component render naturally */}
      {tab === "biomarkers" && <Biomarkers embedded />}
      {tab === "trends"     && <BiomarkerTrends />}
      {tab === "glucose"    && <Glucose    embedded />}
    </div>
  );
}
