import { useState } from "react";
import { setToken } from "../api";

export function LoginPage({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        setError("Invalid credentials");
        return;
      }
      const { token } = await res.json();
      setToken(token);
      onLogin();
    } catch {
      setError("Could not reach the server");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center"
      style={{ backgroundColor: "#0f1117" }}
    >
      {/* Ambient blobs */}
      <div aria-hidden style={{ position: "fixed", inset: 0, pointerEvents: "none", overflow: "hidden" }}>
        <div style={{
          position: "absolute", top: "-10%", left: "15%",
          width: "55vw", height: "55vw", borderRadius: "50%",
          background: "radial-gradient(circle, #6366f12e 0%, transparent 70%)",
        }} />
        <div style={{
          position: "absolute", bottom: "0%", right: "5%",
          width: "45vw", height: "35vw", borderRadius: "50%",
          background: "radial-gradient(circle, #8b5cf625 0%, transparent 70%)",
        }} />
      </div>

      <div style={{
        position: "relative", zIndex: 1,
        background: "rgba(13,15,23,0.85)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 16,
        padding: "2.5rem 2rem",
        width: "100%",
        maxWidth: 360,
      }}>
        {/* Logo + title */}
        <div className="flex items-center gap-3 mb-8">
          <img src="/logo.svg" alt="" style={{ width: 36, height: 36, borderRadius: 9 }} />
          <div>
            <div className="text-sm font-bold" style={{ color: "#e2e8f0" }}>Health Adviser</div>
            <div className="text-xs" style={{ color: "#64748b" }}>Sign in to continue</div>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <input
            type="text"
            placeholder="Username"
            autoComplete="username"
            value={username}
            onChange={e => setUsername(e.target.value)}
            required
            style={{
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 8,
              padding: "0.625rem 0.875rem",
              color: "#e2e8f0",
              fontSize: "0.875rem",
              outline: "none",
              width: "100%",
            }}
            onFocus={e => (e.currentTarget.style.borderColor = "rgba(99,102,241,0.6)")}
            onBlur={e => (e.currentTarget.style.borderColor = "rgba(255,255,255,0.1)")}
          />
          <input
            type="password"
            placeholder="Password"
            autoComplete="current-password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
            style={{
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 8,
              padding: "0.625rem 0.875rem",
              color: "#e2e8f0",
              fontSize: "0.875rem",
              outline: "none",
              width: "100%",
            }}
            onFocus={e => (e.currentTarget.style.borderColor = "rgba(99,102,241,0.6)")}
            onBlur={e => (e.currentTarget.style.borderColor = "rgba(255,255,255,0.1)")}
          />

          {error && (
            <p style={{ color: "#f87171", fontSize: "0.8rem", margin: 0 }}>{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              marginTop: "0.25rem",
              background: loading ? "rgba(99,102,241,0.4)" : "rgba(99,102,241,0.9)",
              border: "none",
              borderRadius: 8,
              padding: "0.625rem",
              color: "#fff",
              fontSize: "0.875rem",
              fontWeight: 600,
              cursor: loading ? "not-allowed" : "pointer",
              transition: "background 0.15s",
            }}
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
