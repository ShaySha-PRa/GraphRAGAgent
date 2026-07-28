# MinerU 文档解析规范文档 v1.0（实测校订版）

> **基础文档**: [`MinerU_Specification.md`](./MinerU_Specification.md)（初版，纯调研，未实测）
> **官方文档**: <https://mineru.net/apiManage/docs>
> **本版本状态**: ✅ 已通过本地 MVP **端到端实测验证**（2026-07-28）
> **验证方式**: 真实 API 调用 + 真实 PDF 解析 + 真实 ZIP 输出文件逐字段核对
> **校订原则**: 官方文档与实测结果冲突时，**以本地实测的真实输出为准**，冲突点均在下文明确标注 🔴

---

## 目录

1. [完整 Pipeline 执行思路与脚本位置](#1-完整-pipeline-执行思路与脚本位置)
2. [输出文件清单：官方文档 vs 实测结果](#2-输出文件清单官方文档-vs-实测结果)
3. [关键参数规范（请求 / 响应）](#3-关键参数规范请求--响应)
4. [本地实际生成文件的完整清单](#4-本地实际生成文件的完整清单)
5. [遗留问题与后续验证建议](#5-遗留问题与后续验证建议)

---

## 1. 完整 Pipeline 执行思路与脚本位置

### 1.1 代码位置

| 内容 | 路径 |
|---|---|
| Pipeline 脚本 | `mineru-pipeline/pipeline.py` |
| 虚拟环境 | `mineru-pipeline/.venv/`（uv 管理，Python 3.12） |
| 环境配置 | `mineru-pipeline/.env`（`MINERU_API_TOKEN` 等） |
| 测试输入 PDF | `mineru-pipeline/test_documents/financial_report.pdf` |
| 解析结果输出目录 | `mineru-pipeline/output/{原始文件名}_{时间戳}/` |

#### 虚拟环境（uv）与启动命令

为避免 MinerU、LangExtract、后续 GraphRAG 组件之间的 Python 依赖冲突，MinerU Pipeline 运行在**独立的 uv 虚拟环境**中。任何对 `pipeline.py` 的执行、调试、或新增依赖，都必须经由该 venv。

```bash
# 方式 A：激活虚拟环境后运行（bash / Git Bash）
cd mineru-pipeline
source .venv/Scripts/activate
python pipeline.py

# 方式 B：直接调用 venv 内的 Python 解释器（所有 Shell，适合脚本化）
mineru-pipeline/.venv/Scripts/python.exe pipeline.py

# 新增依赖
cd mineru-pipeline
python -m uv pip install --python .venv/Scripts/python.exe <package>
```

### 1.2 四阶段执行流程（实测确认）

```
[Phase 1] 本地扫描 PDF
   discover_pdfs(test_documents/) → 去重后的 pathlib.Path 列表
        │
        ▼
[Phase 2] 申请上传 URL + 上传文件
   POST /api/v4/file-urls/batch  { "files": [{"name","size"}, ...] }
        │  → { "batch_id", "file_urls": [url1, url2, ...] }   # 字符串数组，按下标对应本地文件
        ▼
   PUT {file_urls[i]} , body=文件二进制, 【不附带任何自定义 header】
        │  （附带 Content-Type 等 header 会导致阿里云 OSS 预签名 URL 校验失败 → 403 SignatureDoesNotMatch）
        ▼
[Phase 3] 轮询解析状态
   GET /api/v4/extract-results/batch/{batch_id}
        │  → data.extract_result: [ {file_name, state, full_zip_url?, err_msg?, extract_progress?}, ... ]
        │  循环直到全部 state == "done"（或出现 "failed" 立即抛错）
        ▼
[Phase 4] 下载 ZIP 并本地解压
   GET {full_zip_url} → ZIP 二进制 → 解压至 output/{file_name}_{timestamp}/
        │
        ▼
   打印摘要：full.md 行数/字符数、content_list.json 分块统计、images/ 文件数
```

### 1.3 关键工程细节（均来自实测调试，非文档推测）

| 环节 | 细节 |
|---|---|
| OSS 上传 | `requests.put(url, data=fh, timeout=120)`，**禁止**加 `headers={"Content-Type": ...}` |
| 轮询容错 | 需同时捕获 `SSLError`、`ConnectionError`、`Timeout` 三类异常并指数退避重试（1s/2s/4s），否则单次网络抖动会直接中断整条 Pipeline |
| Windows 编码 | 控制台输出含中文/emoji 时需 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` |
| Windows 文件发现 | `glob("*.pdf")` 与 `glob("*.PDF")` 在 Windows 下会重复匹配同一文件，需 `set()` 去重 |

---

## 2. 输出文件清单：官方文档 vs 实测结果

### 2.1 差异总览表

| 官方文档声称的文件 | 本次实测是否存在 | 实测结果 |
|---|---|---|
| `full.md` | ✅ 存在 | 命名、内容与文档描述一致 |
| `{filename}_content_list.json` | ⚠️ 存在但命名不同 | 🔴 实际前缀是**任务 ID（UUID）**，不是原始文件名。例：`87da03d1-3bea-4688-8e09-337c44ca265c_content_list.json` |
| `{filename}_content_list_v2.json` | ⚠️ 存在但命名不同 | 🔴 同上，前缀为任务 UUID；且官方文档仅在文件清单中提及一句"按页分组，v3.0+"，**未给出字段级 schema** —— 本文档 [§4.3](#43-content_list_v2json-字段说明补充实测) 已补全 |
| `{filename}_model.json` | ⚠️ 存在但命名不同 | 🔴 前缀为任务 UUID；字段 schema 与文档描述的「Pipeline 后端」格式**完全一致**（`cls_id`/`label`/`score`/`bbox` 绝对像素/`index`） |
| `{filename}_middle.json` | ❌ **不存在** | 🔴 本次实测的 ZIP 中**没有任何名为 `middle.json` 的文件**。取而代之的是一个**不带文件名前缀**的 `layout.json`，其内部结构（`pdf_info → preproc_blocks → lines → spans`，绝对像素 bbox）与文档 §2.3 描述的 `middle.json` 结构**完全相同**。结论：当前 API 版本已将该文件**重命名为 `layout.json`**，官方文档尚未同步更新 |
| `{filename}_layout.pdf`（布局可视化 PDF） | ❌ **不存在** | 🔴 实测 ZIP 中没有任何可视化 PDF |
| `{filename}_span.pdf`（Span 可视化 PDF） | ❌ **不存在** | 🔴 实测 ZIP 中没有任何可视化 PDF |
| （未提及）`{taskid}_origin.pdf` | ✅ 存在但**文档完全未提及** | 🔴 ZIP 中包含一份原始 PDF 的回传副本，官方文档的文件清单里完全没有这一项 |
| `images/*.png 或 .jpg` | ✅ 存在 | ⚠️ 实测文件名为**内容哈希值 + `.jpg`**（如 `615dfae0e2a9d211e52c1b6089fba023ba35fa4c39ba6d5b4abe2ec4cebbc30b.jpg`），而非文档示例中的描述性命名（如 `table_3_0.png`）。扩展名统一是 `.jpg`，未观测到 `.png` |

### 2.2 结论：以实测为准的真实 ZIP 文件清单

```
{output_dir}/
├── full.md                              # ✅ 与文档一致
├── {task_id}_content_list.json          # ⚠️ 前缀是 UUID，非原始文件名
├── {task_id}_content_list_v2.json       # ⚠️ 同上
├── {task_id}_model.json                 # ⚠️ 同上，schema = Pipeline 后端格式
├── {task_id}_origin.pdf                 # 🔴 官方文档未记录的新增文件（原始 PDF 副本）
├── layout.json                          # 🔴 取代了文档中的 {filename}_middle.json，且不带文件名前缀
└── images/
    └── {content_hash}.jpg               # 🔴 内容哈希命名，非描述性命名；仅观测到 .jpg
```

> **未观测到**：`{filename}_layout.pdf`、`{filename}_span.pdf`。这两个可视化调试文件在本次（pipeline 后端、默认参数）测试中均未生成。不排除仅在 `model_version="pipeline"` 显式开启某些调试参数，或 VLM 后端下才会产出，需后续针对性验证（见 [§5](#5-遗留问题与后续验证建议)）。

### 2.3 content_list_v2.json 字段说明补充（实测，官方文档未展开）

官方文档只在文件清单里提了一句"内容列表 v2（按页分组，v3.0+）"，没有给字段级说明。实测结构如下：

```json
// 顶层结构：list[page] → list[block]（按页分组，与 content_list.json 的扁平结构不同）
[
  [  // 第 0 页的所有块
    {
      "type": "title",
      "content": {
        "title_content": [ { "type": "text", "content": "2025年度财务分析报告" } ],
        "level": 1
      },
      "bbox": [337, 39, 660, 65]
    },
    {
      "type": "paragraph",
      "content": {
        "paragraph_content": [ { "type": "text", "content": "本公司成立于2020年..." } ]
      },
      "bbox": [45, 128, 949, 186]
    },
    {
      "type": "table",
      "content": {
        "image_source": { "path": "images/d5293ad0...jpg" },
        "table_caption": [],
        "table_footnote": [],
        "html": "<table>...</table>"
      },
      "bbox": [45, 233, 810, 423]
    }
  ]
]
```

| 字段 | 说明 |
|---|---|
| 顶层 | `list[page][block]`，按页分组（`content_list.json` 是扁平 `list[block]`，靠 `page_idx` 区分页码） |
| `type` | 观测到 `title` / `paragraph` / `table`（未覆盖到 image/equation/code 等其余类型，样本文档中未出现） |
| `content.title_content[]` / `content.paragraph_content[]` | 嵌套的富文本片段数组，每项含 `type` + `content` |
| `content.image_source.path` | 表格截图相对路径（等价于 `content_list.json` 的 `img_path`） |
| `content.html` | 表格 HTML（等价于 `content_list.json` 的 `table_body`，但字段名不同：`html` vs `table_body`） |
| `bbox` | 坐标范围与 `content_list.json` 一致（0–1000 归一化），与同一元素在两个文件中的数值完全相同 |

🔴 **冲突点**：同一份表格数据在 `content_list.json` 中字段名为 `table_body`，在 `content_list_v2.json` 中字段名为 `html`。若下游代码需要同时兼容两个文件，字段名不能直接复用。

---

## 3. 关键参数规范（请求 / 响应）

### 3.1 请求参数：官方文档声称 vs 本次实测实际发送

| 参数 | 官方文档默认值 | 本次 MVP 实测是否发送 | 说明 |
|---|---|---|---|
| `model_version` | `"pipeline"` | ❌ 未发送 | 请求体中完全没有此字段，服务端按默认值 `"pipeline"` 处理 |
| `is_ocr` | `false` | ❌ 未发送 | 走默认值 |
| `enable_formula` | `true` | ❌ 未发送 | 走默认值 |
| `enable_table` | `true` | ❌ 未发送 | 走默认值 |
| `language` | `"ch"` | ❌ 未发送 | 走默认值 |
| `extra_formats` | — | ❌ 未发送 | 走默认值（无额外导出） |
| `page_ranges` | — | ❌ 未发送 | 走默认值（全部页） |

**实测发送的完整请求体**（`POST /api/v4/file-urls/batch`）：

```json
{
  "files": [
    { "name": "financial_report.pdf", "size": 86731 }
  ]
}
```

🔴 **关键交叉验证**：本次请求未显式指定 `model_version`，而实测返回的 `model.json` 字段结构（`cls_id`/`label`/`score`/`bbox` 绝对像素/`index`）**精确匹配**官方文档中「Pipeline 后端」的 schema，而非「VLM 后端」的 `[[{type, bbox 0-1归一化, angle, content, ...}]]` 结构。这从实测数据侧**验证了**官方文档"默认值 `model_version = pipeline`"的说法是准确的——即本地 `pipeline.py` 打印的 `Model: vlm` 仅是脚本内 `MODEL` 变量的展示值（来自 `.env` 中被注释掉后又回落到 Python 默认字符串 `"vlm"`），**从未真正传给 API**，实际生效的是服务端默认的 `pipeline` 后端。

> **建议修正**：`pipeline.py` 当前完全没有把 `MODEL`/`enable_formula`/`language` 等 `.env` 配置项拼进请求体，这些配置目前是"摆设"。如果后续需要真正切换到 VLM 后端或开启公式识别，需要在 `request_upload_urls()` 里把这些字段加入 `payload`。

### 3.2 响应参数：批量查询结果结构（本次调试中发现的核心 Bug 来源）

🔴 **最关键的一处文档缺口**：初版 `MinerU_Specification.md` 只文档化了**单任务查询**接口（`GET /api/v4/extract/task/{task_id}` → `data.state`），**完全没有文档化批量查询接口**（`GET /api/v4/extract-results/batch/{batch_id}`）的响应体结构，尽管两者结构并不相同。这个空白直接导致 `pipeline.py` 早期版本读取了错误的字段名（`data.results`），造成轮询 200 次全部读到空列表、看起来像"卡死"而不是报错。

**实测确认的批量查询真实响应结构**：

```json
{
  "code": 0,
  "msg": "ok",
  "trace_id": "...",
  "data": {
    "batch_id": "ba57a585-1de1-4af3-8473-4e7728d6e763",
    "extract_result": [
      {
        "file_name": "financial_report.pdf",
        "state": "running",
        "err_msg": "",
        "extract_progress": {
          "extracted_pages": 0,
          "total_pages": 1,
          "start_time": "2026-07-28 15:30:12"
        }
      }
    ]
  }
}
```

| 字段路径 | 正确取值方式 | 常见错误 |
|---|---|---|
| 结果数组 | `data.extract_result` | ❌ `data.results`（不存在，静默返回空列表，**不会报错**，表现为轮询永远"pending"） |
| 完成态 URL | `extract_result[i].full_zip_url` | 仅当 `state == "done"` 时存在 |
| 失败信息 | `extract_result[i].err_msg` | 仅当 `state == "failed"` 时有意义 |
| 进度 | `extract_result[i].extract_progress.{extracted_pages,total_pages,start_time}` | 仅当 `state == "running"` 时存在 |

**实测观测到的 `state` 取值**：`running` → `done`（本次任务耗时约 6–7 分钟，1 页 PDF）。官方文档还定义了 `pending`、`waiting-file`、`failed`、`converting` 四种状态，本次实测未触发，未验证。

### 3.3 轮询响应的异常处理规范（实测新增，官方文档未涉及）

实测中，轮询在第 130 次左右遭遇 `ReadTimeout`（非文档 Bug，是网络层瞬时问题），暴露出以下要求：

- 轮询 HTTP 客户端必须同时捕获 `SSLError`、`ConnectionError`、`Timeout` 三类异常，仅捕获前两类不足以覆盖读超时场景。
- 建议的重试策略：3 次指数退避（1s/2s/4s），最终一次失败时可回退到 `verify=False` 重试一次（仅用于排除证书链问题，生产环境不建议长期关闭校验）。

---

## 4. 本地实际生成文件的完整清单

以下为 `financial_report.pdf`（1 页，86,731 字节，中文财务报告）实测生成的**全部文件**，逐一列出真实文件名、大小、用途，供对照官方文档核实数量与类型。

| 文件名 | 大小 | 官方文档中是否提及 | 用途 |
|---|---|---|---|
| `full.md` | 2,672 字节（25 行） | ✅ 是 | Markdown 全文，含 4 个 `##` 标题、2 个 HTML `<table>` |
| `87da03d1..._content_list.json` | 5,353 字节 | ✅ 是（但命名前缀不同） | 13 个内容块（11 text + 2 table），核心抽取源 |
| `87da03d1..._content_list_v2.json` | 8,159 字节 | ✅ 是（但字段未文档化） | 按页分组的富结构版本，见 [§2.3](#23-content_list_v2json-字段说明补充实测) |
| `87da03d1..._model.json` | 9,824 字节 | ✅ 是（但命名前缀不同） | 原始检测结果，schema = Pipeline 后端 |
| `87da03d1..._origin.pdf` | 84,663 字节 | 🔴 **文档未提及** | 原始 PDF 回传副本 |
| `layout.json` | 45,433 字节 | 🔴 **文档中此文件名不存在**（对应文档中的 `middle.json`） | 最详细布局信息，`pdf_info → preproc_blocks → lines → spans`，绝对像素 bbox |
| `images/615dfae0...jpg` | — | ✅ 是（但命名方式不同） | 表格 3（三、技术指标体系）截图，1264×317 px |
| `images/d5293ad0...jpg` | — | ✅ 是（但命名方式不同） | 表格 2（二、核心财务指标）截图，1264×445 px |

**文件数量对比**：

| | 官方文档声称的文件数 | 实测实际文件数 |
|---|---|---|
| 总文件数（不含 `images/` 内部） | 7（`full.md` + 5 个 JSON/PDF + `images/` 目录本身） | 6（`full.md` + 3 个 JSON + 1 个 PDF + `layout.json`） |
| `images/` 内图片数 | 未定量（"提取的图片/表格/公式截图"） | 2（与 `content_list.json` 中 2 个 `table` 块一一对应） |
| 可视化调试 PDF（`layout.pdf`/`span.pdf`） | 2 | **0** |

结论：**实测文件类型集合与官方文档不完全一致**——多了 `origin.pdf`，少了 `layout.pdf`/`span.pdf`，`middle.json` 被替换为不带前缀的 `layout.json`。数量上，图片文件数与实际表格数量精确对应（2 个表格 → 2 张截图），符合预期；JSON 类文件数量（3 个：`content_list`/`content_list_v2`/`model`）与文档一致。

---

## 5. 遗留问题与后续验证建议

1. `layout.pdf`/`span.pdf` 缺失的原因未定论——需要用一份多页、含公式/代码块的更复杂 PDF 重新测试，排除"当前样本过于简单，服务端跳过生成调试可视化文件"的可能性。
2. 未显式传递 `model_version="vlm"` 进行对照测试，无法直接实测验证官方文档中 VLM 后端的 `model.json`（`[[{type, bbox 0-1, angle, ...}]]`）结构是否与文档描述一致——当前只验证了 Pipeline 后端。
3. 未触发 `state: "failed"` / `"waiting-file"` / `"converting"` / `"pending"`，这四种状态的实际响应体结构仍基于官方文档描述，未经本地实测验证。
4. `content_list_v2.json` 仅验证了 `title`/`paragraph`/`table` 三种 `type`，`image`/`equation`/`code`/`list` 等类型在 v2 结构下的字段命名（是否也是 `content.{type}_content` 模式）尚未实测确认。

---

## 附录：本文档与初版文档的关系

- 初版 [`MinerU_Specification.md`](./MinerU_Specification.md) 保留不变，作为"调研阶段、未实测"的历史记录。
- 本文档（v1.0）是**唯一以实测为准**的版本，后续如需查阅 MinerU 输出格式，应优先参考本文档；仅在本文档未覆盖的细节（如布局坐标系换算公式、数值抽取策略代码示例）上，才回退参考初版文档。
