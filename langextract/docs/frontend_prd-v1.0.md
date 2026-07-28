# 多模态 GraphRAG 问答系统 —— 前端产品需求文档 v1.1

> **文档性质**：产品需求文档（PRD），基于**已实现**的后端 API 和前端代码编写。
> **版本**：v1.1（2026-07-29 更新，与当前实现对齐）
> **消费的上游规范**：`bridge_pipeline_specification-v1.0.md`（KG schema）、`backend_service_architecture-v1.0.md`（后端架构）、`backend/main.py` / `jobs.py` / `qa_agent.py` / `vector_index.py`（已实现）

---

## 目录

1. [核心目标与场景](#1-核心目标与场景)
2. [产品流程](#2-产品流程)
3. [关键页面/模块清单与设计说明](#3-关键页面模块清单与设计说明)
4. [关键节点与核心功能的交互逻辑](#4-关键节点与核心功能的交互逻辑)
5. [整体 UI 布局、配色、响应式与组件样式](#5-整体-ui-布局配色响应式与组件样式)
6. [实现状态对照表](#6-实现状态对照表)

---

## 1. 核心目标与场景

### 1.1 核心目标

后端（`backend/`，FastAPI）已经把 MinerU 文档解析、LangExtract 知识抽取、知识图谱构建、Agentic-RAG 问答、向量检索五个已验证组件收敛成一套支持**多文档并存**的 REST API（8 个端点）。本前端原型的目标：**为这套后端 API 提供一个可运行的 Web 界面**，让"上传文档 → 观察索引进度 → 浏览知识图谱 → 基于图谱 + 向量检索问答"这一完整闭环可以被直观操作和验证，同时如实呈现数据缺口（无坐标节点、未匹配合成节点、关系边无 bbox、citations 可能为空），不掩盖不臆造。

### 1.2 核心场景

| 场景 | 描述 |
|---|---|
| 文档索引与管理 | 上传文档（PDF/Office/图片/纯文本），系统异步跑通 MinerU→LangExtract→Vector Index 链路，前端实时展示阶段状态、成功/失败及原始错误 |
| 知识图谱核查 | 直观查看实体节点、表格节点、关系边；支持按 label 分色展示和类型筛选；可切换节点表/边表逐条核对 provenance |
| 图谱问答 | 针对已索引文档用自然语言提问，基于 KG + 向量检索回答；回答附带结构化 citations（source_kind/page_idx/bbox/node_id/note）；支持 session_id 多轮 |

### 1.3 业务痛点

1. **无可视化验证手段**：后端只能通过 curl/Swagger 验证，效率低
2. **多文档无统一入口**：需要一目了然的列表管理和状态追踪
3. **数据缺口容易被误判**：缺 bbox、未匹配节点、citations 为空时需显式标注
4. **问答结果需可信度线索**：有引用则展示可核验字段，无引用则诚实空状态

### 1.4 用户群体

| 群体 | 需求 |
|---|---|
| 项目内部验证者（主要） | 直观核实上传→索引→图谱→问答全链路是否按预期工作 |
| 知识图谱质检人员（次要） | 逐条核查节点/边的 provenance，关注数据缺口 |
| 业务问答用户（潜在） | 用自然语言从文档获取信息，本原型预留良好体验雏形 |

---

## 2. 产品流程

### 2.0 前置条件

- 后端：`backend/.venv/Scripts/python.exe -m uvicorn main:app --reload`（`127.0.0.1:8000`）
- 前端：`cd frontend && npm run dev`（`127.0.0.1:5173`）

### 2.1 进入系统 → 文档列表

1. 浏览器打开 `http://127.0.0.1:5173/` → 文档列表页
2. 前端调用 `GET /api/v1/documents`，获取全部文档
3. 空状态显示引导提示；有文档按 created_at 倒序展示

### 2.2 上传文档

1. 拖拽或点击选择文件
2. 客户端扩展名预检查（提示但不阻断）；服务端 415 是唯一权威判定
3. `POST /api/v1/documents`（multipart，字段 `file`）
4. 成功：插入新行（status: "queued"），对该行启动 2.5s 轮询
5. 未测格式上传返回 `warning` 字段，行内显示 ⚡ untested 标签

### 2.3 观察索引进度

1. 列表页状态徽标自动刷新（queued→parsing→extracting→ready/failed）
2. 点击行进入详情页 Overview 标签
3. Overview 显示：4 步进度条、元数据网格、实时流水线日志终端（深色主题）
4. 到达 ready 解锁 Graph 和 Q&A 标签；到达 failed 显示原始错误
5. 轮询仅覆盖未落定文档，ready/failed 后停止

### 2.4 浏览知识图谱

1. 点击已解锁的 Graph 标签，调用 `GET /api/v1/documents/{id}/graph`
2. **图形视图**（vis-network v10）：
   - 按 label 分色（hash→HSL 色相环，相同 label 颜色一致）
   - 表格节点（📊 前缀）使用暖橙色系，形状为方框
   - 实体节点使用椭圆，每种 label 独立颜色
   - 灰色菱形：未匹配边的合成占位节点（虚线边）
3. **实体类型筛选栏**：每个 label 一行，带颜色圆点 + 复选框 + 计数，支持 All/None 快捷操作；表格和实体可独立开关
4. **节点表/边表**：可切换视图逐条核对 provenance，缺 bbox 显示"无坐标"红色徽标
5. 节点/边 tooltip 展示完整 provenance（label、page_idx、bbox、block_type）

### 2.5 基于图谱提问

1. 点击 Q&A 标签，看到对话区 + 系统提示（citations + session_id 说明）
2. 输入问题 → 发送 → 显示"Thinking…"加载态（3-20s+）
3. `POST /api/v1/documents/{id}/qa`（body: `{question, session_id}`）
4. 成功：Markdown 渲染回答 + 底部 CitationsList 卡片（source_kind / node_id / page_idx / bbox / note）；无引用时显示"无结构化引用"
5. 同页 session_id 固定，支持多轮追问；刷新后重置
6. 失败：显示错误信息 + Retry 按钮

### 2.6 删除文档

1. 确认对话框 → `DELETE /api/v1/documents/{id}`
2. 成功后从列表移除；若停留在该文档详情页则跳转 404 页

---

## 3. 关键页面/模块清单与设计说明

### 3.1 全局外壳（AppShell + Sidebar）

- 左侧 240px 深色（`#0d1117`）侧边栏，右侧浅色（`#f6f8fa`）内容区
- 侧边栏：品牌标识 "GraphRAG"（蓝底白字 G 图标）、导航项 "📄 Documents"
- 底部：版本号 "v1.0 — citations + multi-turn" + "Responsive layout: not done" 徽标
- 开发者工具视觉基调（GitHub/Linear/Vercel 风格）

### 3.2 文档列表页（DocumentListPage，路由 `/`）

- `UploadDropzone`：虚线边框拖拽区、蓝色圆形 + 号图标、格式说明
- `DocumentTable`：表格（桌面）/ 卡片（移动端）
  - 列：Filename（蓝色链接）、Format（等宽字体）、Status（`StatusBadge` 组件）、Created、删除按钮
  - 未测格式显示 ⚡ untested 标签
  - 行点击跳转详情页
- 空状态："No documents yet. Upload one to get started."
- 错误横幅（红色边框卡片显示原始错误信息）

### 3.3 文档详情页（DocumentDetailPage，路由 `/documents/:docId`）

面包屑导航 + 元数据摘要卡片（文件名、格式、doc_id、节点/边计数、状态徽标、删除按钮）

#### Overview 标签

- **索引进度条**：4 步（queued → parsing → extracting → ready），已完成步显示绿色 ✓，当前步高亮蓝色边框
- **失败块**：红色边框 + `<pre>` 原始错误文本
- **元数据网格**：Filename / Format / Status / Created / Nodes / Edges
- **流水线日志**（ready 后）：深色终端风格 `<pre>`，显示真实子进程 stdout
- **未完成提示**：🚧 "Pipeline log will appear here once indexing completes."

#### Graph 标签

- 仅 ready 状态可访问，否则禁用 + tooltip
- **子视图切换**：Graph View / Nodes Table / Edges Table 三个按钮
- **实体类型筛选栏**（Graph View 模式）：
  - "Entity types" 标签 + All / None 快捷按钮
  - 每行：颜色圆点 + checkbox + 等宽字体 label 名 + 计数
  - 表格节点以 📊 前缀独立展示，暖橙色系圆点
- **图例**：展示前 8 个 label 的颜色圆点及名称，超出显示 +N
- **图形画布**：520px 高，forceAtlas2Based 物理引擎
- **统计**："Showing X/Y nodes, Z/W edges"
- **渲染错误**：红色卡片显示错误详情

#### Q&A 标签

- 仅 ready 状态可访问
- **系统提示**：黄色左边框气泡，说明 citations + session_id
- **对话区**：
  - 用户消息：蓝色浅背景、右对齐、圆角（12/12/4/12）
  - 助手消息：带边框、左对齐、圆角（4/12/12/12）、Markdown 渲染
  - CitationsList 卡片（灰色背景，展示 source_kind / node_id / page_idx / bbox / note）
  - 无引用文本"无结构化引用（本次回答未附带 citations）"
- **输入区**：文本输入框 + Send 按钮，Loading 时禁用
- **错误处理**：红色提示 + Retry 按钮

### 3.4 未找到页（NotFoundPage）

- 大号 404 + "Document not found or has been deleted." + 返回链接

---

## 4. 关键节点与核心功能的交互逻辑

### 4.1 上传与格式路由

- 客户端预检查仅提示，不阻断；服务端 415 + Content-Type/扩展名双重校验为唯一权威
- 上传成功后乐观更新列表，立即对该行启动轮询
- `warning` 字段以行内标签非阻断展示

### 4.2 状态轮询

- 仅对未落定（status ≠ ready/failed）的文档轮询，间隔 2.5s
- 到达终态停止轮询，触发副作用（解锁标签 or 显示错误）

### 4.3 知识图谱

- `GET /graph` 仅在 status=ready 且首次进入 Graph 标签时调用，本地缓存
- 三类缺口可视化：
  1. 节点缺 bbox → "无坐标" 红色徽标
  2. 边永远无 bbox → tooltip 说明协议层限制
  3. 边 subject/object 找不到节点 → 灰色菱形合成节点 + 虚线边
- 按 label 分色 + 类型筛选（checkbox），表格节点独立 📊 前缀
- 重复节点 ID 自动去重；空名称节点 fallback 到 hex id

### 4.4 问答

- 发送后禁用输入，显示 "Thinking…"；响应后恢复
- Markdown 渲染回答；citations 按长度分支展示
- 自动生成 session_id（crypto.randomUUID），同一页面生命周期内固定
- 502 错误保留已输入内容，点击 Retry 重发

### 4.5 删除

- 二次确认弹窗 → 204 后从列表移除 → 详情页 404 跳转

### 4.6 全局错误处理

- 统一 fetch 封装（`lib/api.ts`），解析 `{error_code, message, detail}`
- 展示策略：友好提示 + 原始 message 并存

---

## 5. 整体 UI 布局、配色、响应式与组件样式

### 5.1 整体布局

```
┌───────────┬─────────────────────────────────────────┐
│ 侧边栏     │  面包屑 / 页面标题                        │
│ (240px)   ├─────────────────────────────────────────┤
│ 深色       │                                         │
│ #0d1117   │         主内容区（列表 or 详情+Tabs）       │
│           │                                         │
└───────────┴─────────────────────────────────────────┘
```

### 5.2 配色方案（开发者工具风格 Design Tokens）

| 用途 | 变量 | 取值 |
|---|---|---|
| 页面背景 | `--color-bg` | `#f6f8fa` |
| 侧边栏背景 | `--color-sidebar-bg` | `#0d1117` |
| 卡片背景 | `--color-card-bg` | `#ffffff` |
| 边框 | `--color-border` | `#d0d7de` |
| 正文 | `--color-text` | `#1f2328` |
| 次要文字 | `--color-text-muted` | `#656d76` |
| 侧栏文字 | `--color-sidebar-text` | `#c9d1d9` |
| 侧栏次要文字 | `--color-sidebar-text-muted` | `#8b949e` |
| 强调色 | `--color-accent` | `#2f81f7` |
| 成功 | `--color-success` | `#1a7f37` |
| 警示 | `--color-warning` | `#9a6700` |
| 危险 | `--color-danger` | `#cf222e` |
| 无衬线字体 | `--font-sans` | `-apple-system, "Segoe UI", "Microsoft YaHei", sans-serif` |
| 等宽字体 | `--font-mono` | `ui-monospace, "SFMono-Regular", Consolas, monospace` |

状态徽标配色：queued 灰 / parsing 蓝 / extracting 蓝 / ready 绿 / failed 红

### 5.3 Graph 节点分色方案

| 节点类型 | 颜色 | 形状 |
|---|---|---|
| 实体（Lane B LLM 抽取） | 按 label 哈希→HSL 色相环，相同 label 同色 | 椭圆 |
| 表格（Lane A 确定性解析） | 暖橙色调（hsl(24, 60-90%, 48-63%)），📊 前缀 | 方框 |
| 合成节点（边端点未匹配） | 灰色（#adb5bd） | 菱形，虚线边 |

### 5.4 响应式规则

| 断点 | 布局变化 |
|---|---|
| ≥1024px | 固定 240px 侧边栏；图谱 520px 高；水平标签页 |
| 768–1023px | 侧栏收起为图标/抽屉；图谱高度压缩；表格横向滚动 |
| <768px | 侧栏汉堡菜单抽屉；列表切换卡片；标签横向滚动条；图谱 ~360px；输入框吸附底部 |

> 移动端响应式标记为 not done（见 Sidebar 底部徽标）

### 5.5 组件样式约定

- **StatusBadge**：小圆角矩形，背景浅色 + 文字深色（同语义色系）
- **DocumentTable**：hover 高亮行；移动端卡片纵向堆叠
- **QAChat**：用户气泡蓝底右对齐；助手气泡灰底左边框；citations 卡片灰色背景
- **错误块**：红边框浅红背景；原始错误 `<pre>` 等宽字体
- **Pipeline Log**：深色终端 `#0d1117` 背景 + 绿色字体 `#c9d1d9`

---

## 6. 实现状态对照表

| PRD 条目 | 状态 |
|---|---|
| 文档列表页 — 上传 + 表格 + 轮询 | ✅ |
| 文档列表页 — 空状态提示 | ✅ |
| 文档详情 — Overview 进度条 + 元数据 | ✅ |
| 文档详情 — Overview 流水线日志终端 | ✅ |
| 文档详情 — Graph 标签 gating（ready 解锁） | ✅ |
| 文档详情 — Graph vis-network 图形视图 | ✅ |
| 文档详情 — Graph 按 label 分色（hash→HSL） | ✅ |
| 文档详情 — Graph 📊 表格节点独立过滤 + 暖橙色调 | ✅ |
| 文档详情 — Graph 实体类型筛选栏（checkbox） | ✅ |
| 文档详情 — Graph 节点表/边表切换 | ✅ |
| 文档详情 — Graph bbox 缺失"无坐标"徽标 | ✅ |
| 文档详情 — Graph 合成节点（未匹配边，灰色菱形） | ✅ |
| 文档详情 — Graph tooltip 完整 provenance | ✅ |
| 文档详情 — Q&A Markdown 渲染 + CitationsList | ✅ |
| 文档详情 — Q&A 无引用空状态 | ✅ |
| 文档详情 — Q&A session_id 多轮 | ✅ |
| 文档详情 — Q&A Thinking 加载态 + Retry | ✅ |
| 全局错误处理（error_code + message） | ✅ |
| 404 页面 | ✅ |
| Graph API 过滤参数（label/page_idx/has_bbox） | ✅ |
| Content-Type 双重校验 | ✅ |
| 移动端响应式布局 | ❌（Sidebar 已标注） |
| 多语言 / i18n | ❌ 未计划 |
