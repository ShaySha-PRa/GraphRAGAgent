# LangExtract 核心规范文档

> **版本**: v1.6.0  
> **源码仓库**: <https://github.com/google/langextract>  
> **源码路径**: `langextract/langextract/`  
> **核心入口**: `langextract/__init__.py` → `lx.extract()`

---

## 目录

1. [Pipeline 总览](#1-pipeline-总览)
2. [输入规范](#2-输入规范)
3. [文本模型接入规范](#3-文本模型接入规范)
4. [输出数据格式规范](#4-输出数据格式规范)

---

## 1. Pipeline 总览

LangExtract 的 `lx.extract()` 是一条**纯文本→结构化实体**的信息抽取流水线，由以下阶段串行组成：

```
输入 (text / Document / CSV / URL)
  │
  ▼
[IO 层]  text_or_documents 预处理
  │  - 纯文本字符串：直接使用
  │  - URL (fetch_urls=True)：HTTP GET 下载为文本
  │  - Iterable[Document]：逐条处理
  ├────────────────────────────── 源码: extraction.py:45, 252-256
  │
  ▼
[Prompt 层]  构建 few-shot prompt
  │  - prompt_description → 抽取任务指令
  │  - examples (ExampleData) → few-shot 样本
  │  - 模板渲染: QAPromptGenerator → Q: text / A: <format>
  ├────────────────────────────── 源码: prompting.py:84-138
  │
  ▼
[Chunking 层]  Tokenize → 句子感知分块
  │  - RegexTokenizer (默认) / UnicodeTokenizer
  │  - SentenceIterator: 按标点 + 换行断句
  │  - ChunkIterator: max_char_buffer 控制 chunk 大小
  ├────────────────────────────── 源码: chunking.py:343-506, tokenizer.py:180-506
  │
  ▼
[Inference 层]  并行 LLM 推理
  │  - 批量并发 (batch_length + max_workers)
  │  - 多轮抽取 (extraction_passes ≥ 2)
  │  - Provider: Gemini / OpenAI / Ollama / 自定义插件
  ├────────────────────────────── 源码: annotation.py:285-445, providers/
  │
  ▼
[Resolver 层]  解析 → 对齐 (Grounding)
  │  - 从 LLM 输出解析 JSON/YAML
  │  - 精确/模糊匹配将 extraction_text 对齐到原文字符位置
  ├────────────────────────────── 源码: resolver.py
  │
  ▼
[输出]  AnnotatedDocument
  │  - document_id + text + extractions (含 char_interval 溯源)
  │  - 可序列化为 JSONL / 生成交互式可视化 HTML
  └────────────────────────────── 源码: core/data.py:205-257, io.py:85-141
```

**关键设计边界**（都在 `extraction.py:45-196` 主函数 `extract()` 中体现）：
- 输入必须是**纯文本**，不进行 PDF/DOCX 等富格式解析
- 模型必须是**文本 LLM**（text-in, text-out），不涉及多模态或 Embedding
- 输出是**扁平实体列表**，不是图结构（无节点/边/三元组）
- 不依赖任何外部数据库（关系型/向量/图）

---

## 2. 输入规范

### 2.1 主入口参数

```python
result = lx.extract(
    text_or_documents: str | Iterable[Document],  # 必填：输入文本
    prompt_description: str | None = None,         # 抽取任务描述
    examples: Sequence[ExampleData] | None = None, # few-shot 样本
    model_id: str = "gemini-3.5-flash",            # 模型 ID
    # ... 其他配置参数
)
```

> 源码: `extraction.py:45-75`

### 2.2 支持的输入类型

#### 类型 1：纯文本字符串（主要输入方式）

```python
# 直接传字符串
result = lx.extract(
    text_or_documents="Aspirin 100mg daily for hypertension.",
    prompt_description=prompt,
    examples=examples,
)
```

- 底层走 `annotate_text()`（`annotation.py:532-625`）
- 返回值是单个 `AnnotatedDocument`
- 适用场景：短文本、单一文档

> 源码: `extraction.py:388-403`

#### 类型 2：Document 可迭代对象

```python
from langextract.core.data import Document

documents = [
    Document(text="报告一内容...", document_id="report_001"),
    Document(text="报告二内容...", document_id="report_002"),
]
results = lx.extract(text_or_documents=documents, ...)
```

- 底层走 `annotate_documents()`（`annotation.py:209-283`）
- 返回值是 `list[AnnotatedDocument]`
- `document_id` 可选，未提供时自动生成为 `doc_{uuid前8位}`
- 支持 `additional_context` 字段为每个文档注入额外 prompt 上下文

> 源码: `core/data.py:129-201`, `extraction.py:404-427`

#### 类型 3：HTTP/HTTPS URL（需显式开启）

```python
result = lx.extract(
    text_or_documents="https://www.gutenberg.org/files/1513/1513-0.txt",
    fetch_urls=True,   # ⚠️ 默认为 False，必须显式开启
    ...
)
```

- 使用 `requests.get()` 下载原始文本（`io.py:265-353`）
- 支持的 Content-Type: `text/*`, `application/json`, `application/xml`
- 支持编码自动检测: UTF-8 → Latin-1 → ASCII → UTF-16
- ⚠️ 安全警告（源码注释 `extraction.py:175-178`）：启用后存在 SSRF 风险，仅在可信来源 + 沙箱环境使用

> 源码: `io.py:226-353`, `extraction.py:252-256`

#### 类型 4：CSV 文件（通过 Dataset 类）

```python
from langextract.io import Dataset

dataset = Dataset(
    input_path=pathlib.Path("data.csv"),
    id_key="report_id",
    text_key="report_text",
)
documents = list(dataset.load(delimiter=","))
```

- 内部使用 `pandas.read_csv()` 读取（`io.py:195-223`）
- 必须指定 `id_key`（文档 ID 列名）和 `text_key`（文本列名）
- 仅支持 `.csv` 扩展名，其他文件类型抛出 `NotImplementedError`

> 源码: `io.py:42-82`

### 2.3 ❌ 明确不支持的类型

| 不支持的类型 | 源码证据 |
|---|---|
| **PDF** | 无任何 PDF 解析库依赖（pypdf、pdfplumber、PyMuPDF 均不存在） |
| **DOCX** | 无 `python-docx` 等依赖 |
| **HTML / Markdown** | 无 HTML 解析器，URL 下载后不解包 HTML 标签 |
| **图片 / 音频 / 视频** | 全局搜索 `multimodal\|image\|vision\|video\|audio\|ocr` → 零结果（与模型无关的除外） |
| **其他二进制格式** | `Document.text` 字段类型为 `str`，无 `bytes` 字段 |

### 2.4 Document 数据结构

```python
# 源码: core/data.py:129-201
@dataclasses.dataclass
class Document:
    text: str                              # 必填：原始文本
    additional_context: str | None = None  # 可选：注入 prompt 的额外上下文
    document_id: str | None = None         # 可选：自动生成 "doc_{8位hex}"

    # 内部字段（自动计算）
    tokenized_text: TokenizedText  # 从 text 自动 tokenize（core/tokenizer.py）
```

### 2.5 输入大小限制

LangExtract **无硬性输入大小限制**，通过分块机制处理长文本：

- `max_char_buffer`（默认 1000）：每个 chunk 的最大字符数，控制单次 LLM 调用的上下文大小
- `extraction_passes`（默认 1）：多轮抽取可提升长文档的召回率
- `batch_length`（默认 10）：批次大小
- `max_workers`（默认 10）：并行度
- `context_window_chars`（默认 None）：跨 chunk 上下文窗口，用于指代消解

> 源码: `chunking.py:343-506`, `extraction.py:55-63`

---

## 3. 文本模型接入规范

### 3.1 模型调用链路

```
lx.extract(model_id="gemini-3.5-flash", ...)
  │
  ▼
factory.ModelConfig(model_id=..., provider_kwargs=...)
  │  源码: factory.py:330-331
  ▼
factory.create_model(config, examples, use_schema_constraints, fence_output, output_schema)
  │  源码: factory.py:194-288
  ▼
providers.router → 自动匹配 provider:
  │  - model_id 包含 "gemini" → GeminiLanguageModel
  │  - model_id 包含 "ollama" → OllamaLanguageModel
  │  - model_id 包含 "gpt" 或 "o1"/"o3"/"o4" → OpenAILanguageModel
  │  - 自定义 provider 通过 entry_points 插件机制注册
  │  源码: providers/patterns.py, providers/router.py
  ▼
BaseLanguageModel.infer(batch_prompts: Sequence[str]) → Iterator[Sequence[ScoredOutput]]
```

### 3.2 内置 Provider（模型提供商）

| Provider | 模块 | 支持模型示例 | 特性 |
|---|---|---|---|
| **Gemini** | `providers/gemini.py` | `gemini-3.5-flash`, `gemini-pro`, `gemini-flash-lite` | 推荐默认值；支持 controlled generation（结构化输出）、Vertex AI Batch API、并行推理 |
| **OpenAI** | `providers/openai.py` | `gpt-4o`, `gpt-4o-mini`, `o3`, `o4-mini` | 需要 `pip install langextract[openai]`；支持 structured outputs / JSON mode；支持 Batch API |
| **Ollama** | `providers/ollama.py` | `gemma2:2b`, 任意 Ollama 模型 | 本地推理，无需 API key；支持 JSON mode；不支持 `output_schema` |

> 源码: `pyproject.toml:94-97` entry_points, `providers/` 目录

### 3.3 BaseLanguageModel 抽象接口

所有 Provider 必须实现此接口：

```python
# 源码: core/base_model.py:32-232
class BaseLanguageModel(abc.ABC):

    @abc.abstractmethod
    def infer(
        self, batch_prompts: Sequence[str], **kwargs
    ) -> Iterator[Sequence[ScoredOutput]]:
        """批量文本输入 → 排序后的文本输出"""

    def infer_batch(self, prompts, batch_size=32) -> list[list[ScoredOutput]]:
        """便捷方法：收集 infer() 所有结果"""

    def parse_output(self, output: str) -> Any:
        """将模型输出解析为 JSON 或 YAML 的 dict/list"""
```

**关键约束**：
- 输入：`batch_prompts: Sequence[str]` — 纯文本 prompt，**不支持图像/音频等多模态输入**
- 输出：`ScoredOutput` 包含 `output: str` 字段 — 纯文本 JSON/YAML 字符串
- 模型需要对 prompt 中的格式指令（Q:/A: 模板 + 格式示例）做出响应

### 3.4 模型接入方式

#### 方式 1：model_id 字符串（推荐）

```python
# Gemini（默认 Provider）
lx.extract(..., model_id="gemini-3.5-flash")

# OpenAI
lx.extract(..., model_id="gpt-4o")

# Ollama 本地模型
lx.extract(..., model_id="gemma2:2b", model_url="http://localhost:11434")
```

Provider 通过 model_id 模式自动匹配（`providers/patterns.py` + `providers/builtin_registry.py`）。

#### 方式 2：ModelConfig 显式指定

```python
from langextract.factory import ModelConfig

lx.extract(
    ...,
    config=ModelConfig(
        model_id="my-custom-model",
        provider="openai",                          # 强制指定 provider
        provider_kwargs={"base_url": "https://...", "api_key": "sk-..."},
    ),
)
```

> 源码: `factory.py:88-108`, `extraction.py:282-297`

#### 方式 3：预配置 model 对象

```python
model = create_gemini_model(...)  # 预先配置好 schema、fence 等
lx.extract(..., model=model)
```

> 源码: `extraction.py:264-281`

### 3.5 API Key 配置

优先级从高到低（`factory.py:164-176`）：

1. **`api_key` 参数**直接传入（不推荐生产环境）
2. **环境变量 `LANGEXTRACT_API_KEY`**
3. **`.env` 文件**中的 `LANGEXTRACT_API_KEY`

对于 Vertex AI：
```python
language_model_params={
    "vertexai": True,
    "project": "your-project-id",
    "location": "global",
}
```

### 3.6 自定义 Provider 插件

```python
# 通过 Python entry_points 注册
# pyproject.toml:
# [project.entry-points."langextract.providers"]
# my_provider = "my_package:MyLanguageModel"
```

> 文档: `langextract/providers/README.md`, 示例: `examples/custom_provider_plugin/`

### 3.7 ❌ 不支持的能力

| 能力 | 状态 | 证据 |
|---|---|---|
| 多模态模型（图像/视频/音频输入） | ❌ | `BaseLanguageModel.infer()` 仅接收 `Sequence[str]` |
| Embedding 模型 | ❌ | 全代码库无任何 embedding 调用 |
| Function Calling / Tool Use | ❌ | 无相关接口 |
| Streaming 输出 | ❌ | `infer()` 返回 `Iterator[Sequence[ScoredOutput]]` 非流式 |
| Token 计数 | ❌ | tokenizer 仅供本地分块/对齐使用，不用于 LLM token 计算 |

---

## 4. 输出数据格式规范

### 4.1 主返回类型：AnnotatedDocument

```python
# 源码: core/data.py:205-257
@dataclasses.dataclass
class AnnotatedDocument:
    document_id: str              # 文档唯一标识
    text: str | None              # 原始文本
    extractions: list[Extraction] # 抽取结果列表
    tokenized_text: TokenizedText # 内部字段，自动从 text 计算
```

- 文本字符串输入 → 返回单个 `AnnotatedDocument`
- Document 可迭代对象输入 → 返回 `list[AnnotatedDocument]`

> 源码: `extraction.py:187-190`, `extraction.py:388-427`

### 4.2 Extraction 实体结构

```python
# 源码: core/data.py:63-127
@dataclasses.dataclass(init=False)
class Extraction:
    extraction_class: str                     # 实体类别，如 "medication"、"character"
    extraction_text: str                      # 抽取的原文文本（verbatim）
    char_interval: CharInterval | None        # 在原文中的字符位置（溯源/Grounding）
        # CharInterval.start_pos: int | None  # 起始位置（inclusive）
        # CharInterval.end_pos: int | None    # 结束位置（exclusive）
    alignment_status: AlignmentStatus | None  # 对齐状态
        # MATCH_EXACT   — 精确匹配
        # MATCH_GREATER — 抽取文本覆盖原文字段
        # MATCH_LESSER  — 抽取文本是原文字段的子集
        # MATCH_FUZZY   — 模糊匹配
    extraction_index: int | None              # 在同一文档中的序号
    group_index: int | None                   # 所属组的索引
    description: str | None                   # 实体描述
    attributes: dict[str, str | list[str]] | None  # 属性键值对
    token_interval: TokenInterval | None      # Token 级位置（内部字段）
```

**关键字段说明**：

| 字段 | 含义 | 示例 |
|---|---|---|
| `extraction_class` | 实体/关系类别 | `"medication"`, `"dosage"`, `"character"` |
| `extraction_text` | 原文中的精确文本片段 | `"Aspirin"`, `"100mg"` |
| `char_interval` | 原文溯源坐标（inclusive, exclusive） | `CharInterval(0, 7)` → 原文第 0-6 字符 |
| `attributes` | 自由键值对属性 | `{"dosage": "100mg", "route": "oral"}` |
| `alignment_status` | 溯源可信度 | `MATCH_EXACT` 表示精确定位成功 |

### 4.3 完整 JSON 示例

```json
{
  "document_id": "doc_a1b2c3d4",
  "text": "Aspirin 100mg daily for hypertension.",
  "extractions": [
    {
      "extraction_class": "medication",
      "extraction_text": "Aspirin",
      "char_interval": {
        "start_pos": 0,
        "end_pos": 7
      },
      "alignment_status": "match_exact",
      "extraction_index": 0,
      "attributes": {
        "dosage": "100mg",
        "frequency": "daily",
        "indication": "hypertension"
      }
    }
  ]
}
```

### 4.4 输出持久化格式

#### JSONL 导出（推荐）

```python
# 源码: io.py:85-141
lx.io.save_annotated_documents(
    [result],
    output_name="extraction_results.jsonl",
    output_dir="./output",
)
```

每行一个 `AnnotatedDocument` 对象（JSON 一行，`ensure_ascii=False`）：

```jsonl
{"document_id":"doc_a1b2c3d4","text":"Aspirin 100mg...","extractions":[...]}
{"document_id":"doc_e5f6g7h8","text":"Metformin 500mg...","extractions":[...]}
```

#### JSONL 导入

```python
# 源码: io.py:144-188
for annotated_doc in lx.io.load_annotated_documents_jsonl("extraction_results.jsonl"):
    for extraction in annotated_doc.extractions:
        print(extraction.extraction_class, extraction.extraction_text)
```

#### 交互式 HTML 可视化

```python
# 源码: visualization.py
html = lx.visualize("extraction_results.jsonl")
with open("visualization.html", "w") as f:
    f.write(html.data if hasattr(html, 'data') else html)
```

生成的 HTML 可在浏览器中交互式浏览每一个抽取结果及其在原文中的位置高亮。

### 4.5 ⚠️ 重要注意事项

1. **`char_interval` 可能为 `None`**：当 LLM 抽取的文本片段无法在原文中定位时（如 LLM 幻觉或从 few-shot 示例中复制的内容），`char_interval = None`。可以用 `[e for e in result.extractions if e.char_interval]` 过滤。

2. **非确定性**：`extraction_index` 由 LLM 输出顺序决定，不同运行结果可能不同。跨运行比较应使用 `char_interval` 或 `extraction_text`。

3. **扁平结构**：抽取结果是 `Extraction` 列表，不包含实体间的显式关系边。关系信息需要通过 `extraction_class`（如 `"relationship"`）和 `attributes` 间接编码。

4. **无全局去重**：每次 `lx.extract()` 调用独立进行，不跨文档进行实体链接或共指消解。`extraction_passes` 的多轮结果通过 `char_interval` 重叠检测进行合并（先到先得策略，`annotation.py:46-84`）。

---

## 附录：关键源码索引

| 组件 | 源码路径 |
|---|---|
| 主入口 `extract()` | `langextract/extraction.py:45-196` |
| 输入预处理 | `langextract/io.py:42-82` (Dataset), `265-353` (URL download) |
| 分块器 | `langextract/chunking.py:343-506` (ChunkIterator) |
| Tokenizer | `langextract/core/tokenizer.py:180-227` (RegexTokenizer), `321-467` (UnicodeTokenizer) |
| Prompt 构建 | `langextract/prompting.py:84-138` (QAPromptGenerator) |
| 标注引擎 | `langextract/annotation.py:163-625` (Annotator) |
| 模型工厂 | `langextract/factory.py:88-288` |
| Provider 路由 | `langextract/providers/router.py` |
| BaseLanguageModel | `langextract/core/base_model.py:32-232` |
| Gemini Provider | `langextract/providers/gemini.py` |
| OpenAI Provider | `langextract/providers/openai.py` |
| Ollama Provider | `langextract/providers/ollama.py` |
| 数据模型 | `langextract/core/data.py` |
| 解析与对齐 | `langextract/resolver.py` |
| JSONL 持久化 | `langextract/io.py:85-188` |
| 可视化 | `langextract/visualization.py` |
| Prompt 校验 | `langextract/prompt_validation.py` |
