import type { Document, KGNode, KGEdge, QAResponse, AppError } from "./types";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

class ApiError extends Error {
  code: string;
  detail: string;
  status: number;
  constructor(e: AppError, status: number) {
    super(e.message);
    this.code = e.error_code;
    this.detail = e.detail;
    this.status = status;
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, init);
  if (!res.ok) {
    const body: AppError = await res.json().catch(() => ({ error_code: "UNKNOWN", message: res.statusText, detail: "" }));
    throw new ApiError(body, res.status);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  health: () => request<{ status: string }>("/api/v1/health"),

  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<Document>("/api/v1/documents", { method: "POST", body: fd });
  },

  listDocuments: () => request<Document[]>("/api/v1/documents"),

  getDocument: (docId: string) => request<Document>(`/api/v1/documents/${docId}`),

  getLog: (docId: string) => request<{ doc_id: string; status: string; log: string[] }>(`/api/v1/documents/${docId}/log`),

  getGraph: (docId: string) => request<{ doc_id: string; nodes: KGNode[]; edges: KGEdge[] }>(`/api/v1/documents/${docId}/graph`),

  askQuestion: (docId: string, question: string, sessionId?: string) =>
    request<QAResponse>(`/api/v1/documents/${docId}/qa`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, session_id: sessionId }),
    }),

  deleteDocument: (docId: string) => request<void>(`/api/v1/documents/${docId}`, { method: "DELETE" }),
};
