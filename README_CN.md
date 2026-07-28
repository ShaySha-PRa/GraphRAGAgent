# GraphRAG Agent

多模态知识图谱问答系统 — 上传文档 → 抽取知识图谱 → 智能问答。

```
上传 → MinerU（PDF/Office）/ 文本适配器（txt/md）→ LangExtract 抽取 → 知识图谱 + 向量索引 → 问答
```

## 系统架构

```
frontend/     React 18 + Vite + TypeScript（单页应用）
backend/      FastAPI + LangGraph + DeepSeek（REST API）
```

## 快速启动

### 环境要求

- Python 3.12+，已安装 `uv`
- Node.js 18+
- MinerU API Token（PDF 解析用）
- DeepSeek API Key（LLM 抽取 + 问答用）

### 1. 启动后端

```bash
cd backend

# 创建虚拟环境
uv venv
uv pip install --python .venv/Scripts/python.exe fastapi uvicorn python-multipart python-dotenv langgraph langchain-deepseek langchain-core sentence-transformers chromadb

# 配置 API 密钥
echo "DEEPSEEK_API_KEY=sk-..." > .env
echo "DEEPSEEK_BASE_URL=https://api.deepseek.com/v1" >> .env

# 启动
.venv/Scripts/python.exe -m uvicorn main:app --reload
# → http://127.0.0.1:8000
# → Swagger 文档：http://127.0.0.1:8000/docs
```

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
# → http://127.0.0.1:5173
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/documents` | 上传文件（PDF、TXT、MD、DOC、PPT、图片） |
| `GET` | `/api/v1/documents` | 列出所有文档 |
| `GET` | `/api/v1/documents/{id}` | 查看文档状态与元数据 |
| `GET` | `/api/v1/documents/{id}/log` | 查看索引进度日志 |
| `GET` | `/api/v1/documents/{id}/graph` | 获取知识图谱（节点 + 关系边） |
| `POST` | `/api/v1/documents/{id}/qa` | 基于图谱问答 |
| `DELETE` | `/api/v1/documents/{id}` | 删除文档 |
| `GET` | `/api/v1/health` | 健康检查 |

## 功能特性

- **多格式支持**：PDF 通过 MinerU 云 API 解析，纯文本通过内置适配器，Office/图片（未实测）
- **知识图谱**：双通道抽取 — Lane A 确定性表格解析 + Lane B LLM 实体关系抽取
- **结构化引用**：回答附带 page_idx、bbox 和 provenance 来源信息
- **向量检索**：基于 sentence-transformers + Chroma 的语义搜索
- **多轮对话**：通过 LangGraph MemorySaver 实现会话级追问
- **图谱可视化**：vis-network 交互式图谱，实体/表格/合成节点分色编码

## 项目结构

```
├── backend/             FastAPI 后端
│   ├── main.py          路由定义
│   ├── jobs.py          SQLite 任务存储 + 子进程编排
│   ├── qa_agent.py      LangGraph 问答 Agent
│   ├── text_adapter.py  txt/md → MinerU 兼容格式适配器
│   └── vector_index.py  Chroma 向量索引构建
├── frontend/            React 前端
│   └── src/
│       ├── components/  AppShell、Sidebar、GraphView、QAChat 等
│       ├── pages/       DocumentList、DocumentDetail、NotFound
│       └── lib/         API 客户端 + TypeScript 类型定义
├── mineru-pipeline/     MinerU 云 API PDF 解析
├── langextract_src/     LangExtract 知识抽取
└── langextract/         LangExtract 库源码
```
