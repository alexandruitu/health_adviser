import { useState, useEffect, useRef } from "react";
import { api } from "../api";

interface Toast {
  id: number;
  added: number;
  ts: number;
}

export function IngestToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const lastIngest = useRef<number | null>(null);
  const initialized = useRef(false);

  useEffect(() => {
    const check = async () => {
      try {
        const status = await api.healthStatus();
        if (!initialized.current) {
          // First load — just record the current timestamp, don't show a toast
          lastIngest.current = status.last_ingest;
          initialized.current = true;
          return;
        }
        if (
          status.last_ingest !== null &&
          status.last_ingest !== lastIngest.current
        ) {
          lastIngest.current = status.last_ingest;
          const id = Date.now();
          setToasts((prev) => [
            ...prev,
            { id, added: status.total_added, ts: status.last_ingest! },
          ]);
          // Auto-dismiss after 6 seconds
          setTimeout(() => {
            setToasts((prev) => prev.filter((t) => t.id !== id));
          }, 6000);
        }
      } catch {
        // backend unreachable — ignore
      }
    };

    check();
    const interval = setInterval(check, 8000);
    return () => clearInterval(interval);
  }, []);

  if (toasts.length === 0) return null;

  return (
    <div style={{
      position: "fixed",
      bottom: "1.5rem",
      right: "1.5rem",
      zIndex: 9999,
      display: "flex",
      flexDirection: "column",
      gap: "0.5rem",
    }}>
      {toasts.map((t) => (
        <div
          key={t.id}
          style={{
            backgroundColor: "#1a1d27",
            border: "1px solid #10b98150",
            borderLeft: "4px solid #10b981",
            borderRadius: "0.75rem",
            padding: "0.85rem 1.25rem",
            minWidth: "280px",
            boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
            animation: "slideIn 0.2s ease-out",
          }}
        >
          <span style={{ fontSize: "1.25rem" }}>🍎</span>
          <div>
            <div style={{ color: "#e2e8f0", fontWeight: 600, fontSize: "0.85rem" }}>
              Apple Health synced
            </div>
            <div style={{ color: "#64748b", fontSize: "0.75rem", marginTop: "0.1rem" }}>
              {t.added.toLocaleString()} total records · {new Date(t.ts * 1000).toLocaleTimeString("en", { hour: "2-digit", minute: "2-digit" })}
            </div>
          </div>
          <button
            onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}
            style={{
              marginLeft: "auto",
              background: "none",
              border: "none",
              color: "#64748b",
              cursor: "pointer",
              fontSize: "1rem",
              padding: "0 0.25rem",
            }}
          >
            ×
          </button>
        </div>
      ))}
      <style>{`
        @keyframes slideIn {
          from { transform: translateX(20px); opacity: 0; }
          to   { transform: translateX(0);   opacity: 1; }
        }
      `}</style>
    </div>
  );
}
