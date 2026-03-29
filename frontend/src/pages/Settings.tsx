import { useState } from "react";
import { StravaSync } from "../components/StravaSync";
import { HealthSync } from "../components/HealthSync";
import { GarminSync } from "../components/GarminSync";
import { Explorer } from "./Explorer";

const SECTION_LABEL: React.CSSProperties = {
  fontSize: "0.7rem", fontWeight: 700, color: "#475569",
  textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "0.5rem",
};

export function Settings() {
  const [showExplorer, setShowExplorer] = useState(false);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>

      <div>
        <h1 style={{ fontSize: "1.25rem", fontWeight: 700, color: "#e2e8f0", margin: 0 }}>Settings</h1>
        <p style={{ fontSize: "0.8rem", color: "#64748b", margin: "4px 0 0" }}>
          Manage data sources and sync connections
        </p>
      </div>

      <div>
        <div style={SECTION_LABEL}>Data Sources</div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <StravaSync />
          <GarminSync />
          <HealthSync />
        </div>
      </div>

      <div>
        <div style={SECTION_LABEL}>Advanced</div>
        <div style={{ backgroundColor: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: "0.75rem", overflow: "hidden" }}>
          <button
            onClick={() => setShowExplorer(v => !v)}
            style={{
              width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "0.75rem 1rem", background: "none", border: "none",
              color: "#e2e8f0", fontSize: "0.875rem", fontWeight: 500, cursor: "pointer",
            }}
          >
            <span>Metric Explorer</span>
            <span style={{ color: "#64748b", fontSize: "0.75rem" }}>{showExplorer ? "▲ hide" : "▼ show"}</span>
          </button>
          {showExplorer && (
            <div style={{ borderTop: "1px solid #2a2d3a", padding: "1.25rem" }}>
              <Explorer />
            </div>
          )}
        </div>
      </div>

    </div>
  );
}
