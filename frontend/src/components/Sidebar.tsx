import { useNavigate, useLocation } from "react-router-dom";

export default function Sidebar() {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  return (
    <aside
      style={{
        width: 240,
        minWidth: 240,
        height: "100%",
        background: "var(--color-sidebar-bg)",
        display: "flex",
        flexDirection: "column",
        padding: "24px 0",
        gap: 24,
      }}
    >
      <div
        onClick={() => navigate("/")}
        style={{ display: "flex", alignItems: "center", gap: 10, padding: "0 24px", cursor: "pointer" }}
      >
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: 6,
            background: "var(--color-accent)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#fff",
            fontSize: 16,
            fontWeight: 700,
          }}
        >
          G
        </div>
        <span style={{ fontSize: 16, fontWeight: 600, color: "var(--color-sidebar-text)" }}>GraphRAG</span>
      </div>

      <div style={{ height: 1, background: "#21262d", margin: "0 24px" }} />

      <nav style={{ display: "flex", flexDirection: "column", gap: 2, padding: "0 12px" }}>
        {[
          { label: "Documents", path: "/" },
        ].map((item) => {
          const active = pathname === item.path || pathname.startsWith("/documents/");
          return (
            <div
              key={item.path}
              onClick={() => navigate(item.path)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "8px 12px",
                borderRadius: 6,
                cursor: "pointer",
                fontSize: 14,
                fontWeight: 500,
                color: active ? "#fff" : "var(--color-sidebar-text-muted)",
                background: active ? "rgba(47,129,247,0.15)" : "transparent",
              }}
            >
              📄 {item.label}
            </div>
          );
        })}
      </nav>

      <div style={{ flex: 1 }} />
      <div style={{ padding: "0 24px", display: "flex", flexDirection: "column", gap: 6 }}>
        <div style={{ fontSize: 10, color: "var(--color-sidebar-text-muted)", fontWeight: 500 }}>
          v1.0 — citations + multi-turn
        </div>
        <div
          style={{
            fontSize: 10,
            padding: "2px 6px",
            borderRadius: 3,
            background: "rgba(154,103,0,0.15)",
            color: "var(--color-warning)",
            fontWeight: 500,
            display: "inline-block",
            width: "fit-content",
          }}
        >
          Responsive layout: not done
        </div>
      </div>
    </aside>
  );
}
