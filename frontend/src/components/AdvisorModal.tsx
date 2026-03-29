import { useState, useRef, useEffect } from "react";
import { X, Send, Loader2, BrainCircuit, User } from "lucide-react";

interface Message {
  role: "user" | "advisor";
  text: string;
}

interface Props {
  onClose: () => void;
}

export function AdvisorModal({ onClose }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function send() {
    const question = input.trim();
    if (!question || loading) return;

    setInput("");
    setError(null);
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setLoading(true);

    try {
      const res = await fetch("/api/advisor/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Request failed" }));
        throw new Error(err.detail || "Request failed");
      }
      const data = await res.json();
      setMessages((prev) => [...prev, { role: "advisor", text: data.answer }]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: "fixed", inset: 0, zIndex: 40,
          background: "rgba(0,0,0,0.5)",
          backdropFilter: "blur(4px)",
        }}
      />

      {/* Panel */}
      <div
        style={{
          position: "fixed", top: 0, right: 0, bottom: 0, zIndex: 50,
          width: "min(560px, 100vw)",
          background: "rgba(15,17,27,0.97)",
          borderLeft: "1px solid rgba(255,255,255,0.08)",
          display: "flex", flexDirection: "column",
          boxShadow: "-8px 0 40px rgba(0,0,0,0.6)",
        }}
      >
        {/* Header */}
        <div style={{
          padding: "1.25rem 1.5rem",
          borderBottom: "1px solid rgba(255,255,255,0.07)",
          display: "flex", alignItems: "center", gap: "0.75rem",
        }}>
          <div style={{
            width: 36, height: 36, borderRadius: "10px",
            background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0,
          }}>
            <BrainCircuit size={18} color="#fff" />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ color: "#e2e8f0", fontWeight: 600, fontSize: "0.95rem" }}>Health Advisor</div>
            <div style={{ color: "#64748b", fontSize: "0.75rem" }}>Powered by Claude · uses your health data</div>
          </div>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", cursor: "pointer", color: "#64748b", padding: "4px" }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: "auto", padding: "1.25rem 1.5rem", display: "flex", flexDirection: "column", gap: "1.25rem" }}>
          {messages.length === 0 && !loading && (
            <div style={{ color: "#475569", fontSize: "0.875rem", textAlign: "center", marginTop: "2rem" }}>
              Ask anything about your health data — recent metrics, workouts, sleep, or lab results.
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
              {/* Avatar */}
              <div style={{
                width: 30, height: 30, borderRadius: "8px", flexShrink: 0,
                background: msg.role === "user"
                  ? "rgba(99,102,241,0.2)"
                  : "linear-gradient(135deg, #6366f1, #8b5cf6)",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                {msg.role === "user"
                  ? <User size={14} color="#818cf8" />
                  : <BrainCircuit size={14} color="#fff" />}
              </div>

              {/* Bubble */}
              <div style={{
                flex: 1,
                background: msg.role === "user" ? "rgba(99,102,241,0.1)" : "rgba(255,255,255,0.04)",
                border: `1px solid ${msg.role === "user" ? "rgba(99,102,241,0.2)" : "rgba(255,255,255,0.07)"}`,
                borderRadius: "12px",
                padding: "0.75rem 1rem",
                color: "#cbd5e1",
                fontSize: "0.875rem",
                lineHeight: 1.65,
                whiteSpace: "pre-wrap",
              }}>
                {msg.text}
              </div>
            </div>
          ))}

          {loading && (
            <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
              <div style={{
                width: 30, height: 30, borderRadius: "8px", flexShrink: 0,
                background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <BrainCircuit size={14} color="#fff" />
              </div>
              <div style={{
                padding: "0.75rem 1rem",
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.07)",
                borderRadius: "12px",
                display: "flex", gap: "0.5rem", alignItems: "center",
                color: "#64748b", fontSize: "0.875rem",
              }}>
                <Loader2 size={14} className="animate-spin" style={{ animation: "spin 1s linear infinite" }} />
                Analyzing your health data…
              </div>
            </div>
          )}

          {error && (
            <div style={{
              padding: "0.75rem 1rem",
              background: "rgba(239,68,68,0.1)",
              border: "1px solid rgba(239,68,68,0.2)",
              borderRadius: "10px",
              color: "#f87171",
              fontSize: "0.8rem",
            }}>
              {error}
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div style={{
          padding: "1rem 1.5rem",
          borderTop: "1px solid rgba(255,255,255,0.07)",
          display: "flex", gap: "0.75rem", alignItems: "flex-end",
        }}>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your health data… (Enter to send)"
            rows={2}
            style={{
              flex: 1, resize: "none",
              background: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: "10px",
              padding: "0.65rem 0.9rem",
              color: "#e2e8f0",
              fontSize: "0.875rem",
              outline: "none",
              fontFamily: "inherit",
              lineHeight: 1.5,
            }}
          />
          <button
            onClick={send}
            disabled={!input.trim() || loading}
            style={{
              width: 40, height: 40, borderRadius: "10px", flexShrink: 0,
              background: input.trim() && !loading
                ? "linear-gradient(135deg, #6366f1, #8b5cf6)"
                : "rgba(255,255,255,0.06)",
              border: "none", cursor: input.trim() && !loading ? "pointer" : "default",
              display: "flex", alignItems: "center", justifyContent: "center",
              transition: "background 0.2s",
            }}
          >
            <Send size={16} color={input.trim() && !loading ? "#fff" : "#475569"} />
          </button>
        </div>
      </div>

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </>
  );
}
