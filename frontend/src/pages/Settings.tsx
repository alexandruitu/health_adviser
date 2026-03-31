import { StravaSync } from "../components/StravaSync";
import { HealthSync } from "../components/HealthSync";
import { GarminSync } from "../components/GarminSync";

const SECTION_LABEL: React.CSSProperties = {
  fontSize: "0.7rem", fontWeight: 700, color: "#475569",
  textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "0.5rem",
};

export function Settings() {
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

    </div>
  );
}
