import { useState, useRef, useCallback, useEffect } from "react";
import { Sparkles, X, ChevronDown, ChevronUp, Send, User } from "lucide-react";
import { api } from "../api";

interface Message {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}

interface AdviserPanelProps {
  tab: string;
  start: string;
  end: string;
  gatherData: () => Record<string, unknown>;
}

// ── Markdown renderer ─────────────────────────────────────────────────────────
function renderMarkdown(text: string) {
  const lines = text.split("\n");
  const elements: JSX.Element[] = [];
  let key = 0;

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      elements.push(<div key={key++} className="h-2" />);
      continue;
    }

    const parts = trimmed.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
      part.startsWith("**") && part.endsWith("**")
        ? <strong key={i} style={{ color: "#e2e8f0" }}>{part.slice(2, -2)}</strong>
        : part
    );

    if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      elements.push(
        <div key={key++} className="flex gap-2 ml-2" style={{ lineHeight: 1.6 }}>
          <span style={{ color: "#6366f1", flexShrink: 0 }}>·</span>
          <span>{parts.map((p, i) => typeof p === "string" ? p.replace(/^[-*]\s/, "") : p)}</span>
        </div>
      );
      continue;
    }

    if (trimmed.startsWith("## ") || trimmed.startsWith("### ")) {
      const level = trimmed.startsWith("### ") ? 3 : 2;
      elements.push(
        <div key={key++}
          className={level === 2 ? "text-sm font-semibold mt-3 mb-1" : "text-xs font-semibold mt-2 mb-1"}
          style={{ color: "#e2e8f0" }}
        >
          {trimmed.replace(/^#{2,3}\s/, "")}
        </div>
      );
      continue;
    }

    elements.push(<p key={key++} style={{ lineHeight: 1.6, margin: 0 }}>{parts}</p>);
  }
  return elements;
}

// ── Single message bubble ─────────────────────────────────────────────────────
function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  return (
    <div style={{ display: "flex", gap: "0.6rem", alignItems: "flex-start" }}>
      {/* Avatar */}
      <div style={{
        width: "1.6rem", height: "1.6rem", borderRadius: "50%", flexShrink: 0,
        display: "flex", alignItems: "center", justifyContent: "center",
        marginTop: "0.1rem",
        background: isUser ? "rgba(99,102,241,0.15)" : "rgba(99,102,241,0.25)",
        border: `1px solid ${isUser ? "rgba(99,102,241,0.3)" : "rgba(99,102,241,0.5)"}`,
      }}>
        {isUser
          ? <User size={10} style={{ color: "#818cf8" }} />
          : <Sparkles size={10} style={{ color: "#a78bfa" }} />
        }
      </div>

      {/* Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: "0.65rem", fontWeight: 600, marginBottom: "0.25rem",
          color: isUser ? "#818cf8" : "#a78bfa",
          textTransform: "uppercase", letterSpacing: "0.06em",
        }}>
          {isUser ? "You" : "Health Adviser"}
        </div>
        <div style={{ fontSize: "0.82rem", color: "#cbd5e1", lineHeight: 1.65 }}>
          {isUser
            ? <p style={{ margin: 0 }}>{msg.content}</p>
            : (
              <>
                {renderMarkdown(msg.content)}
                {msg.streaming && (
                  <span className="inline-block w-1.5 h-4 ml-0.5 animate-pulse"
                    style={{ background: "#6366f1", borderRadius: 1, verticalAlign: "middle" }} />
                )}
              </>
            )
          }
        </div>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export function AdviserPanel({ tab, start, end, gatherData }: AdviserPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [collapsed, setCollapsed]   = useState(false);
  const [loading, setLoading]       = useState(false);
  const [followUp, setFollowUp]     = useState("");
  const [cachedData, setCachedData] = useState<Record<string, unknown>>({});
  const streamRef  = useRef("");
  const scrollRef  = useRef<HTMLDivElement>(null);
  const inputRef   = useRef<HTMLInputElement>(null);

  const hasContent = messages.length > 0;

  // Auto-scroll to bottom on new content
  useEffect(() => {
    if (scrollRef.current && !collapsed) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, collapsed]);

  // ── Stream helper ──────────────────────────────────────────────────────────
  const streamInto = useCallback((
    fetchFn: (onChunk: (c: string) => void, onDone: () => void, onError: (e: string) => void) => void
  ) => {
    streamRef.current = "";
    setLoading(true);
    setCollapsed(false);

    // Add a blank assistant message that we'll fill via streaming
    setMessages(prev => [...prev, { role: "assistant", content: "", streaming: true }]);

    fetchFn(
      (chunk) => {
        streamRef.current += chunk;
        const text = streamRef.current;
        setMessages(prev => {
          const next = [...prev];
          next[next.length - 1] = { role: "assistant", content: text, streaming: true };
          return next;
        });
      },
      () => {
        const text = streamRef.current;
        setMessages(prev => {
          const next = [...prev];
          next[next.length - 1] = { role: "assistant", content: text, streaming: false };
          return next;
        });
        setLoading(false);
      },
      (err) => {
        setMessages(prev => {
          const next = [...prev];
          next[next.length - 1] = { role: "assistant", content: `Error: ${err}`, streaming: false };
          return next;
        });
        setLoading(false);
      },
    );
  }, []);

  // ── Initial assessment ─────────────────────────────────────────────────────
  const runAssessment = useCallback(() => {
    const data = gatherData();
    setCachedData(data);
    setMessages([]);  // Reset conversation
    streamInto((onChunk, onDone, onError) =>
      api.adviserAssess(tab, start, end, data, onChunk, onDone, onError)
    );
  }, [tab, start, end, gatherData, streamInto]);

  // ── Follow-up question ─────────────────────────────────────────────────────
  const sendFollowUp = useCallback(() => {
    const q = followUp.trim();
    if (!q || loading) return;
    setFollowUp("");

    // Build conversation history for the API (exclude streaming placeholder)
    const history = messages
      .filter(m => !m.streaming)
      .map(m => ({ role: m.role, content: m.content }));
    history.push({ role: "user", content: q });

    // Add user message to UI immediately
    setMessages(prev => [...prev, { role: "user", content: q }]);

    streamInto((onChunk, onDone, onError) =>
      api.adviserFollowup(tab, start, end, cachedData, history, onChunk, onDone, onError)
    );
  }, [followUp, loading, messages, tab, start, end, cachedData, streamInto]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendFollowUp(); }
  };

  // ── Collapsed pill ─────────────────────────────────────────────────────────
  if (hasContent && collapsed) {
    return (
      <button
        onClick={() => setCollapsed(false)}
        style={{
          display: "flex", alignItems: "center", gap: "0.6rem",
          width: "100%", padding: "0.55rem 1rem",
          background: "rgba(99,102,241,0.07)",
          border: "1px solid rgba(99,102,241,0.18)",
          borderRadius: "0.6rem", cursor: "pointer",
          transition: "background 0.15s",
        }}
      >
        <Sparkles size={13} style={{ color: "#6366f1", flexShrink: 0 }} />
        <span style={{ fontSize: "0.72rem", color: "#818cf8", fontWeight: 600 }}>
          Health Adviser
        </span>
        <span style={{ fontSize: "0.7rem", color: "#475569" }}>
          · Assessment ready · {messages.length} message{messages.length !== 1 ? "s" : ""}
        </span>
        <span style={{ marginLeft: "auto", color: "#475569" }}>
          <ChevronDown size={13} />
        </span>
      </button>
    );
  }

  // ── Full panel ─────────────────────────────────────────────────────────────
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0" }}>

      {/* ── Header bar (always visible) ── */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
        <button
          onClick={runAssessment}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all"
          style={{
            background: loading
              ? "rgba(99,102,241,0.3)"
              : "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
            color: "#fff",
            border: "1px solid rgba(99,102,241,0.4)",
            cursor: loading ? "wait" : "pointer",
            boxShadow: loading ? "none" : "0 0 20px rgba(99,102,241,0.2)",
          }}
        >
          <Sparkles size={14} className={loading ? "animate-spin" : ""} />
          {loading && messages.length === 0
            ? "Analyzing…"
            : hasContent ? "Re-run" : "Adviser Assessment"}
        </button>

        {hasContent && !loading && (
          <>
            <button
              onClick={() => setCollapsed(true)}
              title="Minimise"
              style={{
                display: "flex", alignItems: "center", gap: "0.25rem",
                fontSize: "0.72rem", color: "#64748b", cursor: "pointer",
                background: "transparent", border: "none", padding: "0.25rem 0.5rem",
              }}
            >
              <ChevronUp size={12} /> Minimise
            </button>
            <button
              onClick={() => { setMessages([]); setCollapsed(false); }}
              title="Clear conversation"
              style={{
                display: "flex", alignItems: "center", gap: "0.25rem",
                fontSize: "0.72rem", color: "#475569", cursor: "pointer",
                background: "transparent", border: "none", padding: "0.25rem 0.5rem",
              }}
            >
              <X size={12} /> Clear
            </button>
          </>
        )}
      </div>

      {/* ── Conversation panel ── */}
      {hasContent && (
        <div style={{
          marginTop: "0.75rem",
          background: "rgba(99,102,241,0.05)",
          backdropFilter: "blur(12px)",
          border: "1px solid rgba(99,102,241,0.14)",
          borderRadius: "0.85rem",
          overflow: "hidden",
          animation: "fadeIn 0.25s ease",
        }}>
          {/* Panel header */}
          <div style={{
            display: "flex", alignItems: "center", gap: "0.5rem",
            padding: "0.65rem 1rem",
            borderBottom: "1px solid rgba(99,102,241,0.1)",
          }}>
            <Sparkles size={12} style={{ color: "#6366f1" }} />
            <span style={{ fontSize: "0.68rem", fontWeight: 700, color: "#818cf8", textTransform: "uppercase", letterSpacing: "0.07em" }}>
              Health Adviser
            </span>
            <span style={{ fontSize: "0.67rem", color: "#475569" }}>
              {start} → {end}
            </span>
          </div>

          {/* Message thread */}
          <div
            ref={scrollRef}
            style={{
              maxHeight: "480px",
              overflowY: "auto",
              padding: "1rem",
              display: "flex",
              flexDirection: "column",
              gap: "1.25rem",
            }}
          >
            {messages.map((msg, i) => <MessageBubble key={i} msg={msg} />)}
          </div>

          {/* ── Follow-up input ── */}
          {!loading && messages.length > 0 && (
            <div style={{
              display: "flex", gap: "0.5rem", alignItems: "center",
              padding: "0.65rem 1rem",
              borderTop: "1px solid rgba(99,102,241,0.1)",
              background: "rgba(10,12,24,0.3)",
            }}>
              <input
                ref={inputRef}
                value={followUp}
                onChange={e => setFollowUp(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask a follow-up question…"
                style={{
                  flex: 1, background: "rgba(99,102,241,0.08)",
                  border: "1px solid rgba(99,102,241,0.2)",
                  borderRadius: "0.5rem", padding: "0.45rem 0.75rem",
                  fontSize: "0.78rem", color: "#e2e8f0", outline: "none",
                }}
              />
              <button
                onClick={sendFollowUp}
                disabled={!followUp.trim()}
                style={{
                  padding: "0.45rem 0.7rem", borderRadius: "0.5rem",
                  background: followUp.trim()
                    ? "linear-gradient(135deg, #6366f1, #8b5cf6)"
                    : "rgba(99,102,241,0.15)",
                  border: "1px solid rgba(99,102,241,0.3)",
                  color: followUp.trim() ? "#fff" : "#475569",
                  cursor: followUp.trim() ? "pointer" : "default",
                  display: "flex", alignItems: "center",
                  transition: "all 0.15s",
                }}
              >
                <Send size={13} />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
