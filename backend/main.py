"""FastAPI backend for the multi-modal GraphRAG Q&A system.

Implements the API contract defined in:
  langextract/docs/backend_service_architecture-v1.0.md §7

Run:
    cd backend
    .venv/Scripts/python.exe -m uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import pathlib

from fastapi import FastAPI, File, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import jobs
import qa_agent

app = FastAPI(title="GraphRAG Backend", version="1.0")

# CORS — Vite may be opened as localhost or 127.0.0.1
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Error model (§7.3) ─────────────────────────────────────────────

ERROR_CODES: dict[str, int] = {
    "UNSUPPORTED_FORMAT": 415,
    "INVALID_UPLOAD": 400,
    "MINERU_UPSTREAM_FAILED": 502,
    "MINERU_TIMEOUT": 504,
    "EXTRACTION_FAILED": 502,
    "DOCUMENT_NOT_READY": 409,
    "DOCUMENT_NOT_FOUND": 404,
    "QA_UPSTREAM_FAILED": 502,
}


class AppError(Exception):
    def __init__(self, status_code: int, error_code: str, message: str, detail: str = ""):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.detail = detail


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": exc.error_code, "message": exc.message, "detail": exc.detail},
    )


def _raise(code: str, message: str, detail: str = "") -> None:
    status = ERROR_CODES.get(code, 500)
    raise AppError(status, code, message, detail)


# ── Request models ─────────────────────────────────────────────────


class QuestionRequest(BaseModel):
    question: str
    session_id: str | None = None  # optional; when set, MemorySaver keeps multi-turn state (§6.3)


# ── Helpers ────────────────────────────────────────────────────────


def _require_document(doc_id: str) -> dict:
    doc = jobs.get_document(doc_id)
    if doc is None:
        _raise("DOCUMENT_NOT_FOUND", f"No document with doc_id={doc_id!r}")
    return doc


def _require_ready(doc_id: str) -> dict:
    doc = _require_document(doc_id)
    if doc["status"] != "ready":
        _raise("DOCUMENT_NOT_READY", f"Document is not ready (status={doc['status']!r})")
    return doc


# ── Routes ─────────────────────────────────────────────────────────


@app.get("/api/v1/health")
async def health():
    """§7.2.7 — Health check."""
    return {"status": "ok"}


# Content-Type → expected extensions mapping (§4.1 extension+Content-Type double check)
_CTYPE_MAP: dict[str, set[str]] = {
    "application/pdf": {".pdf"},
    "application/msword": {".doc"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {".docx"},
    "application/vnd.ms-powerpoint": {".ppt"},
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": {".pptx"},
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
    "text/plain": {".txt", ".md"},
    "text/markdown": {".md"},
}


def _check_content_type(ext: str, content_type: str | None) -> None:
    """Validate that the Content-Type header is consistent with the file extension.

    Per spec §4.1: if the Content-Type doesn't match the extension, reject with 400.
    Skips validation when content_type is None or generic (octet-stream).
    """
    if not content_type or content_type == "application/octet-stream":
        return  # browser didn't set a meaningful type — skip
    ctype = content_type.split(";")[0].strip().lower()
    expected = _CTYPE_MAP.get(ctype)
    if expected is not None and ext not in expected:
        _raise("INVALID_UPLOAD", f"Content-Type '{content_type}' does not match file extension '{ext}'")


@app.post("/api/v1/documents", status_code=202)
async def create_document(file: UploadFile = File(...)):
    """§7.2.1 — Upload a document, create an ingestion job."""
    filename = file.filename or ""
    ext = pathlib.Path(filename).suffix.lower()

    if not filename:
        _raise("INVALID_UPLOAD", "No filename provided.")

    # ── Format + Content-Type validation (§4.1, §7.3) ──
    _check_content_type(ext, file.content_type)
    try:
        doc = jobs.create_document(filename)
    except jobs.UnsupportedFormatError as e:
        _raise("UNSUPPORTED_FORMAT", str(e))

    # Save uploaded file
    doc_dir = jobs.doc_storage_dir(doc["doc_id"])
    upload_path = doc_dir / f"source{ext}"
    with upload_path.open("wb") as f:
        f.write(await file.read())

    # Launch background indexing
    jobs.start_indexing_job(doc["doc_id"], upload_path, ext)

    response = {
        "doc_id": doc["doc_id"],
        "status": "queued",
        "source_filename": filename,
        "detected_format": ext,
        "created_at": doc["created_at"],
    }
    if jobs.is_untested_format(ext):
        response["warning"] = (
            f"{ext} is routed through MinerU but has not been verified against a real sample."
        )
    return response


@app.get("/api/v1/documents")
async def list_documents():
    """§7.2.x — List all documents."""
    return jobs.list_documents()


@app.get("/api/v1/documents/{doc_id}")
async def get_document(doc_id: str):
    """§7.2.2 — Get a single document's metadata and status."""
    return _require_document(doc_id)


@app.get("/api/v1/documents/{doc_id}/log")
async def get_document_log(doc_id: str):
    """§7.2.3 — Get the pipeline log for a document."""
    doc = _require_document(doc_id)
    return {"doc_id": doc_id, "status": doc["status"], "log": jobs.get_log(doc_id)}


@app.get("/api/v1/documents/{doc_id}/graph")
async def get_document_graph(
    doc_id: str,
    label: str | None = None,
    page_idx: int | None = None,
    has_bbox: bool | None = None,
):
    """§7.2.4 — Get the knowledge graph (nodes + edges) for a ready document.

    Optional filters (all applied to nodes only, edges returned as-is):
      - label: exact match on node.label
      - page_idx: exact match on node.provenance.page_idx
      - has_bbox: true=only nodes with bbox, false=only nodes without bbox
    """
    _require_ready(doc_id)

    doc_dir = jobs.doc_storage_dir(doc_id)
    nodes: list[dict] = qa_agent.load_jsonl(doc_dir / "kg_nodes.jsonl")
    edges: list[dict] = qa_agent.load_jsonl(doc_dir / "kg_edges.jsonl")

    # Apply node filters (§7.2.4 optional query params)
    if label is not None:
        nodes = [n for n in nodes if n.get("label") == label]
    if page_idx is not None:
        nodes = [n for n in nodes if n.get("provenance", {}).get("page_idx") == page_idx]
    if has_bbox is True:
        nodes = [n for n in nodes if n.get("provenance", {}).get("bbox") is not None]
    elif has_bbox is False:
        nodes = [n for n in nodes if n.get("provenance", {}).get("bbox") is None]

    return {"doc_id": doc_id, "nodes": nodes, "edges": edges}


@app.post("/api/v1/documents/{doc_id}/qa")
async def ask_question(doc_id: str, body: QuestionRequest):
    """§7.2.5 — Ask a question against a ready document's KG."""
    _require_ready(doc_id)

    doc_dir = jobs.doc_storage_dir(doc_id)
    nodes_path = doc_dir / "kg_nodes.jsonl"
    edges_path = doc_dir / "kg_edges.jsonl"

    try:
        result = qa_agent.ask(doc_id, body.question, nodes_path, edges_path, session_id=body.session_id)
    except Exception as exc:
        _raise("QA_UPSTREAM_FAILED", str(exc))

    return {"doc_id": doc_id, **result}


@app.delete("/api/v1/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: str):
    """§7.2.6 — Delete a document and all its storage."""
    _require_document(doc_id)
    jobs.delete_document(doc_id)
    qa_agent.evict_doc(doc_id)


# ── Entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
