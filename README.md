# GraphRAG Agent

A full-stack, multi-modal knowledge-graph RAG (Retrieval-Augmented Generation) system. Upload documents, extract structured knowledge graphs, browse interactive visualizations, and ask natural-language questions backed by KG + vector search.

[中文版](./README_CN.md)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                       Browser (React SPA)                           │
│   Document List → Upload → Poll → Detail (Overview / Graph / Q&A)   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTP REST + JSON
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   backend/ (FastAPI + uvicorn)                       │
│                                                                      │
│  POST   /api/v1/documents           Upload & start indexing          │
│  GET    /api/v1/documents           List all documents               │
│  GET    /api/v1/documents/{id}      Document status & metadata       │
│  GET    /api/v1/documents/{id}/log  Real-time pipeline stdout        │
│  GET    /api/v1/documents/{id}/graph  KG nodes + edges               │
│  POST   /api/v1/documents/{id}/qa   Ask questions (KG + vector)      │
│  DELETE /api/v1/documents/{id}      Delete document & storage        │
│  GET    /api/v1/health              Health check                     │
│                                                                      │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────────────┐   │
│  │ jobs.py     │  │ qa_agent.py  │  │ vector_index.py           │   │
│  │ SQLite job  │  │ LangGraph    │  │ Sentence-Transformers      │   │
│  │ store +     │  │ Agent with   │  │ + Chroma persistent       │   │
│  │ subprocess  │  │ 3 tools:     │  │ vector store              │   │
│  │ orchestration│ │ graph_lookup │  └───────────────────────────┘   │
│  └──────┬──────┘  │ table_lookup │                                   │
│         │         │ vector_search│                                   │
│         │         └──────────────┘                                   │
└─────────┼────────────────────────────────────────────────────────────┘
          │ subprocess (per-doc, isolated venvs)
          ▼
┌──────────────────────┐    ┌───────────────────────────┐
│ mineru-pipeline/     │    │ langextract_src/          │
│ parse_one.py         │    │ build_kg.py               │
│ (PDF/Office/images)  │    │ mineru_adapter.py          │
│ MinerU Cloud API     │    │ LangExtract LLM extraction │
└──────┬───────────────┘    └─────────────┬─────────────┘
       │                                  │
       │ content_list.json                │ --output-dir
       ▼                                  ▼
┌──────────────────────────────────────────────────────────┐
│              backend/storage/{doc_id}/                   │
│  source.pdf  mineru_output/  kg_nodes.jsonl              │
│  kg_edges.jsonl  pipeline.log  chroma_data/              │
└──────────────────────────────────────────────────────────┘
```

## Pipeline

```
Upload → Format Router → Parsing → Extracting → Vector Index → Ready
  │           │              │           │             │
  │     ┌─────┴─────┐   ┌────┴───┐  ┌───┴────┐   ┌────┴─────┐
  │     │ .pdf/.doc  │   │MinerU  │  │Lane A  │   │Chroma    │
  │     │ .ppt/.png  │   │Cloud   │  │tables  │   │persistent │
  │     │ (MinerU)   │   │API     │  │(no LLM)│   │collection │
  │     ├───────────┤   ├────────┤  ├────────┤   │per doc_id │
  │     │ .txt/.md  │   │Text    │  │Lane B  │   │           │
  │     │ (adapter) │   │Adapter │  │LLM     │   │           │
  │     └───────────┘   └────────┘  │entities│   │           │
  │                                 │+ edges │   │           │
  │                                 └────────┘   └───────────┘
```

**Dual-lane knowledge extraction** (from `bridge_pipeline_specification-v1.0.md`):

| Lane | Source | Method | Output | LLM Risk |
|------|--------|--------|--------|----------|
| **A** | `type=="table"` blocks (HTML `<table>`) | Deterministic: parse HTML → `{row_label, metric, value}` triples | `financial_metric` nodes with exact provenance | None — fully deterministic |
| **B** | `type=="text"` blocks (per-page) | LLM: `lx.extract()` via DeepSeek → `char_interval` → `bbox` reverse-lookup | `organization`, `risk_factor`, `date`, `relation` edges | LLM non-determinism; `bbox` may be `null` when alignment fails |

## Features

### Backend

| Feature | Detail |
|---------|--------|
| **Multi-format upload** | PDF (MinerU cloud API, tested), Office documents & images (MinerU, untested — flagged with `warning`), plain text & Markdown (built-in adapter, skips MinerU) |
| **Multi-document isolation** | Each document gets `storage/{doc_id}/` with independent `kg_nodes.jsonl` / `kg_edges.jsonl` — concurrent uploads never collide |
| **SQLite job store** | Survives restarts; zero external dependencies |
| **Graph QA agent** | LangGraph `StateGraph` with `ChatDeepSeek`, 3 tools (`graph_lookup`, `table_lookup`, `vector_search`), rewrite loop (max 2), structured output |
| **Structured citations** | Auto-extracts cited entities from answer text → fills `page_idx` / `bbox` from KG ground truth; edge citations apply endpoint-node fallback |
| **Vector search** | Sentence-Transformers (`all-MiniLM-L6-v2`, 384-dim) + Chroma persistent collection per `doc_id`; chunks document text by paragraph |
| **Multi-turn QA** | LangGraph `MemorySaver` checkpointer; optional `session_id` in request body persists conversation state |
| **Graph API filters** | `?label=`, `?page_idx=`, `?has_bbox=true\|false` on `GET /graph` |
| **Content-Type validation** | Server-side MIME-type vs extension cross-check on upload |
| **Error taxonomy** | 8 error codes (`UNSUPPORTED_FORMAT`/`INVALID_UPLOAD`/`MINERU_UPSTREAM_FAILED`/`MINERU_TIMEOUT`/`EXTRACTION_FAILED`/`DOCUMENT_NOT_READY`/`DOCUMENT_NOT_FOUND`/`QA_UPSTREAM_FAILED`) with unified `{error_code, message, detail}` JSON shape |

### Frontend

| Page | Features |
|------|----------|
| **Document List** (`/`) | Drag-and-drop upload with client-side extension check; status badges (queued/extracting/ready/failed) with auto-polling; untested-format warnings; delete with confirmation |
| **Document Detail — Overview** | 4-step progress stepper; metadata grid; real-time pipeline log terminal (dark theme); error display preserves raw subprocess output |
| **Document Detail — Graph** | `vis-network` interactive graph: blue ellipses = entities, orange boxes = table records, grey diamonds = synthetic placeholders for unmatched edge endpoints; sub-tabs for Nodes Table and Edges Table; `"无坐标"` badge for missing bbox; edge tooltips explain protocol-level bbox absence |
| **Document Detail — Q&A** | Chat interface with Markdown rendering; per-session `session_id` for multi-turn; `CitationsList` component shows `source_kind`, `node_id`, `page_idx`, `bbox`; empty-citations state shown honestly; retry on error |
| **Sidebar** | Dark theme (`#0d1117`); brand header; active navigation highlight |
| **Design** | Developer-tool aesthetic (GitHub/Linear/Vercel-inspired); CSS custom properties design tokens; monospace for technical fields (`doc_id`, `bbox`, `page_idx`); `vis-network` v10 with CSS import |

## API Reference

| Method | Endpoint | Request | Response |
|--------|----------|---------|----------|
| `POST` | `/api/v1/documents` | `multipart/form-data` (`file`) | `202` `{doc_id, status:"queued", source_filename, detected_format, created_at}` + optional `warning` |
| `GET` | `/api/v1/documents` | — | `200` `[{doc_id, status, source_filename, detected_format, node_count, edge_count, error, created_at, updated_at}]` |
| `GET` | `/api/v1/documents/{id}` | — | `200` (single document object) |
| `GET` | `/api/v1/documents/{id}/log` | — | `200` `{doc_id, status, log: [string]}` |
| `GET` | `/api/v1/documents/{id}/graph` | `?label=&page_idx=&has_bbox=` | `200` `{doc_id, nodes: [KGNode], edges: [KGEdge]}` |
| `POST` | `/api/v1/documents/{id}/qa` | `{question, session_id?}` | `200` `{doc_id, answer, citations: [Citation], rewrite_count}` |
| `DELETE` | `/api/v1/documents/{id}` | — | `204` |
| `GET` | `/api/v1/health` | — | `200` `{status:"ok"}` |

**Error response** (all non-2xx): `{error_code: string, message: string, detail: string}`

**KG Schema** (from `bridge_pipeline_specification-v1.0.md`):

```
KGNode   {id, label, name, attributes, provenance: {doc_id, page_idx, bbox?, img_path?, block_type?, char_interval?}}
KGEdge   {subject, predicate, object, provenance: {doc_id, page_idx}}  // edges never have bbox
Citation {source_kind, page_idx?, bbox?, node_id?, note?}
```

- `bbox` is normalized 0–1000; absent when Lane B alignment fails (expected, not a bug)
- `block_type=="table"` marks Lane A deterministic nodes (always have bbox)
- `label` and `predicate` are arbitrary LLM-generated strings (no enum whitelist)
- Edge `subject`/`object` may not match any node `name` → rendered as synthetic dashed nodes in the graph view

## Project Structure

```
├── backend/
│   ├── main.py              FastAPI routes (8 endpoints)
│   ├── jobs.py              SQLite job store + subprocess orchestration
│   ├── qa_agent.py          LangGraph QA agent (3 tools, citations, multi-turn)
│   ├── text_adapter.py      txt/md → fake content_list.json (skips MinerU)
│   └── vector_index.py      Chroma index builder + query (sentence-transformers)
├── frontend/
│   └── src/
│       ├── components/      AppShell, Sidebar, StatusBadge, UploadDropzone,
│       │                    DocumentTable, GraphView, NodesTable, QAChat
│       ├── pages/           DocumentListPage, DocumentDetailPage, NotFoundPage
│       └── lib/             api.ts (typed fetch), types.ts (Document, KGNode, …)
├── mineru-pipeline/         MinerU cloud API PDF parsing
│   ├── pipeline.py          Batch upload/poll/download phases
│   └── parse_one.py         Single-file wrapper used by backend
├── langextract_src/         Bridge pipeline
│   ├── build_kg.py          CLI entry (accepts --output-dir)
│   └── mineru_adapter.py    content_list.json → Lane A/B extraction
└── langextract/             Google LangExtract v1.6.0 library source
```

## Quick Start

**Prerequisites**: Python 3.12+, Node.js 18+, MinerU API token, DeepSeek API key.

### Backend

```bash
cd backend
uv venv
uv pip install --python .venv/Scripts/python.exe \
  fastapi uvicorn python-multipart python-dotenv \
  langgraph langchain-deepseek langchain-core \
  sentence-transformers chromadb

# Create .env (gitignored)
echo "DEEPSEEK_API_KEY=sk-..." > .env
echo "DEEPSEEK_BASE_URL=https://api.deepseek.com/v1" >> .env

.venv/Scripts/python.exe -m uvicorn main:app --reload
# → http://127.0.0.1:8000/docs
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# → http://127.0.0.1:5173
```

Open the browser to upload a document, watch the pipeline progress, browse the knowledge graph, and ask questions.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, uvicorn, LangGraph, LangChain, DeepSeek API, SQLite |
| Embedding | Sentence-Transformers (`all-MiniLM-L6-v2`, 384-dim) |
| Vector DB | Chroma (persistent, per-doc collection) |
| PDF Parsing | MinerU Cloud API v4 |
| Entity Extraction | Google LangExtract v1.6.0 |
| Frontend | React 18, Vite, TypeScript, vis-network v10, react-markdown |
| Package Mgmt | uv (Python), npm (Node) |

## Known Limitations

- **Citations may be empty**: The QA agent auto-extracts entity names from the answer; if no graph entities are mentioned, `citations: []`
- **Edges never have bbox**: Protocol-level limitation (see `bridge_pipeline_specification-v1.0.md` §3.3.1); edge citations use endpoint-node fallback
- **Office/image formats untested**: Code path exists but not verified against real `.docx`/`.pptx`/`.png` samples
- **No entity deduplication**: Same real-world entity appearing in both Lane A (table) and Lane B (text) produces separate KG nodes
- **No authentication / multi-tenancy**
- **Responsive layout**: Desktop-optimized; mobile sidebar drawer not yet implemented
