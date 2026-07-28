# GraphRAG Agent

全栈多模态知识图谱 RAG（检索增强生成）系统。上传文档 → 抽取结构化知识图谱 → 交互式图谱浏览 → 基于 KG + 向量检索的自然语言问答。

[English](./README.md)

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    浏览器（React 单页应用）                           │
│  文档列表 → 上传 → 轮询进度 → 详情页（总览 / 图谱 / 问答）            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTP REST + JSON
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   backend/（FastAPI + uvicorn）                       │
│                                                                      │
│  POST   /api/v1/documents           上传文件，启动后台索引            │
│  GET    /api/v1/documents           列出所有文档                      │
│  GET    /api/v1/documents/{id}      文档状态与元数据                   │
│  GET    /api/v1/documents/{id}/log  实时流水线 stdout 日志             │
│  GET    /api/v1/documents/{id}/graph  知识图谱（节点 + 边）            │
│  POST   /api/v1/documents/{id}/qa   基于 KG + 向量检索问答             │
│  DELETE /api/v1/documents/{id}      删除文档及存储                     │
│  GET    /api/v1/health              健康检查                          │
│                                                                      │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────────────┐    │
│  │ jobs.py     │  │ qa_agent.py  │  │ vector_index.py           │    │
│  │ SQLite 任务 │  │ LangGraph    │  │ Sentence-Transformers      │    │
│  │ 存储 + 子进 │  │ Agent，3 个  │  │ + Chroma 持久化向量库       │    │
│  │ 程编排      │  │ 工具：       │  └───────────────────────────┘    │
│  └──────┬──────┘  │ graph_lookup │                                    │
│         │         │ table_lookup │                                    │
│         │         │ vector_search│                                    │
│         │         └──────────────┘                                    │
└─────────┼────────────────────────────────────────────────────────────┘
          │ 子进程（每文档独立 venv）
          ▼
┌──────────────────────┐    ┌───────────────────────────┐
│ mineru-pipeline/     │    │ langextract_src/          │
│ parse_one.py         │    │ build_kg.py               │
│ MinerU 云 API        │    │ mineru_adapter.py          │
│ PDF/Office/图片解析   │    │ LangExtract LLM 实体抽取   │
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

## 处理流程

```
上传 → 格式路由 → 解析 → 抽取 → 向量索引 → 就绪
  │       │         │       │        │
  │  ┌────┴────┐  ┌─┴───┐ ┌─┴───┐ ┌──┴──────┐
  │  │.pdf/.doc│  │MinerU│ │Lane A│ │Chroma   │
  │  │.ppt/.png│  │云API │ │表格  │ │持久化   │
  │  │(MinerU) │  │      │ │(无LLM)│ │集合     │
  │  ├─────────┤  ├──────┤ ├──────┤ │per doc  │
  │  │.txt/.md │  │文本  │ │Lane B│ │         │
  │  │(适配器) │  │适配器│ │LLM   │ │         │
  │  └─────────┘  └──────┘ │实体  │ │         │
  │                        │+关系 │ │         │
  │                        └──────┘ └─────────┘
```

**双通道知识抽取**（来源：`bridge_pipeline_specification-v1.0.md`）：

| 通道 | 来源 | 方法 | 产出 | LLM 风险 |
|------|------|------|------|----------|
| **A** | `type=="table"` 块（HTML 表格） | 确定性：解析 HTML → `{row_label, metric, value}` 三元组 | `financial_metric` 节点，带精确 provenance | 无 — 完全确定性 |
| **B** | `type=="text"` 块（按页拼接） | LLM：`lx.extract()` 通过 DeepSeek → `char_interval` → `bbox` 反查 | `organization`、`risk_factor`、`date`、`relation` 边 | LLM 非确定性；对齐失败时 `bbox` 可为 `null` |

## 功能特性

### 后端

| 功能 | 说明 |
|------|------|
| **多格式上传** | PDF（MinerU 云 API，已实测）、Office 文档与图片（MinerU，未实测 — 上传时返回 `warning`）、纯文本与 Markdown（内置适配器，跳过 MinerU） |
| **多文档隔离** | 每文档独立 `storage/{doc_id}/` 存储 `kg_nodes.jsonl` / `kg_edges.jsonl` — 并发上传不会互相覆盖 |
| **SQLite 任务存储** | 进程重启不丢数据；零外部依赖 |
| **图谱问答 Agent** | LangGraph `StateGraph` + `ChatDeepSeek`，3 个工具（`graph_lookup`、`table_lookup`、`vector_search`），自动改写循环（最多 2 次），结构化输出 |
| **结构化引用** | 从回答文本中自动提取实体名 → 从 KG 数据回填 `page_idx` / `bbox`；关系边引用使用端点节点坐标回退 |
| **向量检索** | Sentence-Transformers（`all-MiniLM-L6-v2`，384 维）+ Chroma 按 `doc_id` 创建持久化集合；按段落切分文档文本 |
| **多轮对话** | LangGraph `MemorySaver` 检查点；请求体中可选 `session_id` 维持会话状态 |
| **图谱接口过滤** | `GET /graph` 支持 `?label=`、`?page_idx=`、`?has_bbox=true\|false` |
| **上传校验** | 服务端 MIME 类型与扩展名交叉验证 |
| **统一错误格式** | 8 种 `error_code`（`UNSUPPORTED_FORMAT` / `INVALID_UPLOAD` / `MINERU_UPSTREAM_FAILED` / `MINERU_TIMEOUT` / `EXTRACTION_FAILED` / `DOCUMENT_NOT_READY` / `DOCUMENT_NOT_FOUND` / `QA_UPSTREAM_FAILED`），统一 `{error_code, message, detail}` JSON 响应 |

### 前端

| 页面 | 功能 |
|------|------|
| **文档列表**（`/`） | 拖拽上传 + 客户端扩展名预检；状态徽标（queued→extracting→ready→failed）自动轮询；未测格式警告；删除确认 |
| **文档详情 — 总览** | 4 步进度条；元数据网格；实时流水线日志终端（深色主题）；失败时保留原始子进程错误输出 |
| **文档详情 — 图谱** | `vis-network` 交互式图谱：蓝色椭圆 = 实体，橙色方框 = 表格记录，灰色菱形 = 未匹配边的合成占位节点；节点表/边表切换；缺失坐标显示"无坐标"徽标；边 tooltip 说明协议层无 bbox |
| **文档详情 — 问答** | 对话界面 + Markdown 渲染；每会话 `session_id` 支持多轮追问；`CitationsList` 展示 `source_kind`、`node_id`、`page_idx`、`bbox`；无引用时诚实展示空状态；出错可重试 |
| **侧边栏** | 深色主题（`#0d1117`）；品牌标识；当前页高亮导航 |
| **设计风格** | 开发者工具审美（GitHub/Linear/Vercel 风格）；CSS 变量 Design Token；技术字段（`doc_id`、`bbox`、`page_idx`）使用等宽字体；vis-network v10 带 CSS 导入 |

## API 参考

| 方法 | 端点 | 请求 | 响应 |
|------|------|------|------|
| `POST` | `/api/v1/documents` | `multipart/form-data`（`file`） | `202` `{doc_id, status:"queued", source_filename, detected_format, created_at}` + 可选 `warning` |
| `GET` | `/api/v1/documents` | — | `200` `[{doc_id, status, source_filename, detected_format, node_count, edge_count, error, created_at, updated_at}]` |
| `GET` | `/api/v1/documents/{id}` | — | `200`（单文档对象） |
| `GET` | `/api/v1/documents/{id}/log` | — | `200` `{doc_id, status, log: [string]}` |
| `GET` | `/api/v1/documents/{id}/graph` | `?label=&page_idx=&has_bbox=` | `200` `{doc_id, nodes: [KGNode], edges: [KGEdge]}` |
| `POST` | `/api/v1/documents/{id}/qa` | `{question, session_id?}` | `200` `{doc_id, answer, citations: [Citation], rewrite_count}` |
| `DELETE` | `/api/v1/documents/{id}` | — | `204` |
| `GET` | `/api/v1/health` | — | `200` `{status:"ok"}` |

**错误响应**（所有非 2xx）：`{error_code: string, message: string, detail: string}`

**知识图谱数据结构**（来源：`bridge_pipeline_specification-v1.0.md`）：

```
KGNode   {id, label, name, attributes, provenance: {doc_id, page_idx, bbox?, img_path?, block_type?, char_interval?}}
KGEdge   {subject, predicate, object, provenance: {doc_id, page_idx}}  // 边永远无 bbox
Citation {source_kind, page_idx?, bbox?, node_id?, note?}
```

- `bbox` 归一化 0–1000；Lane B 对齐失败时缺失（属预期行为，非 bug）
- `block_type=="table"` 标记 Lane A 确定性节点（始终有 bbox）
- `label` 和 `predicate` 为 LLM 自由生成的字符串（无枚举白名单）
- 边的 `subject`/`object` 可能在节点中找不到 → 图谱中以灰色虚线合成节点展示

## 项目结构

```
├── backend/
│   ├── main.py              FastAPI 路由（8 个端点）
│   ├── jobs.py              SQLite 任务存储 + 子进程编排
│   ├── qa_agent.py          LangGraph 问答 Agent（3 工具、引用、多轮）
│   ├── text_adapter.py      txt/md → 模拟 content_list.json（跳过 MinerU）
│   └── vector_index.py      Chroma 索引构建 + 查询（sentence-transformers）
├── frontend/
│   └── src/
│       ├── components/      AppShell、Sidebar、StatusBadge、UploadDropzone、
│       │                    DocumentTable、GraphView、NodesTable、QAChat
│       ├── pages/           DocumentListPage、DocumentDetailPage、NotFoundPage
│       └── lib/             api.ts（类型化 fetch）、types.ts（Document、KGNode 等）
├── mineru-pipeline/         MinerU 云 API PDF 解析
│   ├── pipeline.py          批量上传/轮询/下载
│   └── parse_one.py         供 backend 调用的单文件封装
├── langextract_src/         桥接流水线
│   ├── build_kg.py          CLI 入口（支持 --output-dir）
│   └── mineru_adapter.py    content_list.json → Lane A/B 抽取
└── langextract/             Google LangExtract v1.6.0 库源码
```

## 快速启动

**环境要求**：Python 3.12+、Node.js 18+、MinerU API Token、DeepSeek API Key。

### 后端

```bash
cd backend
uv venv
uv pip install --python .venv/Scripts/python.exe \
  fastapi uvicorn python-multipart python-dotenv \
  langgraph langchain-deepseek langchain-core \
  sentence-transformers chromadb

# 创建 .env（gitignored）
echo "DEEPSEEK_API_KEY=sk-..." > .env
echo "DEEPSEEK_BASE_URL=https://api.deepseek.com/v1" >> .env

.venv/Scripts/python.exe -m uvicorn main:app --reload
# → http://127.0.0.1:8000/docs
```

### 前端

```bash
cd frontend
npm install
npm run dev
# → http://127.0.0.1:5173
```

打开浏览器，上传文档，观察流水线进度，浏览知识图谱，提问。

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.12、FastAPI、uvicorn、LangGraph、LangChain、DeepSeek API、SQLite |
| 嵌入 | Sentence-Transformers（`all-MiniLM-L6-v2`，384 维） |
| 向量库 | Chroma（持久化，每文档独立集合） |
| PDF 解析 | MinerU Cloud API v4 |
| 实体抽取 | Google LangExtract v1.6.0 |
| 前端 | React 18、Vite、TypeScript、vis-network v10、react-markdown |
| 包管理 | uv（Python）、npm（Node） |

## 已知限制

- **引用可能为空**：QA Agent 从回答文本中自动提取实体名；若回答未提及任何图谱实体，`citations: []`
- **边永远无 bbox**：协议层限制（见 `bridge_pipeline_specification-v1.0.md` §3.3.1）；边引用使用端点节点坐标回退
- **Office/图片格式未实测**：代码路径已通，但未用真实 `.docx`/`.pptx`/`.png` 样本验证
- **无实体去重**：同一实体同时出现在 Lane A（表格）和 Lane B（文本）中会产生多个独立 KG 节点
- **无鉴权 / 多租户**
- **响应式布局**：桌面端优化；移动端侧边栏抽屉尚未实现
