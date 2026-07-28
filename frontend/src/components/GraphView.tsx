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

function nodeTypeKey(n: KGNode): string {
  const base = n.label?.trim() || "(unknown)";
  return n.provenance?.block_type === "table" ? `📊 ${base}` : base;
}

function isTableNode(n: KGNode): boolean {
  return n.provenance?.block_type === "table";
}

function labelColor(label: string, isTable: boolean): string {
  if (isTable) {
    // Tables get warm orange tones — same base hue, varied saturation
    let hash = 0;
    for (let i = 0; i < label.length; i++) hash = (hash * 31 + label.charCodeAt(i)) | 0;
    const sat = 60 + ((hash % 30) + 30);
    const lit = 48 + ((hash >> 8) % 15);
    return `hsl(24, ${sat}%, ${lit}%)`;
  }
  let hash = 0;
  for (let i = 0; i < label.length; i++) hash = (hash * 31 + label.charCodeAt(i)) | 0;
  const hue = ((hash % 360) + 360) % 360;
  return `hsl(${hue}, 65%, 58%)`;
}

function labelBorder(label: string, isTable: boolean): string {
  if (isTable) {
    let hash = 0;
    for (let i = 0; i < label.length; i++) hash = (hash * 31 + label.charCodeAt(i)) | 0;
    const sat = 60 + ((hash % 30) + 30);
    return `hsl(24, ${sat}%, 38%)`;
  }
  let hash = 0;
  for (let i = 0; i < label.length; i++) hash = (hash * 31 + label.charCodeAt(i)) | 0;
  const hue = ((hash % 360) + 360) % 360;
  return `hsl(${hue}, 65%, 46%)`;
}

export default function GraphView({ nodes: kgNodes, edges: kgEdges }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const [view, setView] = useState<ViewMode>("graph");
  const [error, setError] = useState<string | null>(null);

  const labelCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const n of kgNodes) {
      const k = nodeTypeKey(n);
      m.set(k, (m.get(k) ?? 0) + 1);
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  }, [kgNodes]);

  const allLabels = useMemo(() => labelCounts.map(([l]) => l), [labelCounts]);

  const [selectedLabels, setSelectedLabels] = useState<Set<string>>(new Set());
  const labelsInitialized = useRef(false);

  // Default: all types selected; re-seed when document graph changes
  useEffect(() => {
    labelsInitialized.current = false;
  }, [kgNodes]);

  useEffect(() => {
    if (labelsInitialized.current || allLabels.length === 0) return;
    setSelectedLabels(new Set(allLabels));
    labelsInitialized.current = true;
  }, [allLabels]);

  const filteredNodes = useMemo(
    () => kgNodes.filter((n) => selectedLabels.has(nodeTypeKey(n))),
    [kgNodes, selectedLabels],
  );

  const visibleNames = useMemo(() => {
    const s = new Set<string>();
    for (const n of filteredNodes) {
      if (n.name) s.add(n.name);
    }
    return s;
  }, [filteredNodes]);

  // Drop edges that touch a known node currently filtered out; keep if at least one end is visible
  const filteredEdges = useMemo(() => {
    const allNames = new Set(kgNodes.map((n) => n.name).filter(Boolean));
    return kgEdges.filter((e) => {
      const subj = e.subject ?? "";
      const obj = e.object ?? "";
      const subjKnown = allNames.has(subj);
      const objKnown = allNames.has(obj);
      if (subjKnown && !visibleNames.has(subj)) return false;
      if (objKnown && !visibleNames.has(obj)) return false;
      return visibleNames.has(subj) || visibleNames.has(obj);
    });
  }, [kgEdges, kgNodes, visibleNames]);

  const nameToId = useMemo(() => {
    const m = new Map<string, string>();
    for (const n of filteredNodes) {
      const key = n.name || n.id;
      if (!m.has(key)) m.set(key, n.id);
    }
    return m;
  }, [filteredNodes]);

  const nameSet = useMemo(() => new Set(nameToId.keys()), [nameToId]);

  const toggleLabel = (label: string) => {
    setSelectedLabels((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  };

  const selectAll = () => setSelectedLabels(new Set(allLabels));
  const selectNone = () => setSelectedLabels(new Set());

  useEffect(() => {
    if (view !== "graph") return;
    const el = containerRef.current;
    if (!el) return;
    if (!filteredNodes.length) {
      setError(selectedLabels.size === 0 ? "No entity types selected" : "No graph data available");
      return;
    }

    setError(null);

    const seen = new Set<string>();
    const nn: Node[] = [];

    for (const n of filteredNodes) {
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
      const it = isTableNode(n);
      const lc = labelColor(n.label, it);
      const lb = labelBorder(n.label, it);
      nn.push({
        id: vid,
        label: `${n.label}\n${displayName.slice(0, 40)}`,
        title: [
          `${n.label}: ${displayName}`,
          `page_idx=${pageIdx ?? "—"}`,
          `bbox=${bboxLabel}`,
          `block_type=${blockType}`,
        ].join("\n"),
        shape: it ? "box" : "ellipse",
        color: { background: lc, border: lb },
        font: { size: 10, color: "#1f2328" },
        borderWidth: 2,
      });
    }

    const ee: Edge[] = [];
    for (const e of filteredEdges) {
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
    return () => {
      networkRef.current?.destroy();
      networkRef.current = null;
    };
  }, [filteredNodes, filteredEdges, view, nameToId, nameSet, selectedLabels.size]);

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
          ◇ Synthetic &nbsp; | &nbsp;
          <span style={{ display: "inline-flex", gap: 5, flexWrap: "wrap" }}>
            {allLabels.slice(0, 8).map((l) => {
              const isT = l.startsWith("📊 ");
              return (
                <span key={l} style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
                  <span style={{ width: 8, height: 8, borderRadius: "50%", background: labelColor(l, isT), display: "inline-block", flexShrink: 0 }} />
                  {l}
                </span>
              );
            })}
            {allLabels.length > 8 && <span>+{allLabels.length - 8}</span>}
          </span>
        </span>
      </div>

      {labelCounts.length > 0 && (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
            alignItems: "center",
            marginBottom: 12,
            padding: "10px 12px",
            borderRadius: "var(--radius-sm)",
            background: "var(--color-bg)",
            border: "1px solid var(--color-border)",
          }}
        >
          <span style={{ fontSize: 12, fontWeight: 600, color: "var(--color-text-muted)", marginRight: 4 }}>
            Entity types
          </span>
          <button type="button" onClick={selectAll} style={linkBtn}>
            All
          </button>
          <button type="button" onClick={selectNone} style={linkBtn}>
            None
          </button>
          <span style={{ width: 1, height: 14, background: "var(--color-border)", margin: "0 4px" }} />
          {labelCounts.map(([label, count]) => {
            const on = selectedLabels.has(label);
            const isTable = label.startsWith("📊 ");
            const lc = labelColor(label, isTable);
            return (
              <label
                key={label}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "4px 10px",
                  borderRadius: "var(--radius-sm)",
                  border: `1px solid ${on ? "var(--color-accent)" : "var(--color-border)"}`,
                  background: on ? "rgba(47,129,247,0.08)" : "var(--color-card-bg)",
                  fontSize: 12,
                  cursor: "pointer",
                  userSelect: "none",
                }}
              >
                <span style={{ width: 10, height: 10, borderRadius: "50%", background: lc, display: "inline-block", flexShrink: 0 }} />
                <input
                  type="checkbox"
                  checked={on}
                  onChange={() => toggleLabel(label)}
                  style={{ margin: 0, accentColor: "var(--color-accent)" }}
                />
                <code style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>{label}</code>
                <span style={{ color: "var(--color-text-muted)", fontSize: 11 }}>{count}</span>
              </label>
            );
          })}
        </div>
      )}

      {view === "graph" && error && (
        <div
          style={{
            padding: 20,
            background: "rgba(207,34,46,0.06)",
            border: "1px solid var(--color-danger)",
            borderRadius: "var(--radius-sm)",
            marginBottom: 12,
          }}
        >
          <strong style={{ color: "var(--color-danger)" }}>Render Error:</strong> {error}
        </div>
      )}
      {view === "graph" && !error && (
        <div style={{ fontSize: 12, color: "var(--color-text-muted)", marginBottom: 8 }}>
          Showing {filteredNodes.length}/{kgNodes.length} nodes, {filteredEdges.length}/{kgEdges.length} edges
        </div>
      )}
      {view === "graph" && (
        <div
          ref={containerRef}
          style={{
            height: 520,
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            background: "#fff",
          }}
        />
      )}
      {view === "nodes-table" && <NodesTable nodes={filteredNodes} />}
      {view === "edges-table" && <EdgesTable edges={filteredEdges} />}
    </div>
  );
}

const linkBtn: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "var(--color-accent)",
  fontSize: 12,
  cursor: "pointer",
  padding: "2px 4px",
  fontWeight: 500,
};
