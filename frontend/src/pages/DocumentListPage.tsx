import { useState, useEffect, useCallback } from "react";
import UploadDropzone from "../components/UploadDropzone";
import DocumentTable from "../components/DocumentTable";
import { api } from "../lib/api";
import type { Document } from "../lib/types";

export default function DocumentListPage() {
  const [docs, setDocs] = useState<Document[]>([]);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try { setDocs(await api.listDocuments()); } catch { /* ignore */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  // Poll in-progress docs
  useEffect(() => {
    const pending = docs.filter((d) => d.status !== "ready" && d.status !== "failed");
    if (pending.length === 0) return;
    const t = setInterval(refresh, 2500);
    return () => clearInterval(t);
  }, [docs, refresh]);

  const handleUpload = async (file: File) => {
    setError("");
    try {
      await api.upload(file);
      await refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Upload failed");
    }
  };

  const handleDelete = async (docId: string) => {
    if (!confirm("Delete this document and all its data?")) return;
    try {
      await api.deleteDocument(docId);
      setDocs((prev) => prev.filter((d) => d.doc_id !== docId));
    } catch { /* ignore */ }
  };

  return (
    <div style={{ padding: 40, maxWidth: 1100 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 600, margin: 0 }}>Documents</h1>
          <p style={{ fontSize: 14, color: "var(--color-text-muted)", margin: "4px 0 0" }}>{docs.length} document{docs.length !== 1 ? "s" : ""}</p>
        </div>
      </div>

      {error && (
        <div style={{ padding: "10px 16px", marginBottom: 16, borderRadius: 6, background: "rgba(207,34,46,0.08)", border: "1px solid var(--color-danger)", fontSize: 13, color: "var(--color-danger)" }}>
          {error}
        </div>
      )}

      <div style={{ marginBottom: 24 }}>
        <UploadDropzone onUpload={handleUpload} />
      </div>

      <DocumentTable docs={docs} onDelete={handleDelete} />
    </div>
  );
}
