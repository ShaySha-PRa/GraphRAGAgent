# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Building a **multi-modal GraphRAG Q&A system** with this pipeline:

```
MinerU (doc parsing) → LangExtract (entity extraction) → Knowledge Graph + Vector Index + Retrieval
```

- `langextract/` — Google's LangExtract v1.6.0 source (LLM-based structured extraction from text)
- `langextract_src/` — LangExtract functional-testing venv (editable install pointing at `langextract/`), MVP test scripts + output
- `mineru-pipeline/` — MinerU cloud API MVP pipeline (PDF → structured JSON/Markdown)
- `langextract/docs/` — Specification docs for all systems (ground truth is `mineru_specification-v1.0.md` and `langextract_specification-v1.0.md`)

## Environment isolation

Each project component (MinerU, LangExtract, ...) runs in its own **uv-managed virtual environment** under `.venv/`. A **PreToolUse hook** automatically redirects bare `python`/`pip` commands to the appropriate venv — you don't need to manually activate or type venv paths. The hook rewrites `python foo.py` → `path/to/.venv/Scripts/python.exe foo.py` transparently.

If you see a "No .venv/ found" denial, the component doesn't have its own venv yet. Create one with `uv venv` inside that directory.

```bash
# The hook rewrites these transparently. But if running manually:
source mineru-pipeline/.venv/Scripts/activate
# or use the venv Python directly:
mineru-pipeline/.venv/Scripts/python.exe pipeline.py
```

## Key Commands

```bash
# MinerU MVP pipeline (cloud parse a PDF) — ALWAYS use the venv Python
mineru-pipeline/.venv/Scripts/python.exe mineru-pipeline/pipeline.py
# or:
cd mineru-pipeline && source .venv/Scripts/activate && python pipeline.py

# Add a new dependency to the MinerU venv
cd mineru-pipeline && python -m uv pip install --python .venv/Scripts/python.exe <package>

# LangExtract functional test (DeepSeek via OpenAI-compatible provider) — ALWAYS run from langextract_src/, not the repo root
cd langextract_src && .venv/Scripts/python.exe test_deepseek_extract.py

# Add a new dependency to the LangExtract test venv
cd langextract_src && python -m uv pip install --python .venv/Scripts/python.exe <package>
```

## Architecture

### MinerU pipeline (`mineru-pipeline/pipeline.py`)

Four-phase script proven end-to-end:

1. **Discover** — glob `test_documents/*.pdf` (case-insensitive, `set()`-deduped for Windows)
2. **Upload** — `POST /api/v4/file-urls/batch` → PUT each PDF to its OSS pre-signed URL (**no custom headers** — Aliyun OSS signature fails on extra headers)
3. **Poll** — `GET /api/v4/extract-results/batch/{batch_id}` with exponential backoff retry (catches `SSLError`, `ConnectionError`, `Timeout`). Results are under `data.extract_result` (singular), NOT `data.results`.
4. **Download** — GET `full_zip_url` → extract to `output/{filename}_{timestamp}/`

Config in `.env`: `MINERU_API_TOKEN`, `MINERU_API_BASE_URL`, optional `MINERU_POLL_INTERVAL` / `MINERU_POLL_MAX_RETRIES`.

### MinerU ZIP output (ground truth, verified)

```
{output_dir}/
├── full.md                              # Markdown (tables as HTML <table>)
├── {task_uuid}_content_list.json        # Flat block list with page_idx; 0-1000 normalized bbox
├── {task_uuid}_content_list_v2.json     # Blocks grouped by page; table HTML under content.html
├── {task_uuid}_model.json               # Pipeline backend format: cls_id, label, score, bbox (pixels), index
├── {task_uuid}_origin.pdf               # Undocumented — original PDF copy
├── layout.json                          # Replaces middle.json from old docs; pdf_info.preproc_blocks → lines → spans
└── images/{content_hash}.jpg            # Table/figure screenshots, hash-named, .jpg only
```

**No `middle.json`, `layout.pdf`, or `span.pdf`** — the official docs are stale on these.

The ground-truth reference is `langextract/docs/mineru_specification-v1.0.md` (diffed against live output on 2026-07-28). The older `MinerU_Specification.md` is pre-verification research only.

### LangExtract (`langextract/`, tested via `langextract_src/`)

Core API: `lx.extract()`. Text-only I/O — no PDF parsing, no multimodal models, no embedding support. Providers: Gemini, OpenAI, Ollama (configurable via `BaseLanguageModel`). Chunking, tokenizer, and extraction pipeline in `langextract/langextract/core/`.

Third-party OpenAI-compatible endpoints (DeepSeek, etc.) are **not** auto-routed — `model_id` pattern matching only recognizes `gpt`/`o1`-`o4`/`gemini`/`ollama`. Must pass `config=ModelConfig(model_id=..., provider="openai", provider_kwargs={"api_key":..., "base_url":...})` explicitly.

Pure in-memory pipeline — no intermediate per-chunk files, unlike MinerU. Only output artifacts are what you explicitly persist: JSONL (`lx.io.save_annotated_documents`) and/or an HTML *fragment* (`lx.visualize` — no `<html>`/`<body>` wrapper).

The ground-truth reference is `langextract/docs/langextract_specification-v1.0.md` (verified against a real DeepSeek call on 2026-07-28). See it for full parameter reference and the cwd/namespace pitfall below.

### Spec docs hierarchy

| Priority | File | Status |
|---|---|---|
| Primary (use this) | `langextract/docs/mineru_specification-v1.0.md` | Live-output-verified |
| Primary (use this) | `langextract/docs/langextract_specification-v1.0.md` | Live-output-verified (DeepSeek MVP) |
| Historical | `langextract/docs/MinerU_Specification.md` | Pre-verification research |
| Historical | `langextract/docs/LANGExtract_Specification.md` | Source-code-backed, not run against a real LLM |

## Hard-learned pitfalls (from live API debugging)

1. **Batch poll key**: Response is `data.extract_result` (singular) — `data.results` silently returns `[]`, looks like a hang with no error.
2. **OSS upload**: `requests.put(url, data=fh)` with NO headers. A `Content-Type` header causes `403 SignatureDoesNotMatch`.
3. **Upload body keys**: `{"files": [{"name": ..., "size": ...}]}` — NOT `file_name`/`file_size`.
4. **`file_urls` is a flat list of strings**, not a list of dicts. Correlate to local files by array index.
5. **Windows glob**: `glob("*.pdf")` + `glob("*.PDF")` returns duplicates on case-insensitive FS → wrap in `set()`.
6. **Windows console**: Emoji crashes with `UnicodeEncodeError` on GBK codepage → `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`. Same fix needed for `lx.io.save_annotated_documents()`'s `✓` progress marker.
7. **Token format**: MinerU expects `sk-...` API tokens, not JWT.
8. **LangExtract cwd/namespace collision**: running any script that does `import langextract` with cwd = repo root silently resolves to an empty PEP 420 namespace package (repo root contains a dir literally named `langextract/`), shadowing the real editable install before its finder is consulted. Symptom: `AttributeError` on any real attribute (`extract`, etc.) despite a correct install. Fix: always run from `langextract_src/` (or any non-colliding cwd).
9. **LangExtract + third-party OpenAI-compatible models**: `model_id` auto-routing won't match non-`gpt` ids (e.g. `deepseek-chat`) — pass `provider="openai"` explicitly via `ModelConfig`, and consider `use_schema_constraints=False` since strict `json_schema` structured-output support isn't guaranteed on compatible endpoints.

## Uncommitted work

`PROJECT_STATE.md`, `mineru-pipeline/` (incl. `.env` with a live MinerU token), and `langextract_src/` (incl. `.env` with a live DeepSeek key) are not yet committed. A root `.gitignore` now excludes `.env`, `.venv/`, `output/`, and `__pycache__/` — verify `git status` doesn't show any `.env` file before committing.

## Next steps (roadmap)

1. ✅ LangExtract MVP verified end-to-end against DeepSeek (`langextract_specification-v1.0.md`)
2. Feed real MinerU `full.md` / `content_list.json` output into LangExtract for entity extraction (only mock text tested so far)
3. Design knowledge graph schema (nodes/edges/properties)
4. Build vector index and retrieval layer
