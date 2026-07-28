import { useState, useRef, useEffect, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "../lib/api";
import type { ChatMessage, Citation } from "../lib/types";

interface Props {
  docId: string;
}

function formatBbox(bbox: number[] | null | undefined): string {
  if (!bbox || bbox.length === 0) return "无坐标";
  return `[${bbox.map((v) => Math.round(v)).join(", ")}]`;
}

function CitationsList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) {
    return (
      <div style={{ marginTop: 10, fontSize: 11, color: "var(--color-text-muted)" }}>
        无结构化引用（本次回答未附带 citations）
      </div>
    );
  }

  return (
    <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--color-text-muted)" }}>
        Citations ({citations.length})
      </div>
      {citations.map((c, i) => (
        <div
          key={`${c.node_id ?? "c"}-${i}`}
          style={{
            padding: "8px 10px",
            borderRadius: "var(--radius-sm)",
            background: "var(--color-bg)",
            border: "1px solid var(--color-border)",
            fontSize: 11,
            lineHeight: 1.5,
          }}
        >
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <code style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>{c.source_kind}</code>
            {c.node_id && (
              <code style={{ fontFamily: "var(--font-mono)", color: "var(--color-text-muted)" }}>
                id:{c.node_id.slice(0, 12)}
              </code>
            )}
            <span style={{ color: "var(--color-text-muted)" }}>
              page {c.page_idx ?? "—"}
            </span>
            {c.bbox ? (
              <code style={{ fontFamily: "var(--font-mono)" }}>{formatBbox(c.bbox)}</code>
            ) : (
              <span style={{ color: "var(--color-danger)", fontWeight: 500 }}>无坐标</span>
            )}
          </div>
          {c.note && (
            <div style={{ marginTop: 4, color: "var(--color-text-muted)" }}>{c.note}</div>
          )}
        </div>
      ))}
    </div>
  );
}

export default function QAChat({ docId }: Props) {
  const sessionId = useRef(
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `sess-${Date.now()}-${Math.random().toString(36).slice(2)}`,
  );
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "system",
      content:
        "回答可附带结构化 citations（page_idx / bbox）。本页会话会传 session_id 以支持多轮追问；刷新页面后历史与会话会重置。",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async (e?: FormEvent) => {
    e?.preventDefault();
    const q = input.trim();
    if (!q || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: q }]);
    setInput("");
    setError("");
    setLoading(true);

    try {
      const res = await api.askQuestion(docId, q, sessionId.current);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.answer, citations: res.citations ?? [] },
      ]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: 12 }}>
      <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 12 }}>
        {messages.map((m, i) => (
          <div
            key={i}
            style={{
              alignSelf: m.role === "user" ? "flex-end" : "flex-start",
              maxWidth: "80%",
              padding: m.role === "system" ? "10px 14px" : "12px 16px",
              borderRadius: m.role === "user" ? "12px 12px 4px 12px" : "4px 12px 12px 12px",
              background:
                m.role === "user" ? "rgba(47,129,247,0.1)"
                : m.role === "system" ? "rgba(154,103,0,0.08)"
                : "var(--color-bg)",
              border: m.role === "assistant" ? "1px solid var(--color-border)" : "none",
              borderLeft: m.role === "system" ? "3px solid var(--color-warning)" : undefined,
              fontSize: 13,
              lineHeight: 1.6,
            }}
          >
            {m.role === "system" && (
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--color-warning)", marginBottom: 4 }}>
                ℹ Note
              </div>
            )}
            {m.role === "assistant" ? <ReactMarkdown>{m.content}</ReactMarkdown> : <span>{m.content}</span>}
            {m.role === "assistant" && <CitationsList citations={m.citations ?? []} />}
          </div>
        ))}
        {loading && (
          <div style={{ fontSize: 13, color: "var(--color-text-muted)", fontStyle: "italic" }}>
            Thinking…
          </div>
        )}
        {error && (
          <div
            style={{
              padding: 10,
              borderRadius: 6,
              background: "rgba(207,34,46,0.08)",
              border: "1px solid var(--color-danger)",
              fontSize: 12,
              color: "var(--color-danger)",
            }}
          >
            {error}
            <button
              onClick={() => {
                setError("");
                send();
              }}
              style={{
                marginLeft: 12,
                background: "none",
                border: "none",
                color: "var(--color-accent)",
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              Retry
            </button>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={send}
        style={{ display: "flex", gap: 8, paddingTop: 8, borderTop: "1px solid var(--color-border)" }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question about this document…"
          disabled={loading}
          style={{
            flex: 1,
            padding: "10px 14px",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-sm)",
            fontSize: 13,
            fontFamily: "var(--font-sans)",
            outline: "none",
            background: "var(--color-card-bg)",
          }}
          onFocus={(e) => {
            (e.target as HTMLInputElement).style.borderColor = "var(--color-accent)";
          }}
          onBlur={(e) => {
            (e.target as HTMLInputElement).style.borderColor = "var(--color-border)";
          }}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          style={{
            padding: "10px 20px",
            background: loading ? "var(--color-text-muted)" : "var(--color-accent)",
            color: "#fff",
            border: "none",
            borderRadius: "var(--radius-sm)",
            fontWeight: 500,
            fontSize: 13,
            cursor: loading ? "not-allowed" : "pointer",
          }}
        >
          Send
        </button>
      </form>
    </div>
  );
}
