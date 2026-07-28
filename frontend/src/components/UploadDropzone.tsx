import { useRef, useState, type DragEvent, type ChangeEvent } from "react";

const SUPPORTED = [".pdf", ".doc", ".docx", ".ppt", ".pptx", ".png", ".jpg", ".jpeg", ".txt", ".md"];
const KNOWN = new Set(SUPPORTED);

interface Props {
  onUpload: (file: File) => void;
  disabled?: boolean;
}

export default function UploadDropzone({ onUpload, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [warning, setWarning] = useState("");

  const handleFile = (file: File) => {
    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    if (!KNOWN.has(ext)) {
      setWarning(`"${ext}" may not be supported. The server will make the final decision.`);
    } else {
      setWarning("");
    }
    onUpload(file);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  };

  return (
    <div>
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        style={{
          border: `2px dashed ${dragOver ? "var(--color-accent)" : "var(--color-border)"}`,
          borderRadius: "var(--radius-md)",
          padding: "32px 24px",
          textAlign: "center",
          cursor: disabled ? "not-allowed" : "pointer",
          background: dragOver ? "#f0f6ff" : "var(--color-card-bg)",
          opacity: disabled ? 0.5 : 1,
          transition: "border 0.15s",
        }}
      >
        <div
          style={{
            width: 40, height: 40, borderRadius: "50%", background: "var(--color-accent)",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            color: "#fff", fontSize: 20, fontWeight: 700, marginBottom: 12,
          }}
        >
          +
        </div>
        <p style={{ fontSize: 14, color: "var(--color-text-muted)", margin: 0 }}>
          Drag &amp; drop files here, or click to browse
        </p>
        <p style={{ fontSize: 12, color: "var(--color-text-muted)", margin: "4px 0 0" }}>
          PDF, TXT, MD, DOC, PPT, Images — max 50MB
        </p>
      </div>
      {warning && (
        <p style={{ fontSize: 12, color: "var(--color-warning)", margin: "6px 0 0" }}>⚠ {warning}</p>
      )}
      <input ref={inputRef} type="file" hidden onChange={(e: ChangeEvent<HTMLInputElement>) => {
        const f = e.target.files?.[0];
        if (f) handleFile(f);
        e.target.value = "";
      }} />
    </div>
  );
}
