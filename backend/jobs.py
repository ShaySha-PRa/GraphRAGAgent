"""SQLite-backed document job store + subprocess orchestration.

Runs mineru-pipeline/parse_one.py and langextract_src/build_kg.py as subprocesses
in their own venvs into an isolated backend/storage/{doc_id}/ tree.

Stage machine (per backend_service_architecture-v1.0.md §4.3):
  queued → parsing → extracting → ready
     │         │          │
     └─────────┴──────────┴──→ failed
"""

from __future__ import annotations

import pathlib
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
MINERU_DIR = ROOT / "mineru-pipeline"
LANGEXTRACT_DIR = ROOT / "langextract_src"

MINERU_PY = MINERU_DIR / ".venv" / "Scripts" / "python.exe"
LANGEXTRACT_PY = LANGEXTRACT_DIR / ".venv" / "Scripts" / "python.exe"

STORAGE_DIR = pathlib.Path(__file__).resolve().parent / "storage"
STORAGE_DIR.mkdir(exist_ok=True)
DB_PATH = pathlib.Path(__file__).resolve().parent / "job_store.sqlite"

_db_lock = threading.Lock()

# ── Format routing (§4.1) ──────────────────────────────────────────

MINERU_TESTED = {".pdf"}
MINERU_UNTESTED = {".doc", ".docx", ".ppt", ".pptx", ".png", ".jpg", ".jpeg"}
MINERU_EXTENSIONS = MINERU_TESTED | MINERU_UNTESTED
TEXT_EXTENSIONS = {".txt", ".md"}
ALL_SUPPORTED = MINERU_EXTENSIONS | TEXT_EXTENSIONS

# ── Stage helpers ──────────────────────────────────────────────────

STAGE_TERMINAL = {"ready", "failed"}


def is_terminal(stage: str) -> bool:
    return stage in STAGE_TERMINAL


# ── Database ───────────────────────────────────────────────────────


def _init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                doc_id      TEXT PRIMARY KEY,
                source_filename TEXT NOT NULL,
                detected_format TEXT NOT NULL,
                status      TEXT NOT NULL,
                error       TEXT,
                node_count  INTEGER,
                edge_count  INTEGER,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
            """
        )


_init_db()


def _set_status(doc_id: str, status: str, **kwargs: object) -> None:
    """Atomically update a document row's status and optional fields."""
    pairs = {"status": status, "updated_at": _now()}
    pairs.update(kwargs)
    set_clause = ", ".join(f"{k} = ?" for k in pairs)
    values = list(pairs.values()) + [doc_id]
    with _db_lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(f"UPDATE documents SET {set_clause} WHERE doc_id = ?", values)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def doc_storage_dir(doc_id: str) -> pathlib.Path:
    return STORAGE_DIR / doc_id


# ── Public API ─────────────────────────────────────────────────────


class UnsupportedFormatError(Exception):
    pass


class InvalidUploadError(Exception):
    pass


def create_document(filename: str, content_type: str | None = None) -> dict:
    """Validate format, allocate doc_id + storage dir, insert 'queued' row.

    Returns the document dict (matching §7.2.1 response shape).
    """
    ext = pathlib.Path(filename).suffix.lower()
    if ext not in ALL_SUPPORTED:
        raise UnsupportedFormatError(f"Unsupported file extension: {ext!r}")

    doc_id = uuid.uuid4().hex[:12]
    doc_storage_dir(doc_id).mkdir(parents=True, exist_ok=True)
    created_at = _now()

    row = {
        "doc_id": doc_id,
        "source_filename": filename,
        "detected_format": ext,
        "status": "queued",
        "error": None,
        "node_count": None,
        "edge_count": None,
        "created_at": created_at,
        "updated_at": created_at,
    }
    with _db_lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO documents (doc_id, source_filename, detected_format, status, "
            "error, node_count, edge_count, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (doc_id, filename, ext, "queued", None, None, None, created_at, created_at),
        )
    return row


def get_document(doc_id: str) -> dict | None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
    return dict(row) if row else None


def list_documents() -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def delete_document(doc_id: str) -> None:
    doc_dir = doc_storage_dir(doc_id)
    if doc_dir.is_dir():
        shutil.rmtree(doc_dir)
    # Clean up vector index
    import vector_index
    vector_index.delete_index(doc_id)
    with _db_lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))


def is_untested_format(ext: str) -> bool:
    return ext in MINERU_UNTESTED


def get_log(doc_id: str) -> list[str]:
    """Read the pipeline.log for a document (if it exists)."""
    log_path = doc_storage_dir(doc_id) / "pipeline.log"
    if not log_path.is_file():
        return []
    return log_path.read_text(encoding="utf-8", errors="replace").splitlines()


# ── Subprocess runner ──────────────────────────────────────────────


def _run(cmd: list[str], cwd: pathlib.Path, log_file: pathlib.Path | None = None) -> str:
    """Run a subprocess, streaming stdout line-by-line to an optional log file.

    Returns combined stdout.  Raises RuntimeError on non-zero exit.
    """
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None
    lines: list[str] = []
    for line in proc.stdout:
        lines.append(line.rstrip("\n\r"))
        if log_file is not None:
            with log_file.open("a", encoding="utf-8", errors="replace") as lf:
                lf.write(line)
    rc = proc.wait()
    output = "\n".join(lines)
    if rc != 0:
        raise RuntimeError(output)
    return output


# ── Indexing pipeline ──────────────────────────────────────────────


def run_indexing(doc_id: str, upload_path: pathlib.Path, ext: str) -> None:
    """Background job body.  Mutates document status as it progresses.

    Paths:
      PDF / Office / Image  →  MinerU (parsing) → LangExtract (extracting) → ready
      txt / md              →  text_adapter      → LangExtract (extracting) → ready
    """
    import text_adapter  # local import to avoid circular dependency at module level

    doc_dir = doc_storage_dir(doc_id)
    log_path = doc_dir / "pipeline.log"

    try:
        if ext in TEXT_EXTENSIONS:
            # ── Direct text adapter (skip MinerU) ──
            _set_status(doc_id, "parsing")  # adapter is the "parsing" phase for text
            mineru_output_dir = text_adapter.build_fake_content_list(upload_path, doc_dir, doc_id)
            _append_log(log_path, f"[text_adapter] Fake content_list.json written to {mineru_output_dir}")
        else:
            # ── MinerU path ──
            _set_status(doc_id, "parsing")
            raw_mineru_dir = doc_dir / "mineru_output"
            raw_mineru_dir.mkdir(parents=True, exist_ok=True)

            output = _run(
                [str(MINERU_PY), str(MINERU_DIR / "parse_one.py"), str(upload_path), str(raw_mineru_dir)],
                cwd=MINERU_DIR,
                log_file=log_path,
            )
            result_dir = next(
                (line[len("RESULT_DIR="):].strip() for line in output.splitlines() if line.startswith("RESULT_DIR=")),
                None,
            )
            if not result_dir:
                raise RuntimeError(f"parse_one.py did not report a RESULT_DIR= marker in its stdout.\n\nFull output:\n{output}")
            mineru_output_dir = pathlib.Path(result_dir)

        # ── LangExtract (common to both paths) ──
        _set_status(doc_id, "extracting")
        _run(
            [
                str(LANGEXTRACT_PY),
                str(LANGEXTRACT_DIR / "build_kg.py"),
                str(mineru_output_dir),
                "--output-dir",
                str(doc_dir),
            ],
            cwd=LANGEXTRACT_DIR,
            log_file=log_path,
        )

        # ── Vector index (Phase 4) ──
        import vector_index
        _append_log(log_path, "[vector_index] Building embedding index...")
        n_chunks = vector_index.build_index(doc_id, mineru_output_dir)
        _append_log(log_path, f"[vector_index] Indexed {n_chunks} chunks")

        # ── Count results ──
        nodes_path = doc_dir / "kg_nodes.jsonl"
        edges_path = doc_dir / "kg_edges.jsonl"
        node_count = _count_lines(nodes_path)
        edge_count = _count_lines(edges_path)

        _set_status(doc_id, "ready", node_count=node_count, edge_count=edge_count)

    except Exception as exc:
        _set_status(doc_id, "failed", error=str(exc))
        _append_log(log_path, f"[ERROR] {exc}")


def start_indexing_job(doc_id: str, upload_path: pathlib.Path, ext: str) -> None:
    thread = threading.Thread(target=run_indexing, args=(doc_id, upload_path, ext), daemon=True)
    thread.start()


# ── Helpers ────────────────────────────────────────────────────────


def _append_log(log_path: pathlib.Path, message: str) -> None:
    with log_path.open("a", encoding="utf-8", errors="replace") as f:
        f.write(message + "\n")


def _count_lines(path: pathlib.Path) -> int:
    if not path.is_file():
        return 0
    with path.open("r", encoding="utf-8") as f:
        return sum(1 for _ in f)
