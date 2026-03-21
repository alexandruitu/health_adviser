import { useState, useEffect, useRef } from "react";
import { api } from "../api";

const APPLE_COLOR  = "#ff375f";
const GDRIVE_COLOR = "#4285f4";

function fmtTime(ts: number | null): string {
  if (!ts) return "Never";
  return new Date(ts * 1000).toLocaleString("en", {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export function HealthSync() {
  const [healthStatus, setHealthStatus] = useState<{
    last_ingest: number | null; total_added: number; webhook_url: string
  } | null>(null);
  const [gdriveStatus, setGdriveStatus] = useState<{
    connected: boolean; last_sync: number | null; folder_path: string
  } | null>(null);
  const [gdriveSyncing, setGdriveSyncing] = useState(false);
  const [gdriveResult, setGdriveResult]   = useState<string | null>(null);
  const [copied, setCopied]               = useState(false);
  const [uploading, setUploading]         = useState(false);
  const [uploadResult, setUploadResult]   = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function refreshHealth() {
    api.healthStatus().then(setHealthStatus).catch(() => setHealthStatus(null));
  }
  function refreshGdrive() {
    fetch("/api/gdrive/status").then(r => r.json()).then(setGdriveStatus).catch(() => {});
  }

  useEffect(() => {
    refreshHealth();
    refreshGdrive();
  }, []);

  function copyUrl() {
    if (!healthStatus?.webhook_url) return;
    navigator.clipboard.writeText(healthStatus.webhook_url).then(() => {
      setCopied(true); setTimeout(() => setCopied(false), 2000);
    });
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true); setUploadResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res  = await fetch("/api/health/upload", { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Upload failed");
      setUploadResult(`✓ ${data.added} added, ${data.skipped} skipped`);
      refreshHealth();
      setTimeout(() => setUploadResult(null), 6000);
    } catch (err: unknown) {
      setUploadResult(`✗ ${err instanceof Error ? err.message : "Upload failed"}`);
      setTimeout(() => setUploadResult(null), 6000);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function startGdriveSync() {
    setGdriveSyncing(true); setGdriveResult(null);
    await fetch("/api/gdrive/sync", { method: "POST" });
    const poll = setInterval(async () => {
      const s = await fetch("/api/gdrive/sync/status").then(r => r.json());
      if (s.status !== "running") {
        clearInterval(poll);
        setGdriveSyncing(false);
        if (s.status === "done") {
          setGdriveResult(`✓ ${s.added} added, ${s.skipped} skipped`);
          refreshHealth(); refreshGdrive();
        } else {
          setGdriveResult(`✗ ${s.error || "Sync failed"}`);
        }
        setTimeout(() => setGdriveResult(null), 8000);
      }
    }, 3000);
  }

  const hasHealth  = healthStatus && healthStatus.last_ingest !== null;
  const hasGdrive  = gdriveStatus?.connected;

  const rowStyle: React.CSSProperties = {
    backgroundColor: "#1a1d27", border: "1px solid #2a2d3a",
    borderRadius: "0.75rem", padding: "0.75rem 1.25rem",
    display: "flex", alignItems: "center", justifyContent: "space-between",
    flexWrap: "wrap", gap: "0.75rem",
  };
  const badgeStyle = (active: boolean): React.CSSProperties => ({
    fontSize: "0.65rem", fontWeight: 600, padding: "0.15rem 0.5rem",
    borderRadius: "0.25rem",
    backgroundColor: active ? "#10b98118" : "#64748b18",
    color: active ? "#10b981" : "#64748b",
    border: `1px solid ${active ? "#10b98130" : "#64748b30"}`,
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>

      {/* ── Apple Health row ── */}
      <div style={rowStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <span style={{ color: APPLE_COLOR, fontWeight: 700, fontSize: "0.9rem" }}>Apple Health</span>
          <span style={badgeStyle(!!hasHealth)}>{hasHealth ? "Connected" : "Waiting"}</span>
          {hasHealth && (
            <span style={{ color: "#64748b", fontSize: "0.75rem" }}>
              {healthStatus!.total_added.toLocaleString()} records · Last: {fmtTime(healthStatus!.last_ingest)}
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
          {uploadResult && (
            <span style={{ fontSize: "0.72rem", fontWeight: 600,
              color: uploadResult.startsWith("✓") ? "#10b981" : "#ef4444" }}>
              {uploadResult}
            </span>
          )}
          <input ref={fileRef} type="file" accept=".hae,.json"
            style={{ display: "none" }} onChange={handleFileUpload} />
          <button onClick={() => fileRef.current?.click()} disabled={uploading} style={{
            backgroundColor: uploading ? "#64748b20" : "#ff375f18",
            color: uploading ? "#64748b" : APPLE_COLOR,
            border: `1px solid ${uploading ? "#64748b30" : "#ff375f40"}`,
            borderRadius: "0.375rem", padding: "0.3rem 0.7rem",
            fontSize: "0.75rem", fontWeight: 600,
            cursor: uploading ? "not-allowed" : "pointer", whiteSpace: "nowrap",
          }}>
            {uploading ? "Uploading…" : "⬆ Upload .hae"}
          </button>
          {healthStatus?.webhook_url && (
            <>
              <code style={{ fontSize: "0.72rem", color: "#94a3b8", backgroundColor: "#0f1117",
                border: "1px solid #2a2d3a", borderRadius: "0.25rem",
                padding: "0.2rem 0.5rem", userSelect: "all" }}>
                {healthStatus.webhook_url}
              </code>
              <button onClick={copyUrl} style={{
                backgroundColor: copied ? "#10b98120" : "#6366f120",
                color: copied ? "#10b981" : "#6366f1",
                border: `1px solid ${copied ? "#10b98140" : "#6366f140"}`,
                borderRadius: "0.375rem", padding: "0.3rem 0.7rem",
                fontSize: "0.75rem", fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap",
              }}>
                {copied ? "Copied!" : "Copy URL"}
              </button>
            </>
          )}
        </div>
      </div>

      {/* ── Google Drive row ── */}
      <div style={rowStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <span style={{ color: GDRIVE_COLOR, fontWeight: 700, fontSize: "0.9rem" }}>Google Drive</span>
          <span style={badgeStyle(!!hasGdrive)}>{hasGdrive ? "Connected" : "Not connected"}</span>
          {hasGdrive && (
            <span style={{ color: "#64748b", fontSize: "0.75rem" }}>
              {gdriveStatus!.folder_path} · Last sync: {fmtTime(gdriveStatus!.last_sync)}
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          {gdriveResult && (
            <span style={{ fontSize: "0.72rem", fontWeight: 600,
              color: gdriveResult.startsWith("✓") ? "#10b981" : "#ef4444" }}>
              {gdriveResult}
            </span>
          )}
          {!hasGdrive ? (
            <button onClick={() => window.open("/api/gdrive/auth", "_blank")} style={{
              backgroundColor: "#4285f418", color: GDRIVE_COLOR,
              border: "1px solid #4285f440", borderRadius: "0.375rem",
              padding: "0.3rem 0.7rem", fontSize: "0.75rem", fontWeight: 600,
              cursor: "pointer", whiteSpace: "nowrap",
            }}>
              Connect Google Drive
            </button>
          ) : (
            <button onClick={startGdriveSync} disabled={gdriveSyncing} style={{
              backgroundColor: gdriveSyncing ? "#64748b20" : "#4285f418",
              color: gdriveSyncing ? "#64748b" : GDRIVE_COLOR,
              border: `1px solid ${gdriveSyncing ? "#64748b30" : "#4285f440"}`,
              borderRadius: "0.375rem", padding: "0.3rem 0.7rem",
              fontSize: "0.75rem", fontWeight: 600,
              cursor: gdriveSyncing ? "not-allowed" : "pointer", whiteSpace: "nowrap",
            }}>
              {gdriveSyncing ? "Syncing…" : "↺ Sync from Drive"}
            </button>
          )}
        </div>
      </div>

    </div>
  );
}
