import { useState, useEffect, useRef } from "react";
import { api } from "../api";
import type { GarminStatus, SyncResult } from "../api";

const GARMIN_BLUE = "#00a2e8";

function fmtLastSync(ts: number | null): string {
  if (!ts) return "Never";
  return new Date(ts * 1000).toLocaleString("en", {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export function GarminSync() {
  const [status, setStatus]       = useState<GarminStatus | null>(null);
  const [syncing, setSyncing]     = useState(false);
  const [result, setResult]       = useState<SyncResult | null>(null);
  const [error, setError]         = useState<string | null>(null);
  const [showForm, setShowForm]   = useState(false);
  const [email, setEmail]         = useState("");
  const [password, setPassword]   = useState("");
  const [mfaCode, setMfaCode]     = useState("");
  const [needsMfa, setNeedsMfa]   = useState(false);
  const [logging, setLogging]     = useState(false);
  const pollRef                   = useRef<ReturnType<typeof setInterval> | null>(null);

  function refreshStatus() {
    api.garminStatus().then(setStatus).catch(() => setStatus(null));
  }
  useEffect(() => { refreshStatus(); }, []);

  function stopPolling() {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }

  function startPolling() {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.garminSyncStatus();
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

  useEffect(() => () => stopPolling(), []);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLogging(true);
    setError(null);
    try {
      await api.garminConnect(email, password, needsMfa ? mfaCode : undefined);
      setShowForm(false);
      setEmail(""); setPassword(""); setMfaCode(""); setNeedsMfa(false);
      refreshStatus();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Login failed";
      if (msg.includes("MFA_REQUIRED")) {
        setNeedsMfa(true);
        setError("Enter the 6-digit code from your Garmin authenticator app.");
      } else {
        setError(msg);
      }
    } finally {
      setLogging(false);
    }
  }

  async function handleDisconnect() {
    if (!window.confirm("Disconnect Garmin? Your synced activities will remain in the database.")) return;
    await api.garminDisconnect();
    setResult(null);
    refreshStatus();
  }

  async function handleSync(force = false) {
    setSyncing(true);
    setResult(null);
    setError(null);
    try {
      await api.garminSync(force);
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
      flexDirection: "column",
      gap: "0.75rem",
    }}>
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.75rem" }}>
        {/* Left */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <span style={{ color: GARMIN_BLUE, fontWeight: 700, fontSize: "0.9rem", letterSpacing: "0.02em" }}>
            Garmin
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
              {status?.email && <>{status.email} · </>}
              Last sync: {fmtLastSync(status?.last_sync ?? null)}
            </span>
          )}
        </div>

        {/* Right: actions */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          {result && (
            <span style={{ fontSize: "0.75rem", color: "#10b981" }}>
              ✓ {result.added} added{result.skipped > 0 ? `, ${result.skipped} skipped` : ""}
            </span>
          )}
          {error && !showForm && (
            <span style={{ fontSize: "0.75rem", color: "#ef4444" }}>{error}</span>
          )}
          {syncing && (
            <span style={{ fontSize: "0.75rem", color: "#64748b" }}>Fetching activities…</span>
          )}

          {!connected ? (
            <button onClick={() => { setShowForm(f => !f); setError(null); }} style={{
              backgroundColor: GARMIN_BLUE, color: "#fff", border: "none",
              borderRadius: "0.375rem", padding: "0.4rem 0.9rem",
              fontSize: "0.8rem", fontWeight: 600, cursor: "pointer",
            }}>
              Connect Garmin
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
                onClick={() => { if (window.confirm("Re-import full Garmin history? This will delete existing Garmin data and re-sync everything.")) handleSync(true); }}
                disabled={syncing}
                title="Re-import full Garmin history"
                style={{
                  backgroundColor: "transparent",
                  color: syncing ? "#64748b" : "#94a3b8",
                  border: "1px solid #3a3d4a",
                  borderRadius: "0.375rem", padding: "0.4rem 0.6rem",
                  fontSize: "0.75rem", cursor: syncing ? "not-allowed" : "pointer",
                }}>
                ↺ Backfill
              </button>
              <button onClick={handleDisconnect} style={{
                backgroundColor: "transparent",
                color: "#64748b",
                border: "1px solid #3a3d4a",
                borderRadius: "0.375rem", padding: "0.4rem 0.6rem",
                fontSize: "0.75rem", cursor: "pointer",
              }}>
                Disconnect
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Login form (shown when connecting) */}
      {showForm && !connected && (
        <form onSubmit={handleLogin} style={{
          display: "flex", flexDirection: "column", gap: "0.5rem",
          borderTop: "1px solid #2a2d3a", paddingTop: "0.75rem",
        }}>
          <p style={{ margin: 0, fontSize: "0.75rem", color: "#94a3b8" }}>
            Enter your Garmin Connect credentials. They are used only to fetch your activities and are stored locally.
          </p>
          {error && (
            <span style={{ fontSize: "0.75rem", color: "#ef4444" }}>{error}</span>
          )}
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            {!needsMfa && (
              <>
                <input
                  type="email" placeholder="Email" value={email}
                  onChange={e => setEmail(e.target.value)} required
                  style={{
                    flex: 1, minWidth: "160px",
                    backgroundColor: "#0f1117", border: "1px solid #2a2d3a",
                    borderRadius: "0.375rem", padding: "0.4rem 0.75rem",
                    color: "#e2e8f0", fontSize: "0.8rem", outline: "none",
                  }}
                />
                <input
                  type="password" placeholder="Password" value={password}
                  onChange={e => setPassword(e.target.value)} required
                  style={{
                    flex: 1, minWidth: "160px",
                    backgroundColor: "#0f1117", border: "1px solid #2a2d3a",
                    borderRadius: "0.375rem", padding: "0.4rem 0.75rem",
                    color: "#e2e8f0", fontSize: "0.8rem", outline: "none",
                  }}
                />
              </>
            )}
            {needsMfa && (
              <input
                type="text" placeholder="6-digit MFA code" value={mfaCode}
                onChange={e => setMfaCode(e.target.value)} required autoFocus
                maxLength={6}
                style={{
                  flex: 1, minWidth: "160px",
                  backgroundColor: "#0f1117", border: "1px solid #f59e0b",
                  borderRadius: "0.375rem", padding: "0.4rem 0.75rem",
                  color: "#e2e8f0", fontSize: "0.8rem", outline: "none",
                  letterSpacing: "0.2em",
                }}
              />
            />
            <button type="submit" disabled={logging} style={{
              backgroundColor: logging ? "#2a2d3a" : GARMIN_BLUE,
              color: logging ? "#64748b" : "#fff",
              border: "none", borderRadius: "0.375rem",
              padding: "0.4rem 0.9rem", fontSize: "0.8rem",
              fontWeight: 600, cursor: logging ? "not-allowed" : "pointer",
            }}>
              {logging ? "Connecting…" : "Connect"}
            </button>
            <button type="button" onClick={() => { setShowForm(false); setError(null); }} style={{
              backgroundColor: "transparent", color: "#64748b",
              border: "1px solid #3a3d4a", borderRadius: "0.375rem",
              padding: "0.4rem 0.6rem", fontSize: "0.75rem", cursor: "pointer",
            }}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
