export interface Provenance {
  doc_id: string;
  page_idx: number;
  bbox?: number[] | null;
  img_path?: string;
  block_type?: string;
  char_interval?: { start_pos: number; end_pos: number };
}

export interface KGNode {
  id: string;
  label: string;
  name: string;
  attributes: Record<string, string>;
  provenance: Provenance;
}

export interface KGEdge {
  subject: string;
  predicate: string;
  object: string;
  provenance: Provenance;
}

export interface Document {
  doc_id: string;
  source_filename: string;
  detected_format: string;
  status: Stage;
  error: string | null;
  node_count: number | null;
  edge_count: number | null;
  created_at: string;
  updated_at: string;
  warning?: string;
}

export type Stage = "queued" | "parsing" | "extracting" | "ready" | "failed";

export type CitationSourceKind = "graph_node" | "graph_edge" | "table" | "vector_chunk";

export interface Citation {
  source_kind: CitationSourceKind;
  page_idx: number | null;
  bbox: number[] | null;
  node_id: string | null;
  note: string | null;
}

export interface QAResponse {
  doc_id: string;
  answer: string;
  citations: Citation[];
  rewrite_count: number;
}

export interface AppError {
  error_code: string;
  message: string;
  detail: string;
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  citations?: Citation[];
}
