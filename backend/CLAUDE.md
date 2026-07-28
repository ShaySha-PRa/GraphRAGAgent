# CLAUDE.md

## 启动命令

```bash
cd backend
.venv/Scripts/python.exe -m uvicorn main:app --reload
# → http://127.0.0.1:8000
# Swagger UI → http://127.0.0.1:8000/docs
```

## 安装依赖

```bash
cd backend
"/c/Program Files/Python312/python.exe" -m uv pip install --python .venv/Scripts/python.exe <package>
```

## 路径

```
backend/
├── main.py           # FastAPI 路由（8 个端点）
├── jobs.py           # SQLite job store + 子进程编排
├── qa_agent.py       # LangGraph 问答 Agent（按 doc_id 缓存）
├── text_adapter.py   # txt/md → fake content_list.json
├── storage/          # 文档存储（gitignored）
└── job_store.sqlite  # 任务数据库（gitignored）
```

## 依赖

FastAPI + uvicorn + langgraph + langchain-deepseek，独立 `.venv/`（uv 管理）。
API Key 从 `backend/.env` 读取，若不存在则回退到 `langextract_src/.env`。
