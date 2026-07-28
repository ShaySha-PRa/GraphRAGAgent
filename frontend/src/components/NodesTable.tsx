import type { KGNode, KGEdge } from "../lib/types";

interface Props {
  nodes: KGNode[];
  edges: KGEdge[];
}

function bboxStr(b: number[] | null | undefined) {
  if (!b) return "无坐标";
  return `[${b.map((v) => Math.round(v)).join(", ")}]`;
}

export default function NodesTable({ nodes }: Pick<Props, "nodes">) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
            {["Name", "Label", "Page", "Bbox", "Type", "Attributes"].map((h) => (
              <th
                key={h}
                style={{
                  textAlign: "left",
                  padding: "8px 12px",
                  fontWeight: 600,
                  color: "var(--color-text-muted)",
                  whiteSpace: "nowrap",
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {nodes.map((n) => (
            <tr key={n.id} style={{ borderBottom: "1px solid var(--color-border)" }}>
              <td style={td}>
                <strong>{n.name}</strong>
              </td>
              <td style={td}>{n.label}</td>
              <td style={td}>{n.provenance.page_idx}</td>
              <td style={td}>
                {n.provenance.bbox ? (
                  <code style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
                    {bboxStr(n.provenance.bbox)}
                  </code>
                ) : (
                  <span style={{ color: "var(--color-danger)", fontSize: 11, fontWeight: 500 }}>
                    无坐标
                  </span>
                )}
              </td>
              <td style={td}>
                <code style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
                  {n.provenance.block_type ?? "—"}
                </code>
              </td>
              <td style={td}>
                <code
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 10,
                    color: "var(--color-text-muted)",
                  }}
                >
                  {JSON.stringify(n.attributes)}
                </code>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function EdgesTable({ edges }: Pick<Props, "edges">) {
  return (
    <div>
      <p
        style={{
          fontSize: 11,
          color: "var(--color-text-muted)",
          margin: "0 0 10px",
          padding: "8px 10px",
          borderRadius: "var(--radius-sm)",
          background: "rgba(154,103,0,0.06)",
          border: "1px dashed var(--color-warning)",
        }}
      >
        关系边协议层无 bbox（见 bridge_pipeline_specification §3.3.1）。下表仅展示 page_idx；坐标需反查端点节点。
      </p>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
              {["Subject", "Predicate", "Object", "Page", "Bbox"].map((h) => (
                <th
                  key={h}
                  style={{
                    textAlign: "left",
                    padding: "8px 12px",
                    fontWeight: 600,
                    color: "var(--color-text-muted)",
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {edges.map((e, i) => (
              <tr key={i} style={{ borderBottom: "1px solid var(--color-border)" }}>
                <td style={td}>{e.subject}</td>
                <td style={td}>
                  <code style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>{e.predicate}</code>
                </td>
                <td style={td}>{e.object}</td>
                <td style={td}>{e.provenance.page_idx}</td>
                <td style={td}>
                  <span style={{ color: "var(--color-danger)", fontSize: 11, fontWeight: 500 }}>
                    协议层无坐标
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const td: React.CSSProperties = { padding: "8px 12px" };
