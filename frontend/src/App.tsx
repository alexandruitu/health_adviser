import { useState } from "react";
import { LayoutDashboard, Heart, Activity, Moon, Weight, Droplets, Search, List, FlaskConical, Settings as SettingsIcon } from "lucide-react";
import { Overview } from "./pages/Overview";
import { Heart as HeartPage } from "./pages/Heart";
import { Activity as ActivityPage } from "./pages/Activity";
import { Activities } from "./pages/Activities";
import { Sleep } from "./pages/Sleep";
import { Body } from "./pages/Body";
import { Glucose } from "./pages/Glucose";
import { Explorer } from "./pages/Explorer";
import { Biomarkers } from "./pages/Biomarkers";
import { Settings } from "./pages/Settings";
import { IngestToast } from "./components/IngestToast";

const PAGES = [
  { id: "overview",    label: "Overview",    icon: LayoutDashboard, component: Overview },
  { id: "heart",       label: "Heart",       icon: Heart,           component: HeartPage },
  { id: "activity",    label: "Activity",    icon: Activity,        component: ActivityPage },
  { id: "activities",  label: "Activities",  icon: List,            component: Activities },
  { id: "sleep",       label: "Sleep",       icon: Moon,            component: Sleep },
  { id: "body",        label: "Body",        icon: Weight,          component: Body },
  { id: "glucose",     label: "Glucose",     icon: Droplets,        component: Glucose },
  { id: "biomarkers",  label: "Biomarkers",  icon: FlaskConical,    component: Biomarkers },
  { id: "explorer",    label: "Explorer",    icon: Search,          component: Explorer },
];

const BOTTOM_PAGES = [
  { id: "settings", label: "Settings", icon: SettingsIcon, component: Settings },
];

const ALL_PAGES = [...PAGES, ...BOTTOM_PAGES];

export default function App() {
  const [page, setPage] = useState("overview");
  const CurrentPage = ALL_PAGES.find((p) => p.id === page)!.component;

  return (
    <div className="flex min-h-screen" style={{ backgroundColor: "#0f1117" }}>
      {/* Sidebar */}
      <nav
        className="w-52 flex-shrink-0 flex flex-col py-6 px-3"
        style={{ backgroundColor: "#13151f", borderRight: "1px solid #2a2d3a", position: "sticky", top: 0, height: "100vh" }}
      >
        <div className="px-3 mb-5">
          <div className="text-base font-bold" style={{ color: "#e2e8f0" }}>Health</div>
          <div className="text-xs" style={{ color: "#64748b" }}>Dashboard</div>
        </div>

        {/* Main nav items */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1px", flex: 1 }}>
          {PAGES.map(({ id, label, icon: Icon }) => {
            const active = page === id;
            return (
              <button
                key={id}
                onClick={() => setPage(id)}
                className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium text-left transition-colors w-full"
                style={{
                  backgroundColor: active ? "#6366f1" : "transparent",
                  color: active ? "#fff" : "#94a3b8",
                  cursor: "pointer",
                  border: "none",
                }}
              >
                <Icon size={15} />
                {label}
              </button>
            );
          })}
        </div>

        {/* Bottom: Settings */}
        <div style={{ borderTop: "1px solid #2a2d3a", paddingTop: "0.5rem", marginTop: "0.5rem" }}>
          {BOTTOM_PAGES.map(({ id, label, icon: Icon }) => {
            const active = page === id;
            return (
              <button
                key={id}
                onClick={() => setPage(id)}
                className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium text-left transition-colors w-full"
                style={{
                  backgroundColor: active ? "#6366f1" : "transparent",
                  color: active ? "#fff" : "#94a3b8",
                  cursor: "pointer",
                  border: "none",
                }}
              >
                <Icon size={15} />
                {label}
              </button>
            );
          })}
        </div>
      </nav>

      {/* Main content */}
      <main className="flex-1 p-6 overflow-auto">
        <div className="max-w-5xl mx-auto">
          <CurrentPage />
        </div>
      </main>

      {/* Global Apple Health sync toast — polls every 8s, fires when new data arrives */}
      <IngestToast />
    </div>
  );
}
