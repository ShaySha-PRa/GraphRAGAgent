import { useNavigate } from "react-router-dom";
import StatusBadge from "./StatusBadge";
import type { Document } from "../lib/types";

interface Props {
  docs: Document[];
  onDelete: (docId: string) => void;
}

export default function DocumentTable({ docs, onDelete }: Props) {
  const navigate = useNavigate();

  if (docs.length === 0) {
    return (
      <div style={{ padding: 60, textAlign: "center", color: "var(--color-text-muted)", fontSize: 14 }}>
        No documents yet. Upload one to get started.
      </div>
    );
  }

  return (
    <div
      style={{
        background: "var(--color-card-bg)",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-md)",
        overflow: "hidden",
      }}
    >
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
            <th style={th}>Filename</th>
            <th style={th}>Format</th>
            <th style={th}>Status</th>
            <th style={th}>Created</th>
            <th style={{ ...th, width: 60 }}></th>
          </tr>
        </thead>
        <tbody>
          {docs.map((doc) => (
            <tr
              key={doc.doc_id}
              onClick={() => navigate(`/documents/${doc.doc_id}`)}
              style={{ cursor: "pointer", borderBottom: "1px solid var(--color-border)" }}
            >
              <td style={td}>
                <span style={{ color: "var(--color-accent)", fontWeight: 500 }}>{doc.source_filename}</span>
                {doc.warning && (
                  <span style={{ fontSize: 10, color: "var(--color-warning)", marginLeft: 8 }} title={doc.warning}>
                    ⚡ untested
                  </span>
                )}
              </td>
              <td style={td}>
                <code style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-text-muted)" }}>{doc.detected_format}</code>
              </td>
              <td style={td}><StatusBadge stage={doc.status} /></td>
              <td style={td}>
                <code style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-text-muted)" }}>
                  {doc.created_at?.replace("T", " ").slice(0, 16)}
                </code>
              </td>
              <td style={td}>
                <button
                  onClick={(e) => { e.stopPropagation(); onDelete(doc.doc_id); }}
                  style={{ background: "none", border: "none", fontSize: 14, padding: 4 }}
                  title="Delete"
                >
                  🗑
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const th: React.CSSProperties = {
  textAlign: "left",
  padding: "10px 20px",
  fontSize: 12,
  fontWeight: 600,
  color: "var(--color-text-muted)",
};

const td: React.CSSProperties = {
  padding: "12px 20px",
};
