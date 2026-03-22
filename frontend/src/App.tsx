import { useState } from "react";
import { LayoutDashboard, Heart, Activity, Moon, Weight, FlaskConical, List, Settings as SettingsIcon, Dumbbell } from "lucide-react";
import { Overview }            from "./pages/Overview";
import { Heart as HeartPage }  from "./pages/Heart";
import { Activity as TrainingPage } from "./pages/Activity";
import { Activities }          from "./pages/Activities";
import { Sleep }               from "./pages/Sleep";
import { Body }                from "./pages/Body";
import { Labs }                from "./pages/Labs";
import { Settings }            from "./pages/Settings";
import { IngestToast }         from "./components/IngestToast";

const PAGES = [
  { id: "overview",  label: "Overview",  icon: LayoutDashboard, component: Overview },
  { id: "heart",     label: "Heart",     icon: Heart,           component: HeartPage },
  { id: "training",  label: "Training",  icon: Dumbbell,        component: TrainingPage },
  { id: "log",       label: "Log",       icon: List,            component: Activities },
  { id: "sleep",     label: "Sleep",     icon: Moon,            component: Sleep },
  { id: "body",      label: "Body",      icon: Weight,          component: Body },
  { id: "labs",      label: "Labs",      icon: FlaskConical,    component: Labs },
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
        style={{ background: "rgba(13,15,23,0.85)", backdropFilter: "blur(20px)", WebkitBackdropFilter: "blur(20px)", borderRight: "1px solid rgba(255,255,255,0.06)", position: "sticky", top: 0, height: "100vh" }}
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
      <main className="flex-1 p-6 overflow-auto" style={{ position: "relative" }}>
        {/* Background ambient blobs — animated aurora behind glass cards */}
        <div aria-hidden style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0, overflow: "hidden" }}>
          <div className="blob-1" style={{
            position: "absolute", top: "-10%", left: "15%",
            width: "55vw", height: "55vw", borderRadius: "50%",
            background: "radial-gradient(circle, #6366f12e 0%, transparent 70%)",
          }} />
          <div className="blob-2" style={{
            position: "absolute", top: "35%", right: "-5%",
            width: "40vw", height: "40vw", borderRadius: "50%",
            background: "radial-gradient(circle, #06b6d425 0%, transparent 70%)",
          }} />
          <div className="blob-3" style={{
            position: "absolute", bottom: "0%", left: "5%",
            width: "45vw", height: "35vw", borderRadius: "50%",
            background: "radial-gradient(circle, #8b5cf625 0%, transparent 70%)",
          }} />
        </div>
        <div className="max-w-5xl mx-auto" style={{ position: "relative", zIndex: 1 }}>
          <CurrentPage />
        </div>
      </main>

      <IngestToast />
    </div>
  );
}
