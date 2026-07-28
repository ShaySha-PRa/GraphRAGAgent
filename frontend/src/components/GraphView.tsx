import { useEffect, useRef, useState, useMemo } from "react";
import { Network, type Node, type Edge } from "vis-network";
import "vis-network/styles/vis-network.css";
import type { KGNode, KGEdge } from "../lib/types";
import NodesTable, { EdgesTable } from "./NodesTable";

type ViewMode = "graph" | "nodes-table" | "edges-table";

interface Props {
  nodes: KGNode[];
  edges: KGEdge[];
}

export default function GraphView({ nodes: kgNodes, edges: kgEdges }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const [view, setView] = useState<ViewMode>("graph");

  const [error, setError] = useState<string | null>(null);

  // Build lookup: node name → node id (for matching edges to nodes)
  const nameToId = useMemo(() => {
    const m = new Map<string, string>();
    for (const n of kgNodes) {
      const key = n.name || n.id;
      if (!m.has(key)) m.set(key, n.id);
    }
    return m;
  }, [kgNodes]);

  const nameSet = useMemo(() => new Set(nameToId.keys()), [nameToId]);

  useEffect(() => {
    if (view !== "graph") return;
    const el = containerRef.current;
    if (!el) return;
    if (!kgNodes.length) { setError("No graph data available"); return; }

    setError(null);

    const seen = new Set<string>();
    const nn: Node[] = [];

    for (const n of kgNodes) {
      const vid = n.id;
      if (seen.has(vid)) continue;
      seen.add(vid);
      const isTable = n.provenance?.block_type === "table";
      const displayName = n.name || "(empty)";
      const hasBbox = n.provenance?.bbox != null;
      const pageIdx = n.provenance?.page_idx;
      const blockType = n.provenance?.block_type ?? "—";
      const bboxLabel = hasBbox
        ? `[${(n.provenance.bbox as number[]).map((v) => Math.round(v)).join(", ")}]`
        : "无坐标";
      nn.push({
        id: vid,
        label: `${n.label}\n${displayName.slice(0, 40)}`,
        title: [
          `${n.label}: ${displayName}`,
          `page_idx=${pageIdx ?? "—"}`,
          `bbox=${bboxLabel}`,
          `block_type=${blockType}`,
        ].join("\n"),
        shape: isTable ? "box" : "ellipse",
        color: { background: isTable ? "#f08c00" : "#4dabf7", border: isTable ? "#e07b00" : "#339af0" },
        font: { size: 10, color: "#1f2328" },
        borderWidth: 2,
      });
    }

    const ee: Edge[] = [];
    for (const e of kgEdges) {
      const fromKey = e.subject ?? "";
      const toKey = e.object ?? "";
      let fromId = nameToId.get(fromKey);
      let toId = nameToId.get(toKey);

      if (!fromId) {
        fromId = `synth_${fromKey.slice(0, 20)}`;
        if (!seen.has(fromId)) {
          seen.add(fromId);
          nn.push({
            id: fromId,
            label: `? ${fromKey.slice(0, 20)}`,
            title: `未匹配到图节点\nsubject/object=${fromKey}`,
            shape: "diamond",
            color: { background: "#adb5bd", border: "#868e96" },
            font: { size: 9, color: "#868e96" },
            borderWidth: 1,
          });
        }
      }
      if (!toId) {
        toId = `synth_${toKey.slice(0, 20)}`;
        if (!seen.has(toId)) {
          seen.add(toId);
          nn.push({
            id: toId,
            label: `? ${toKey.slice(0, 20)}`,
            title: `未匹配到图节点\nsubject/object=${toKey}`,
            shape: "diamond",
            color: { background: "#adb5bd", border: "#868e96" },
            font: { size: 9, color: "#868e96" },
            borderWidth: 1,
          });
        }
      }

      ee.push({
        id: `${fromId}__${toId}__${e.predicate}__${ee.length}`,
        from: fromId,
        to: toId,
        label: e.predicate,
        title: [
          `${e.subject} --[${e.predicate}]--> ${e.object}`,
          `page_idx=${e.provenance?.page_idx ?? "—"}`,
          "关系边协议层无 bbox（bridge_pipeline_specification §3.3.1）",
        ].join("\n"),
        font: { size: 9, color: "#656d76" },
        color: "#adb5bd",
        dashes: !nameSet.has(fromKey) || !nameSet.has(toKey),
      });
    }

    try {
      const net = new Network(el, { nodes: nn as never, edges: ee as never }, {
        physics: { solver: "forceAtlas2Based", stabilization: { iterations: 100 } },
        interaction: { hover: true, tooltipDelay: 100 },
      });
      networkRef.current = net;
    } catch (err) {
      setError(`Graph render failed: ${err instanceof Error ? err.message : String(err)}`);
      console.error("vis-network init failed:", err);
    }
    return () => { networkRef.current?.destroy(); networkRef.current = null; };
  }, [kgNodes, kgEdges, view, nameToId, nameSet]);

  return (
    <div>
      <div style={{ display: "flex", gap: 4, marginBottom: 12 }}>
        {(["graph", "nodes-table", "edges-table"] as ViewMode[]).map((v) => (
          <button
            key={v}
            onClick={() => setView(v)}
            style={{
              padding: "6px 14px",
              border: `1px solid ${view === v ? "var(--color-accent)" : "var(--color-border)"}`,
              background: view === v ? "var(--color-card-bg)" : "var(--color-bg)",
              borderRadius: "var(--radius-sm)",
              fontWeight: view === v ? 600 : 400,
              fontSize: 12,
              color: "var(--color-text)",
              cursor: "pointer",
            }}
          >
            {v === "graph" ? "Graph View" : v === "nodes-table" ? "Nodes Table" : "Edges Table"}
          </button>
        ))}
        <span style={{ flex: 1 }} />
        <span style={{ fontSize: 11, color: "var(--color-text-muted)", alignSelf: "center" }}>
          🔵 Entity &nbsp; 🟧 Table &nbsp; ◇ Synthetic (unmatched)
        </span>
      </div>

      {view === "graph" && error && (
        <div style={{ padding: 20, background: "rgba(207,34,46,0.06)", border: "1px solid var(--color-danger)", borderRadius: "var(--radius-sm)", marginBottom: 12 }}>
          <strong style={{ color: "var(--color-danger)" }}>Render Error:</strong> {error}
        </div>
      )}
      {view === "graph" && !error && (
        <div style={{ fontSize: 12, color: "var(--color-text-muted)", marginBottom: 8 }}>
          Rendering {kgNodes.length} nodes, {kgEdges.length} edges
        </div>
      )}
      {view === "graph" && (
        <div
          ref={containerRef}
          style={{ height: 520, border: "1px solid var(--color-border)", borderRadius: "var(--radius-md)", background: "#fff" }}
        />
      )}
      {view === "nodes-table" && <NodesTable nodes={kgNodes} />}
      {view === "edges-table" && <EdgesTable edges={kgEdges} />}
    </div>
  );
}
