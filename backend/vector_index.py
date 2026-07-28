"""Vector index for semantic search over document text.

Per backend_service_architecture-v1.0.md §9 Phase 4:
Builds a per-document Chroma collection from the MinerU output's page-level text,
then exposes a search function for the QA agent's vector_search_tool.

Embedding model: all-MiniLM-L6-v2 (384-dim, local, free, no API key needed).
"""

from __future__ import annotations

import json
import pathlib
import re
import threading

import chromadb
from sentence_transformers import SentenceTransformer

# ── Singleton embedding model ──────────────────────────────────────

_model_lock = threading.Lock()
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


# ── Chroma client ──────────────────────────────────────────────────

_client_lock = threading.Lock()
_client: chromadb.PersistentClient | None = None
CHROMA_DIR = pathlib.Path(__file__).resolve().parent / "chroma_data"


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                CHROMA_DIR.mkdir(parents=True, exist_ok=True)
                _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client


# ── Chunking ───────────────────────────────────────────────────────


def _chunk_text(text: str, max_chars: int = 500) -> list[dict]:
    """Split text into overlapping chunks with metadata.

    Returns list of {text, meta: {chunk_idx, char_start, char_end}}.
    """
    # Split by paragraphs first, then merge small ones
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[dict] = []
    current = ""
    start = 0

    for para in paragraphs:
        if len(current) + len(para) < max_chars:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                chunks.append({"text": current, "meta": {"chunk_idx": len(chunks), "char_start": start, "char_end": start + len(current)}})
                start += len(current)
            current = para

    if current:
        chunks.append({"text": current, "meta": {"chunk_idx": len(chunks), "char_start": start, "char_end": start + len(current)}})

    return chunks


# ── Public API ─────────────────────────────────────────────────────


def build_index(doc_id: str, mineru_output_dir: pathlib.Path) -> int:
    """Build a Chroma vector index from a MinerU output directory.

    Reads full.md (preferred) or content_list.json to get document text,
    chunks it, embeds chunks, and stores in a collection named `doc_id`.

    Returns the number of chunks indexed.
    """
    # Try full.md first, fall back to content_list.json
    full_md = mineru_output_dir / "full.md"
    if full_md.is_file():
        text = full_md.read_text(encoding="utf-8", errors="replace")
    else:
        # Scan for content_list.json files
        cl_files = sorted(mineru_output_dir.glob("*_content_list.json"))
        if cl_files:
            blocks = json.loads(cl_files[0].read_text(encoding="utf-8"))
            text = "\n\n".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        else:
            return 0

    if not text.strip():
        return 0

    chunks = _chunk_text(text)
    if not chunks:
        return 0

    model = _get_model()
    client = _get_client()

    # Delete existing collection for this doc (re-index)
    try:
        client.delete_collection(name=doc_id)
    except Exception:
        pass

    collection = client.get_or_create_collection(name=doc_id, metadata={"hnsw:space": "cosine"})

    # Batch embed and insert
    chunk_texts = [c["text"] for c in chunks]
    embeddings = model.encode(chunk_texts, show_progress_bar=False).tolist()
    ids = [f"{doc_id}_{c['meta']['chunk_idx']}" for c in chunks]
    metadatas = [c["meta"] for c in chunks]

    collection.add(ids=ids, embeddings=embeddings, documents=chunk_texts, metadatas=metadatas)
    return len(chunks)


def search(doc_id: str, query: str, top_k: int = 5) -> list[str]:
    """Search the vector index for chunks relevant to the query.

    Returns a list of text snippets (up to top_k).
    """
    client = _get_client()
    try:
        collection = client.get_collection(name=doc_id)
    except Exception:
        return []

    model = _get_model()
    query_embedding = model.encode([query], show_progress_bar=False).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=min(top_k, 10))
    documents = results.get("documents", [[]])[0] if results else []
    return [d for d in documents if d]


def delete_index(doc_id: str) -> None:
    """Remove a document's vector index."""
    client = _get_client()
    try:
        client.delete_collection(name=doc_id)
    except Exception:
        pass
