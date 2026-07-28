import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div style={{ padding: 80, textAlign: "center" }}>
      <h1 style={{ fontSize: 48, fontWeight: 700, color: "var(--color-text-muted)", margin: 0 }}>404</h1>
      <p style={{ fontSize: 16, color: "var(--color-text-muted)", margin: "12px 0 24px" }}>
        Document not found or has been deleted.
      </p>
      <Link to="/" style={{ color: "var(--color-accent)", fontSize: 14 }}>← Back to Documents</Link>
    </div>
  );
}
