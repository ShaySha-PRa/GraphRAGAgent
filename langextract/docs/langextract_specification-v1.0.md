# LangExtract 信息抽取规范文档 v1.0（实测校订版）

> **基础文档**: [`LANGExtract_Specification.md`](./LANGExtract_Specification.md)（源码调研版，未跑通真实 LLM 调用）
> **源码仓库**: `langextract/`（v1.6.0，editable 安装于 `langextract_src/.venv/`）
> **本版本状态**: ✅ 已通过本地 MVP **端到端实测验证**（2026-07-28），真实调用 DeepSeek API（`deepseek-chat`，OpenAI 兼容接口）
> **验证方式**: 真实 LLM 推理 + 真实 JSONL/HTML 输出文件逐字段核对
> **校订原则**: 源码调研文档与实测结果冲突时，**以本地实测的真实输出为准**，冲突点均在下文明确标注 🔴

---

## 目录

1. [完整 Pipeline 执行思路与脚本位置](#1-完整-pipeline-执行思路与脚本位置)
2. [输出数据格式：源码调研文档 vs 实测结果](#2-输出数据格式源码调研文档-vs-实测结果)
3. [关键参数规范](#3-关键参数规范)
4. [本地实际生成文件的完整清单](#4-本地实际生成文件的完整清单)
5. [遗留问题与后续验证建议](#5-遗留问题与后续验证建议)

---

## 1. 完整 Pipeline 执行思路与脚本位置

### 1.1 代码位置

| 内容 | 路径 |
|---|---|
| MVP 测试脚本 | `langextract_src/test_deepseek_extract.py` |
| 虚拟环境 | `langextract_src/.venv/`（uv 管理，Python 3.12） |
| LangExtract 源码 | `langextract/langextract/`（editable 安装，改源码立即生效，无需重装） |
| 环境配置 | `langextract_src/.env`（`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`） |
| 输出目录 | `langextract_src/output/`（`extraction_results.jsonl` + `visualization.html`） |
| 组件级 CLAUDE.md | `langextract_src/CLAUDE.md`（venv 强制说明） |

#### 虚拟环境（uv）与启动命令

`langextract_src/.venv/` 与 `langextract/`（源码克隆，无 venv）、`mineru-pipeline/.venv/` 完全隔离。任何脚本执行都必须经由该 venv，且 **cwd 不能是项目根目录**（原因见 [§1.3](#13-关键工程细节均来自实测调试非源码调研文档推测)）。

```bash
# 正确：cwd 切到 langextract_src/ 内
cd langextract_src
.venv/Scripts/python.exe test_deepseek_extract.py

# 新增依赖
cd langextract_src
python -m uv pip install --python .venv/Scripts/python.exe <package>
```

### 1.2 六阶段执行流程（实测确认）

```
[Phase 1] 构造输入文本 + few-shot 示例
   MOCK_TEXT（模拟病历文本，纯字符串）
   EXAMPLES: list[ExampleData]（每条含 text + extractions）
        │
        ▼
[Phase 2] 装配 Provider（DeepSeek 无内置 Provider，需显式指定）
   ModelConfig(
       model_id="deepseek-chat",
       provider="openai",            # 强制走 OpenAI 兼容 Provider
       provider_kwargs={"api_key": ..., "base_url": "https://api.deepseek.com"},
   )
        │  🔴 model_id "deepseek-chat" 不匹配任何内置 provider 的 model_id 正则
        │     （gemini/gpt/o1-o4/ollama 均不含 "deepseek"），必须显式 provider="openai"
        ▼
[Phase 3] lx.extract() 调用
   text_or_documents=MOCK_TEXT, prompt_description=..., examples=EXAMPLES,
   config=config, use_schema_constraints=False
        │  内部：Prompt 构建(few-shot) → Chunking(单 chunk，文本仅 161 字符)
        │       → Inference(OpenAILanguageModel.infer, base_url 覆盖为 DeepSeek 端点)
        │       → Resolver(JSON 解析 + 字符位置对齐)
        ▼
[Phase 4] 返回 AnnotatedDocument（单文本输入 → 单对象，非 list）
        │
        ▼
[Phase 5] 持久化 JSONL
   lx.io.save_annotated_documents([result], output_dir=..., output_name="extraction_results.jsonl")
        │
        ▼
[Phase 6] 生成可视化 HTML
   lx.visualize(str(jsonl_path)) → HTML 片段字符串 → 手动 write_text() 落盘
```

### 1.3 关键工程细节（均来自实测调试，非源码调研文档推测）

| 环节 | 细节 |
|---|---|
| 🔴 **cwd 命名空间坑** | 项目根目录 `GraphRAGAgent/` 下恰好有个叫 `langextract/` 的文件夹（源码仓库本身，顶层无 `__init__.py`）。若从项目根跑 `python -c "import langextract"`，Python 默认 `PathFinder` 会把它误判成一个**空的 PEP 420 namespace package**，抢在 editable-install 的 finder 之前"拦截"了导入——`import langextract` 不报错，但 `lx.__file__` 为 `None`，`lx.extract` 等任何真实属性访问全部触发 `AttributeError`。**必须从 `langextract_src/` 或其他非碰撞目录运行**才能拿到真实的 editable 安装 |
| Provider 路由 | `model_id` 字符串匹配是内置 provider 自动路由的唯一依据（`providers/patterns.py`）。第三方 OpenAI 兼容服务（DeepSeek、Moonshot 等）的 `model_id` 通常不含 `gpt`/`o1`-`o4` 等关键字，**必须用 `ModelConfig(provider="openai", ...)` 显式指定**，否则 `factory.create_model` 会抛 `InferenceConfigError`（未匹配到任何 provider） |
| API Key 解析 | 源码调研文档只写了通用的 `LANGEXTRACT_API_KEY`，实测阅读 `factory.py:70-75` 发现更精确的优先级：`gpt` 系模型优先读 `OPENAI_API_KEY`，`gemini` 系优先读 `GEMINI_API_KEY`，两者都以 `LANGEXTRACT_API_KEY` 作为兜底。**本次 MVP 未使用环境变量自动解析**——因为走的是 `ModelConfig.provider_kwargs={"api_key": ...}` 显式传参路径（`factory.py` 中 `if "api_key" not in resolved` 才会触发环境变量兜底逻辑），从 `.env` 的 `DEEPSEEK_API_KEY` 读出后手动传入 |
| Schema 约束兼容性 | `lx.extract()` 的 `use_schema_constraints` 默认 `True`，会尝试对 OpenAI Provider 施加 `response_format={"type":"json_schema",...}` 的 strict 结构化输出。DeepSeek 的 OpenAI 兼容端点是否支持该模式未经文档确认，本次 MVP **显式设为 `False`** 规避风险，实测退化为普通 `{"type":"json_object"}` JSON mode + few-shot 提示，效果正常（2/2 实体精确抽取，`alignment_status` 均为 `MATCH_EXACT`） |
| Windows 控制台编码 | `lx.io.save_annotated_documents()` 的进度条会打印 `✓`（Unicode checkmark），Windows 默认 GBK 控制台会抛 `UnicodeEncodeError`。修复方式与 `mineru-pipeline/pipeline.py` 完全一致：脚本顶部加 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` |
| 首次运行耗时 | 单条 161 字符文本、单 chunk、单次 LLM 调用，端到端（含网络往返）约 5–7 秒 |

---

## 2. 输出数据格式：源码调研文档 vs 实测结果

### 2.1 AnnotatedDocument / JSONL 结构差异

| 源码调研文档描述 | 实测结果 | 差异说明 |
|---|---|---|
| JSON 顶层字段顺序示例：`document_id, text, extractions` | 实测顺序：`extractions, text, document_id` | ⚠️ JSON 对象字段本身无序，语义上不影响解析；但若下游用**正则/逐字段位置**解析（而非 JSON parser）需注意，不能假设固定顺序 |
| 示例中 `extraction_index` 从 `0` 开始 | 实测第一个实体 `extraction_index: 1`，第二个 `extraction_index: 2` | 🔴 实测索引从 **1** 开始计数，非文档示例展示的 0。`group_index` 则确认从 0 开始（`0`, `1`），两个计数器**起始值不一致**，使用时不能假设两者对齐 |
| `lx.visualize()` "生成的 HTML 可在浏览器中交互式浏览" | ✅ 功能正确，但 🔴 **实际产物是 HTML 片段，非完整文档**：无 `<!DOCTYPE>`/`<html>`/`<head>`/`<body>` 标签，仅 `<style>...</style>` + `<div class="lx-animated-wrapper">...</div>`（内含 `<script>` 定义 `extractions` JS 数组驱动高亮动画）。浏览器可以容错渲染裸片段，但若要生成规范 HTML 文档需自行包一层 `<html><body>` | 
| `char_interval`/`alignment_status` 字段格式 | ✅ 与文档完全一致 | 无差异；本次两个实体均 `alignment_status: "match_exact"`，`char_interval` 均非 `None` |

### 2.2 实测确认的真实 JSONL 单行结构

```json
{
  "extractions": [
    {
      "extraction_class": "medication",
      "extraction_text": "Metformin",
      "char_interval": {"start_pos": 35, "end_pos": 44},
      "alignment_status": "match_exact",
      "extraction_index": 1,
      "group_index": 0,
      "description": null,
      "attributes": {"dosage": "500mg", "frequency": "twice daily", "indication": "type 2 diabetes"}
    }
  ],
  "text": "Patient John Carter was prescribed Metformin 500mg twice daily for type 2 diabetes. He was also given Lisinopril 10mg once daily in the morning for hypertension.",
  "document_id": "doc_b9158088"
}
```

- `document_id` 自动生成为 `doc_{8位hex}`，与文档描述一致
- 每次运行 `document_id` 都不同（UUID 派生），非确定性——与文档 [§4.5.2](./LANGExtract_Specification.md) "非确定性" 提示一致

### 2.3 visualization.html 实测结构

```
<style>...</style>                              # ~100 行内联 CSS（高亮框、tooltip、控制条样式）
<div class="lx-animated-wrapper lx-gif-optimized">
  <div class="lx-attributes-panel">
    <div class="lx-legend">...</div>            # 按 extraction_class 着色的图例
    <div id="attributesContainer"></div>
  </div>
  <div class="lx-text-window" id="textWindow"></div>
  <div class="lx-controls">...</div>            # 播放/暂停/进度条控制
  <script>
    const extractions = [                        # 逐实体 JS 对象数组，驱动动画高亮
      {"index":0, "class":"medication", "text":"Metformin", "color":"#D2E3FC",
       "startPos":35, "endPos":44, "beforeText":"...", "extractionText":"Metformin",
       "afterText":"...", "attributesHtml":"<div>...</div>"},
      ...
    ];
    ...
  </script>
</div>
```

无 IPython 环境时 `lx.visualize()` 返回裸字符串（非 `IPython.display.HTML` 对象），代码里需要 `html.data if hasattr(html, "data") else html` 兼容两种返回类型——本次实测在纯 venv Python（无 IPython）下走的是字符串分支。

---

## 3. 关键参数规范

### 3.1 `lx.extract()` 主参数（实测使用值 vs 默认值）

| 参数 | 默认值 | 本次 MVP 实测值 | 说明 |
|---|---|---|---|
| `text_or_documents` | 必填 | 161 字符纯文本字符串 | 走 `annotate_text()` 分支，返回单个 `AnnotatedDocument`（非 list） |
| `prompt_description` | `None` | 一句英文任务描述 | 拼入 few-shot prompt 模板 |
| `examples` | `None` | 1 条 `ExampleData`（1 个 `Extraction`） | few-shot 数量对结果质量影响未测（仅测过 1 条） |
| `model_id` | `"gemini-3.5-flash"` | `"deepseek-chat"`（通过 `config.model_id`，未单独传 `model_id` 参数） | 直接传 `model_id="deepseek-chat"` 会因无法匹配任何 provider 正则而失败,必须走 `config=` |
| `config` | `None` | `ModelConfig(model_id, provider="openai", provider_kwargs={api_key, base_url})` | 见 [§1.3](#13-关键工程细节均来自实测调试非源码调研文档推测) |
| `use_schema_constraints` | `True` | **`False`**（显式关闭） | 关闭后退化为 `response_format={"type":"json_object"}` 普通 JSON mode，DeepSeek 兼容端点实测可用 |
| `fetch_urls` | `False` | 未使用 | 本次输入是纯字符串，非 URL |
| `max_char_buffer` | `1000` | 未显式传（用默认值） | 输入仅 161 字符，未触发分块 |
| `extraction_passes` | `1` | 未显式传（用默认值） | 未测试多轮抽取对召回率的影响 |
| `batch_length` / `max_workers` | `10` / `10` | 未显式传 | 单文本输入未触发批处理/并行路径 |
| `fence_output` | `None` | 未显式传 | OpenAI Provider 的 `requires_fence_output` 在 JSON mode 下自动为 `False`（见源码 `openai.py:96-104`），无需手工设置 |

### 3.2 `ModelConfig`（`factory.py`）字段

| 字段 | 类型 | 本次实测值 |
|---|---|---|
| `model_id` | `str \| None` | `"deepseek-chat"` |
| `provider` | `str \| None` | `"openai"`（**必填**，因 model_id 不含内置 provider 匹配关键字） |
| `provider_kwargs` | `dict` | `{"api_key": "sk-...", "base_url": "https://api.deepseek.com"}` |

### 3.3 `OpenAILanguageModel`（实际承接 DeepSeek 调用的 Provider）关键字段

源码：`langextract/providers/openai.py:42-171`

| 字段 | 默认值 | 说明 |
|---|---|---|
| `model_id` | `"gpt-4o-mini"` | 实测被覆盖为 `"deepseek-chat"` |
| `api_key` | `None` | 必填，否则 `__init__` 直接抛 `InferenceConfigError('API key not provided.')` |
| `base_url` | `None` | 实测覆盖为 `"https://api.deepseek.com"`；为 `None` 时使用 OpenAI 官方端点 |
| `format_type` | `data.FormatType.JSON` | 决定 system prompt 措辞（"respond in JSON format"）与 `response_format` 取值 |
| `temperature` | `None` | 未覆盖，走 API 侧默认值 |
| `max_workers` | `10` | 控制 `infer()` 内部并发线程数（`concurrent.futures`），单条输入未触发 |

底层实际发出的请求（`_build_chat_completions_params`，`openai.py:180-242`）等价于：
```python
client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": "You are a helpful assistant that responds in JSON format."},
        {"role": "user", "content": "<few-shot prompt + 待抽取文本>"},
    ],
    n=1,
    response_format={"type": "json_object"},   # 因 use_schema_constraints=False，走此分支而非 json_schema
)
```

### 3.4 持久化 / 可视化函数参数

| 函数 | 参数 | 本次实测值 |
|---|---|---|
| `lx.io.save_annotated_documents` | `annotated_documents` | `[result]`（单文档需手动包成 list，函数签名要求 `Iterator[AnnotatedDocument]`） |
| | `output_dir` | `langextract_src/output/` |
| | `output_name` | `"extraction_results.jsonl"`（默认 `"data.jsonl"`） |
| `lx.visualize` | `data_source` | JSONL 文件路径字符串（也支持直接传 `AnnotatedDocument` 对象，未测） |
| | `show_legend` / `gif_optimized` | 均未覆盖，用默认值 `True` |

---

## 4. 本地实际生成文件的完整清单

以下为本次 MVP（模拟病历文本，161 字符，2 个可抽取实体）实测生成的**全部文件**：

| 文件名 | 大小 | 内容摘要 |
|---|---|---|
| `langextract_src/output/extraction_results.jsonl` | 845 字节，1 行 JSON（末尾含换行） | 单个 `AnnotatedDocument`：2 个 `Extraction`（`Metformin`、`Lisinopril`），均 `alignment_status="match_exact"` |
| `langextract_src/output/visualization.html` | 8,069 字节 | HTML 片段（无 `<html>` 外壳），含内联 CSS + 2 条实体的高亮动画数据 |

**文件数量对比**（本次未使用官方文档描述的其他输出形态）：

| | 源码调研文档描述的可能输出 | 本次 MVP 实际产出 |
|---|---|---|
| JSONL | ✅ 支持（`io.save_annotated_documents`） | ✅ 1 个文件，1 条记录 |
| HTML 可视化 | ✅ 支持（`lx.visualize`） | ✅ 1 个文件（片段，非完整文档） |
| 图片/表格截图 | ❌ 不支持（LangExtract 是纯文本 pipeline，见 [`LANGExtract_Specification.md` §2.3](./LANGExtract_Specification.md#23-明确不支持的类型)） | 未产出，符合预期 |
| 中间分块文件（per-chunk） | 未在源码调研文档中提及会落盘 | 未产出——`chunking` 全程在内存中进行，不写中间文件 |

结论：与 MinerU 不同，LangExtract 是**纯内存 pipeline**，本地落盘文件只有最终结果这两类（JSONL + 可选 HTML），没有 MinerU 那种"任务 UUID 前缀的多文件 ZIP 输出"模式。

---

## 5. 遗留问题与后续验证建议

1. `use_schema_constraints=True`（默认值）在 DeepSeek 兼容端点下是否可用（即 DeepSeek 是否支持 OpenAI 的 strict `json_schema` response_format）——本次为规避风险显式关闭，未实测验证，需要单独一次对照测试。
2. 未测试 `Document` 可迭代对象（多文档批量）输入路径，仅验证了单字符串输入 → 单 `AnnotatedDocument` 的路径。
3. 未测试 `extraction_passes > 1` 的多轮抽取合并逻辑，也未测试触发真实分块（`max_char_buffer` 限制）的长文本场景——本次输入仅 161 字符，远低于默认 1000 字符的分块阈值。
4. 未测试 `fetch_urls=True`（URL 输入）与 CSV `Dataset` 加载路径。
5. 未对照测试 Gemini / Ollama 两个内置 Provider——Ollama 路径尤其值得后续验证，因其"不支持 `output_schema`"这一限制与本次 DeepSeek 遇到的 schema 兼容性问题性质类似，可以互相参照。
6. `visualization.html` 片段在无 IPython 环境下的返回类型（裸字符串）已确认，但未测试安装 IPython 后 `lx.visualize()` 返回 `IPython.display.HTML` 对象时的 `.data` 属性访问路径是否与本次代码兼容（本次代码已用 `hasattr` 做了兼容判断，但未实际触发该分支）。

---

## 附录：本文档与初版文档的关系

- 初版 [`LANGExtract_Specification.md`](./LANGExtract_Specification.md) 保留不变，作为"源码调研、未跑通真实 LLM 调用"的历史记录，其 Pipeline 总览、输入/输出数据结构定义仍然准确，可作为 API 签名参考。
- 本文档（v1.0）补充的是**真实运行时行为**：cwd 命名空间坑、第三方 OpenAI 兼容 Provider 接入方式、`use_schema_constraints` 兼容性风险、实测字段顺序/索引起始值、HTML 产物的真实结构。后续如需验证 LangExtract 行为，应优先参考本文档；仅在本文档未覆盖的 API 签名细节上，才回退参考初版文档。
