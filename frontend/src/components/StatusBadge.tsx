import type { Stage } from "../lib/types";

const COLOR: Record<Stage, string> = {
  queued: "var(--color-text-muted)",
  parsing: "var(--color-accent)",
  extracting: "var(--color-accent)",
  ready: "var(--color-success)",
  failed: "var(--color-danger)",
};

export default function StatusBadge({ stage }: { stage: Stage }) {
  const c = COLOR[stage];
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "2px 8px",
        borderRadius: 4,
        fontSize: 11,
        fontWeight: 500,
        color: c,
        background: `${c}1a`,
        fontFamily: "var(--font-sans)",
      }}
    >
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: c, flexShrink: 0 }} />
      {stage}
    </span>
  );
}
