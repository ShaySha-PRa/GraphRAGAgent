# GraphRAG Agent

Multi-modal GraphRAG Q&A system — upload documents, extract knowledge graphs, ask questions.

```
Upload → MinerU (PDF/Office) / Text Adapter (txt/md) → LangExtract → KG + Vector Index → Q&A
```

## Architecture

```
frontend/     React 18 + Vite + TypeScript (SPA)
backend/      FastAPI + LangGraph + DeepSeek (REST API)
```

## Quick Start

### Prerequisites

- Python 3.12+ with `uv`
- Node.js 18+
- MinerU API token (for PDF parsing)
- DeepSeek API key (for LLM extraction + Q&A)

### 1. Backend

```bash
cd backend

# Create virtual environment
uv venv
uv pip install --python .venv/Scripts/python.exe fastapi uvicorn python-multipart python-dotenv langgraph langchain-deepseek langchain-core sentence-transformers chromadb

# Create .env with API keys
echo "DEEPSEEK_API_KEY=sk-..." > .env
echo "DEEPSEEK_BASE_URL=https://api.deepseek.com/v1" >> .env

# Start
.venv/Scripts/python.exe -m uvicorn main:app --reload
# → http://127.0.0.1:8000
# → Swagger UI: http://127.0.0.1:8000/docs
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
# → http://127.0.0.1:5173
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/documents` | Upload a file (PDF, TXT, MD, DOC, PPT, images) |
| `GET` | `/api/v1/documents` | List all documents |
| `GET` | `/api/v1/documents/{id}` | Get document status & metadata |
| `GET` | `/api/v1/documents/{id}/log` | Pipeline stdout log |
| `GET` | `/api/v1/documents/{id}/graph` | Knowledge graph (nodes + edges) |
| `POST` | `/api/v1/documents/{id}/qa` | Ask a question |
| `DELETE` | `/api/v1/documents/{id}` | Delete document |
| `GET` | `/api/v1/health` | Health check |

## Features

- **Multi-format**: PDF via MinerU cloud API, plain text via built-in adapter, Office/images (untested)
- **Knowledge Graph**: Dual-lane extraction — deterministic table parsing (Lane A) + LLM entity extraction (Lane B)
- **Structured Citations**: Answers include page_idx, bbox, and provenance references
- **Vector Search**: Semantic search over raw document text (sentence-transformers + Chroma)
- **Multi-turn Q&A**: Session-aware conversation via LangGraph MemorySaver
- **Graph Visualization**: vis-network interactive graph with entity/table/synthetic node encoding

## Project Structure

```
├── backend/             FastAPI server
│   ├── main.py          Routes
│   ├── jobs.py          SQLite job store + subprocess orchestration
│   ├── qa_agent.py      LangGraph QA agent
│   ├── text_adapter.py  txt/md → MinerU-compatible format
│   └── vector_index.py  Chroma vector index builder
├── frontend/            React SPA
│   └── src/
│       ├── components/  AppShell, Sidebar, GraphView, QAChat, etc.
│       ├── pages/       DocumentList, DocumentDetail, NotFound
│       └── lib/         API client + TypeScript types
├── mineru-pipeline/     PDF parsing via MinerU cloud API
├── langextract_src/     LangExtract knowledge extraction
└── langextract/         LangExtract library source
```
