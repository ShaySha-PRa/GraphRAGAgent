import { useState, useEffect } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import StatusBadge from "../components/StatusBadge";
import GraphView from "../components/GraphView";
import QAChat from "../components/QAChat";
import { api } from "../lib/api";
import type { Document, KGNode, KGEdge } from "../lib/types";

function PipelineLog({ docId, polling }: { docId: string; polling: boolean }) {
  const [log, setLog] = useState<string[] | null>(null);

  useEffect(() => {
    let cancelled = false;

    const fetchLog = async () => {
      try {
        const r = await api.getLog(docId);
        if (!cancelled) setLog(r.log);
      } catch {
        if (!cancelled) setLog((prev) => prev ?? []);
      }
    };

    fetchLog();
    if (!polling) return () => { cancelled = true; };

    const t = setInterval(fetchLog, 2500);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [docId, polling]);

  return (
    <div style={{ marginTop: 24 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <h3 style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>Pipeline Log</h3>
        <span
          style={{
            fontSize: 10,
            fontWeight: 500,
            padding: "1px 6px",
            borderRadius: 3,
            background: polling ? "var(--color-accent)" : "var(--color-success)",
            color: "#fff",
          }}
        >
          {polling ? "Live" : "Final"}
        </span>
      </div>
      <pre
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 11,
          lineHeight: 1.6,
          background: "#0d1117",
          color: "#c9d1d9",
          padding: "14px 18px",
          borderRadius: "var(--radius-sm)",
          overflow: "auto",
          maxHeight: 300,
          margin: 0,
        }}
      >
        {log === null ? "Loading…" : log.length === 0 ? "(empty)" : log.join("\n")}
      </pre>
    </div>
  );
}

type Tab = "overview" | "graph" | "qa";

export default function DocumentDetailPage() {
  const { docId } = useParams<{ docId: string }>();
  const navigate = useNavigate();
  const [doc, setDoc] = useState<Document | null>(null);
  const [graph, setGraph] = useState<{ nodes: KGNode[]; edges: KGEdge[] } | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!docId) return;
    api.getDocument(docId)
      .then(setDoc)
      .catch(() => setDoc(null))
      .finally(() => setLoading(false));
  }, [docId]);

  // Poll while indexing
  useEffect(() => {
    if (!docId || !doc || doc.status === "ready" || doc.status === "failed") return;
    const t = setInterval(async () => {
      try { setDoc(await api.getDocument(docId!)); } catch { /* ignore */ }
    }, 2500);
    return () => clearInterval(t);
  }, [docId, doc]);

  // Load graph when done
  useEffect(() => {
    if (!docId || doc?.status !== "ready") return;
    api.getGraph(docId).then(setGraph).catch(() => {});
  }, [docId, doc?.status]);

  const deleteDoc = async () => {
    if (!docId || !confirm("Delete this document?")) return;
    await api.deleteDocument(docId);
    navigate("/");
  };

  if (loading) return <div style={{ padding: 40, color: "var(--color-text-muted)" }}>Loading…</div>;
  if (!doc) return <div style={{ padding: 40 }}>Document not found. <Link to="/">Back</Link></div>;

  const isDone = doc.status === "ready";
  const isSettled = isDone || doc.status === "failed";

  const steps: { stage: string; label: string; desc: string }[] = [
    { stage: "queued", label: "queued", desc: "File saved" },
    { stage: "parsing", label: "parsing", desc: doc.detected_format === ".txt" || doc.detected_format === ".md" ? "Text adapter" : "MinerU parsing" },
    { stage: "extracting", label: "extracting", desc: "LangExtract KG build" },
    { stage: "ready", label: "ready", desc: "Ready" },
  ];
  const currentIdx = steps.findIndex((s) => s.stage === doc.status);

  return (
    <div style={{ padding: 32, maxWidth: 1100 }}>
      {/* Breadcrumb */}
      <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, marginBottom: 16 }}>
        <Link to="/" style={{ color: "var(--color-accent)" }}>Documents</Link>
        <span style={{ color: "var(--color-text-muted)" }}>/</span>
        <span style={{ fontWeight: 500 }}>{doc.source_filename}</span>
      </div>

      {/* Meta card */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: 20, borderRadius: "var(--radius-md)", background: "var(--color-card-bg)",
        border: "1px solid var(--color-border)", marginBottom: 16,
      }}>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 600, margin: "0 0 4px" }}>{doc.source_filename}</h2>
          <div style={{ display: "flex", gap: 16, fontSize: 12 }}>
            <code style={{ fontFamily: "var(--font-mono)", color: "var(--color-text-muted)" }}>{doc.detected_format}</code>
            <code style={{ fontFamily: "var(--font-mono)", color: "var(--color-text-muted)" }}>{doc.doc_id}</code>
            {isDone && <span style={{ color: "var(--color-text-muted)" }}>{doc.node_count ?? 0} nodes / {doc.edge_count ?? 0} edges</span>}
          </div>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <StatusBadge stage={doc.status} />
          <button onClick={deleteDoc} style={{ background: "none", border: "none", fontSize: 16, cursor: "pointer" }} title="Delete">🗑</button>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", marginBottom: 16, border: "1px solid var(--color-border)", borderRadius: "var(--radius-md)", overflow: "hidden" }}>
        {(["overview", "graph", "qa"] as Tab[]).map((t) => {
          const disabled = t !== "overview" && !isDone;
          return (
            <button
              key={t}
              onClick={() => !disabled && setTab(t)}
              disabled={disabled}
              title={disabled ? "Document must be indexed first" : undefined}
              style={{
                flex: 1, padding: "10px 20px", border: "none",
                background: tab === t ? "var(--color-card-bg)" : "var(--color-bg)",
                borderBottom: tab === t ? "2px solid var(--color-accent)" : "2px solid transparent",
                fontWeight: tab === t ? 600 : 400, fontSize: 13,
                color: disabled ? "var(--color-text-muted)" : "var(--color-text)",
                cursor: disabled ? "not-allowed" : "pointer",
                opacity: disabled ? 0.5 : 1,
              }}
            >
              {t === "overview" ? "Overview" : t === "graph" ? "Graph" : "Q&A"}
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      <div style={{ background: "var(--color-card-bg)", border: "1px solid var(--color-border)", borderRadius: "var(--radius-md)", padding: 24 }}>
        {tab === "overview" && (
          <div>
            {!isSettled && (
              <div>
                <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>Indexing Progress</h3>
                <div style={{ display: "flex", alignItems: "center", gap: 0, marginBottom: 24 }}>
                  {steps.map((s, i) => {
                    const done = i <= currentIdx;
                    const active = i === currentIdx;
                    return (
                      <div key={s.stage} style={{ display: "flex", alignItems: "center", flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
                          <div style={{
                            width: 28, height: 28, borderRadius: "50%",
                            background: done ? "var(--color-success)" : "var(--color-border)",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            color: done ? "#fff" : "var(--color-text-muted)", fontSize: 14, fontWeight: 700,
                            border: active && !done ? "2px solid var(--color-accent)" : "none",
                          }}>
                            {done ? "✓" : i + 1}
                          </div>
                          <span style={{ fontSize: 11, fontWeight: 600, color: done ? "var(--color-text)" : "var(--color-text-muted)" }}>{s.label}</span>
                          <span style={{ fontSize: 10, color: "var(--color-text-muted)" }}>{s.desc}</span>
                        </div>
                        {i < steps.length - 1 && (
                          <div style={{ flex: 1, height: 2, background: done ? "var(--color-success)" : "var(--color-border)", margin: "0 8px", marginBottom: 30 }} />
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {doc.status === "failed" && (
              <div style={{
                padding: 16, borderRadius: 6, background: "rgba(207,34,46,0.06)",
                border: "1px solid var(--color-danger)", marginBottom: 16,
              }}>
                <h4 style={{ fontSize: 14, fontWeight: 600, color: "var(--color-danger)", margin: "0 0 8px" }}>Indexing Failed</h4>
                <pre style={{ fontFamily: "var(--font-mono)", fontSize: 12, whiteSpace: "pre-wrap", margin: 0, color: "var(--color-text)" }}>{doc.error}</pre>
              </div>
            )}

            <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 12 }}>Metadata</h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12 }}>
              {(
                [
                  ["Filename", doc.source_filename, false],
                  ["Format", doc.detected_format, true],
                  ["Status", doc.status, false],
                  ["Created", doc.created_at, true],
                  ["Nodes", String(doc.node_count ?? "—"), false],
                  ["Edges", String(doc.edge_count ?? "—"), false],
                ] as [string, string, boolean][]
              ).map(([label, value, mono]) => (
                <div key={label} style={{ padding: "12px 16px", borderRadius: "var(--radius-sm)", background: "var(--color-bg)", border: "1px solid var(--color-border)" }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: "var(--color-text-muted)", marginBottom: 2 }}>{label}</div>
                  <div style={{ fontFamily: mono ? "var(--font-mono)" : "var(--font-sans)", fontSize: 13, fontWeight: 500 }}>{value}</div>
                </div>
              ))}
            </div>

            <PipelineLog docId={docId!} polling={!isSettled} />
          </div>
        )}

        {tab === "graph" && graph && <GraphView nodes={graph.nodes} edges={graph.edges} />}
        {tab === "graph" && !graph && <div style={{ color: "var(--color-text-muted)", fontSize: 13 }}>Loading graph data…</div>}

        {tab === "qa" && (
          <div style={{ height: 500 }}>
            <QAChat docId={docId!} />
          </div>
        )}
      </div>
    </div>
  );
}
