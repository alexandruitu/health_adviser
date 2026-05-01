import { useState, useRef, useCallback, useEffect } from "react";
import { LayoutDashboard, Heart, Moon, Weight, FlaskConical, List, Settings as SettingsIcon, Dumbbell, GripVertical, BrainCircuit, LogOut } from "lucide-react";
import { AdvisorModal } from "./components/AdvisorModal";
import { Overview }            from "./pages/Overview";
import { Heart as HeartPage }  from "./pages/Heart";
import { Activity as TrainingPage } from "./pages/Activity";
import { Activities }          from "./pages/Activities";
import { Sleep }               from "./pages/Sleep";
import { Body }                from "./pages/Body";
import { Labs }                from "./pages/Labs";
import { Settings }            from "./pages/Settings";
import { IngestToast }         from "./components/IngestToast";
import { LoginPage }           from "./pages/LoginPage";
import { getToken, clearToken } from "./api";

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

const SIDEBAR_MIN = 160;
const SIDEBAR_MAX = 320;
const SIDEBAR_DEFAULT = 208;

// ─── Auth gate ───────────────────────────────────────────────────────────────

export default function App() {
  const [token, setTokenState] = useState<string | null>(() => getToken());

  useEffect(() => {
    const handler = () => setTokenState(null);
    window.addEventListener("auth:logout", handler);
    return () => window.removeEventListener("auth:logout", handler);
  }, []);

  if (!token) {
    return <LoginPage onLogin={() => setTokenState(getToken())} />;
  }

  return <MainApp onLogout={() => { clearToken(); setTokenState(null); }} />;
}

// ─── Main app (only rendered when authenticated) ──────────────────────────────

function MainApp({ onLogout }: { onLogout: () => void }) {
  const [page, setPage] = useState("overview");
  const [advisorOpen, setAdvisorOpen] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_DEFAULT);
  const dragging = useRef(false);
  const startX = useRef(0);
  const startW = useRef(SIDEBAR_DEFAULT);

  const CurrentPage = ALL_PAGES.find((p) => p.id === page)!.component;

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    dragging.current = true;
    startX.current = e.clientX;
    startW.current = sidebarWidth;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [sidebarWidth]);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      const delta = e.clientX - startX.current;
      setSidebarWidth(Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, startW.current + delta)));
    };
    const onUp = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  const navBtn = (id: string, label: string, Icon: React.ElementType) => {
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
        {sidebarWidth > 180 ? label : null}
      </button>
    );
  };

  return (
    <div className="flex min-h-screen" style={{ backgroundColor: "#0f1117" }}>
      {/* Sidebar */}
      <nav
        className="flex-shrink-0 flex flex-col py-6 px-3"
        style={{
          width: sidebarWidth,
          background: "rgba(13,15,23,0.85)",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
          borderRight: "1px solid rgba(255,255,255,0.06)",
          position: "sticky",
          top: 0,
          height: "100vh",
          transition: dragging.current ? "none" : "width 0.15s ease",
        }}
      >
        <div className="px-3 mb-5 flex items-center gap-2.5">
          <img src="/logo.svg" alt="Health Adviser" style={{ width: 32, height: 32, borderRadius: 8, flexShrink: 0 }} />
          {sidebarWidth > 180 && (
            <div>
              <div className="text-sm font-bold" style={{ color: "#e2e8f0", lineHeight: 1.2 }}>Health Adviser</div>
              <div className="text-xs" style={{ color: "#64748b" }}>Personal analytics</div>
            </div>
          )}
        </div>

        {/* Main nav items */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1px", flex: 1 }}>
          {PAGES.map(({ id, label, icon: Icon }) => navBtn(id, label, Icon))}
        </div>

        {/* Ask the Advisor */}
        <div style={{ paddingBottom: "0.5rem" }}>
          <button
            onClick={() => setAdvisorOpen(true)}
            className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium text-left w-full transition-all"
            style={{
              background: "linear-gradient(135deg, rgba(99,102,241,0.25), rgba(139,92,246,0.25))",
              border: "1px solid rgba(99,102,241,0.35)",
              color: "#a5b4fc",
              cursor: "pointer",
            }}
          >
            <BrainCircuit size={15} />
            {sidebarWidth > 180 ? "Ask the Advisor" : null}
          </button>
        </div>

        {/* Bottom: Settings + Sign out */}
        <div style={{ borderTop: "1px solid #2a2d3a", paddingTop: "0.5rem", marginTop: "0.5rem" }}>
          {BOTTOM_PAGES.map(({ id, label, icon: Icon }) => navBtn(id, label, Icon))}
          <button
            onClick={onLogout}
            className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium text-left w-full transition-colors"
            style={{ backgroundColor: "transparent", color: "#64748b", cursor: "pointer", border: "none" }}
            onMouseEnter={e => (e.currentTarget.style.color = "#f87171")}
            onMouseLeave={e => (e.currentTarget.style.color = "#64748b")}
          >
            <LogOut size={15} />
            {sidebarWidth > 180 ? "Sign out" : null}
          </button>
        </div>

        {/* Drag handle */}
        <div
          onMouseDown={onMouseDown}
          title="Drag to resize"
          style={{
            position: "absolute",
            top: 0,
            right: -4,
            width: 8,
            height: "100%",
            cursor: "col-resize",
            zIndex: 50,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div style={{
            width: 2,
            height: 40,
            borderRadius: 2,
            background: "rgba(255,255,255,0.08)",
            transition: "background 0.2s",
          }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(99,102,241,0.6)")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.08)")}
          >
            <GripVertical size={8} style={{ color: "transparent" }} />
          </div>
        </div>
      </nav>

      {/* Main content */}
      <main className="flex-1 p-6 overflow-auto" style={{ position: "relative" }}>
        {/* Background ambient blobs */}
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
        <div key={page} className="page-enter max-w-6xl mx-auto" style={{ position: "relative", zIndex: 1 }}>
          <CurrentPage />
        </div>
      </main>

      <IngestToast />
      {advisorOpen && <AdvisorModal onClose={() => setAdvisorOpen(false)} />}
    </div>
  );
}
