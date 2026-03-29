import { useState, useEffect, useRef } from "react";
import { api } from "../api";
import type { StravaStatus, StravaSyncResult } from "../api";

const STRAVA_ORANGE = "#fc4c02";

function fmtLastSync(ts: number | null): string {
  if (!ts) return "Never";
  return new Date(ts * 1000).toLocaleString("en", {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export function StravaSync() {
  const [status, setStatus]   = useState<StravaStatus | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [result, setResult]   = useState<StravaSyncResult | null>(null);
  const [error, setError]     = useState<string | null>(null);
  const pollRef               = useRef<ReturnType<typeof setInterval> | null>(null);

  function refreshStatus() {
    api.stravaStatus().then(setStatus).catch(() => setStatus(null));
  }
  useEffect(() => { refreshStatus(); }, []);

  function stopPolling() {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }

  function startPolling() {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.stravaSyncStatus();
        if (s.status === "done") {
          setResult({ added: s.added, skipped: s.skipped });
          setSyncing(false);
          stopPolling();
          refreshStatus();
        } else if (s.status === "error") {
          setError(s.error ?? "Sync failed");
          setSyncing(false);
          stopPolling();
        }
      } catch {
        // keep polling
      }
    }, 3000);
  }

  // Cleanup on unmount
  useEffect(() => () => stopPolling(), []);

  function handleConnect() {
    window.open("/api/strava/auth", "_blank");
    setTimeout(refreshStatus, 3000);
  }

  async function handleSync(force = false) {
    setSyncing(true);
    setResult(null);
    setError(null);
    try {
      await api.stravaSync(force);
      startPolling();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Sync failed");
      setSyncing(false);
    }
  }

  const connected = status?.connected ?? false;

  return (
    <div style={{
      backgroundColor: "#1a1d27",
      border: "1px solid #2a2d3a",
      borderRadius: "0.75rem",
      padding: "0.75rem 1.25rem",
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      flexWrap: "wrap",
      gap: "0.75rem",
    }}>
      {/* Left: identity + status */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
        <span style={{ color: STRAVA_ORANGE, fontWeight: 700, fontSize: "0.9rem", letterSpacing: "0.02em" }}>
          Strava
        </span>
        <span style={{
          fontSize: "0.65rem", fontWeight: 600, padding: "0.15rem 0.5rem",
          borderRadius: "0.25rem",
          backgroundColor: connected ? "#10b98118" : "#64748b18",
          color: connected ? "#10b981" : "#64748b",
          border: `1px solid ${connected ? "#10b98130" : "#64748b30"}`,
        }}>
          {connected ? "Connected" : "Not connected"}
        </span>
        {connected && (
          <span style={{ color: "#64748b", fontSize: "0.75rem" }}>
            {status?.athlete_name && <>{status.athlete_name} · </>}
            Last sync: {fmtLastSync(status?.last_sync ?? null)}
          </span>
        )}
      </div>

      {/* Right: action */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
        {result && (
          <span style={{ fontSize: "0.75rem", color: "#10b981" }}>
            ✓ {result.added} added{result.skipped > 0 ? `, ${result.skipped} skipped` : ""}
          </span>
        )}
        {error && (
          <span style={{ fontSize: "0.75rem", color: "#ef4444" }}>{error}</span>
        )}
        {syncing && (
          <span style={{ fontSize: "0.75rem", color: "#64748b" }}>Fetching activities…</span>
        )}
        {!connected ? (
          <button onClick={handleConnect} style={{
            backgroundColor: STRAVA_ORANGE, color: "#fff", border: "none",
            borderRadius: "0.375rem", padding: "0.4rem 0.9rem",
            fontSize: "0.8rem", fontWeight: 600, cursor: "pointer",
          }}>
            Connect Strava
          </button>
        ) : (
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button onClick={() => handleSync(false)} disabled={syncing} style={{
              backgroundColor: syncing ? "#2a2d3a" : "#6366f1",
              color: syncing ? "#64748b" : "#fff",
              border: `1px solid ${syncing ? "#3a3d4a" : "#6366f1"}`,
              borderRadius: "0.375rem", padding: "0.4rem 0.9rem",
              fontSize: "0.8rem", fontWeight: 600,
              cursor: syncing ? "not-allowed" : "pointer",
            }}>
              {syncing ? "Syncing…" : "Sync Activities"}
            </button>
            <button
              onClick={() => { if (window.confirm("Backfill will re-import all Strava history with enriched data (HR, elevation, pace, cadence). This takes ~2 min. Continue?")) handleSync(true); }}
              disabled={syncing}
              title="Re-import full Strava history with enriched fields (HR, elevation, pace, cadence)"
              style={{
                backgroundColor: "transparent",
                color: syncing ? "#64748b" : "#94a3b8",
                border: "1px solid #3a3d4a",
                borderRadius: "0.375rem", padding: "0.4rem 0.6rem",
                fontSize: "0.75rem", cursor: syncing ? "not-allowed" : "pointer",
              }}>
              ↺ Backfill
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
