# MinerU 文档解析规范文档

> **版本**: 基于 MinerU API v4（精准解析）  
> **官方文档**: <https://mineru.net/apiManage/docs>  
> **输出格式参考**: <https://opendatalab.github.io/MinerU/reference/output_files/>  
> **方案**: 云端 API（Bearer Token 认证）

---

## 目录

1. [支持的原始输入文件格式](#1-支持的原始输入文件格式)
2. [云端 API 输出格式：完整文件与字段说明](#2-云端-api-输出格式完整文件与字段说明)
   - [2.1 输出文件清单](#21-输出文件清单)
   - [2.2 content_list.json — 内容列表（核心抽取源）](#22-content_listjson--内容列表核心抽取源)
   - [2.3 middle.json — 中间处理结果（布局信息）](#23-middlejson--中间处理结果布局信息)
   - [2.4 model.json — 模型推理结果](#24-modeljson--模型推理结果)
   - [2.5 full.md — Markdown 解析结果](#25-fullmd--markdown-解析结果)
3. [文档解析后的布局信息详解](#3-文档解析后的布局信息详解)
4. [MVP 执行的必要与必须字段](#4-mvp-执行的必要与必须字段)

---

## 1. 支持的原始输入文件格式

### 1.1 精准解析 API（v4）— 全量支持

| 类别 | 扩展名 | 说明 |
|---|---|---|
| **PDF** | `.pdf` | 核心格式，支持 OCR、公式、表格 |
| **图片** | `.png`, `.jpg`, `.jpeg`, `.jp2`, `.webp`, `.gif`, `.bmp` | 自动走 OCR 识别 |
| **Word 文档** | `.doc`, `.docx` | 新旧版本均支持 |
| **PowerPoint** | `.ppt`, `.pptx` | 新旧版本均支持 |
| **Excel 表格** | `.xls`, `.xlsx` | 新旧版本均支持 |
| **HTML** | `.html` | 需指定 `model_version: "MinerU-HTML"` |

### 1.2 文件限制

| 限制项 | 值 |
|---|---|
| 单文件大小上限 | **200 MB** |
| 单文件页数上限 | **200 页** |
| 批量提交数量 | 文件上传模式 ≤ 200 个；URL 批量 ≤ 50 个 |
| 每日高优先级配额 | 1000 页/账号 |

### 1.3 关键参数

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `model_version` | string | `"pipeline"` | `"vlm"`（推荐，更准确）或 `"pipeline"` |
| `is_ocr` | bool | `false` | 扫描件/图片需开启 |
| `enable_formula` | bool | `true` | 数学公式识别（LaTeX 输出） |
| `enable_table` | bool | `true` | 表格识别 |
| `language` | string | `"ch"` | 文档语言，支持 50+ 语种 |
| `extra_formats` | [string] | — | 额外导出：`docx`, `html`, `latex` |
| `page_ranges` | string | — | 页码范围，如 `"2,4-6"` |

---

## 2. 云端 API 输出格式：完整文件与字段说明

### 2.1 输出文件清单

精准解析 API 完成后返回一个 **ZIP 压缩包**（`full_zip_url`），内含以下文件：

```
{original_filename}/
├── full.md                          # Markdown 解析结果
├── {filename}_content_list.json     # 内容列表（按阅读顺序）
├── {filename}_content_list_v2.json  # 内容列表 v2（按页分组，v3.0+）
├── {filename}_model.json            # 模型推理结果
├── {filename}_middle.json           # 中间处理结果（布局信息）
├── {filename}_layout.pdf            # 布局可视化（调试用）
├── {filename}_span.pdf              # Span 可视化（pipeline 后端）
└── images/                          # 提取的图片/表格/公式截图
    ├── ... .png/.jpg
```

### 2.2 content_list.json — 内容列表（核心抽取源）

**定位**：这是 GraphRAG 数值提取的**首选数据源**。按阅读顺序排列所有识别内容块。

#### 顶层结构

```json
// 类型：list[dict] — 按阅读顺序排列的内容块列表
[
  { "type": "text", "text": "...", "bbox": [x0,y0,x1,y1], "page_idx": 0, ... },
  { "type": "table", "table_body": "<table>...", "bbox": [...], "page_idx": 0, ... },
  ...
]
```

#### 所有块共有字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | 内容类型（见下表） |
| `bbox` | array[4] int | 边界框 `[x0, y0, x1, y1]`，坐标归一化到 **0–1000** 范围 |
| `page_idx` | int | 所在页码，从 0 开始 |

#### 块类型枚举（content_list.json，pipeline 后端）

| type 值 | 含义 | 特色字段 |
|---|---|---|
| `text` | 正文/标题 | `text`, `text_level` |
| `image` | 图片 | `img_path`, `image_caption`, `image_footnote` |
| `table` | 表格 | `table_body` (HTML), `img_path`, `table_caption`, `table_footnote` |
| `chart` | 图表 | `img_path`, `sub_type` |
| `equation` | 行间公式 | `text` (LaTeX), `text_format: "latex"`, `img_path` |
| `code` | 代码块 | `sub_type`, `code_body`, `code_caption`, `code_footnote` |
| `list` | 列表 | `sub_type`, `list_items` |
| `header` | 页眉 | `text`（页面辅助块） |
| `footer` | 页脚 | `text`（页面辅助块） |
| `page_number` | 页码 | `text`（页面辅助块） |
| `aside_text` | 边注 | `text`（页面辅助块） |
| `page_footnote` | 页脚注 | `text`（页面辅助块） |

#### text 块详细字段

```json
{
  "type": "text",
  "text": "第三章 实验结果分析",
  "text_level": 1,
  "bbox": [100, 200, 900, 250],
  "page_idx": 3
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `text` | string | ✅ | 文本内容 |
| `text_level` | int | 否 | 标题层级：`1`=一级标题，`2`=二级标题...；缺失或 `0`=正文 |
| `bbox` | array[4] int | ✅ | 坐标 `[x0, y0, x1, y1]`，范围 0–1000 |
| `page_idx` | int | ✅ | 页码 |

#### table 块详细字段

```json
{
  "type": "table",
  "table_body": "<table><tr><td>参数</td><td>值</td></tr>...</table>",
  "table_caption": ["表 2-1 实验参数配置"],
  "table_footnote": ["数据来源：2025 年度报告"],
  "img_path": "images/table_3_0.png",
  "bbox": [50, 300, 950, 600],
  "page_idx": 3
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `table_body` | string | ✅ | **HTML 格式**的表格内容 — 这是 RAG 数值提取的核心字段 |
| `table_caption` | list[string] | 否 | 表格标题 |
| `table_footnote` | list[string] | 否 | 表格脚注 |
| `img_path` | string | ✅ | 表格截图的相对路径 |

#### image 块详细字段

```json
{
  "type": "image",
  "img_path": "images/image_2_0.png",
  "image_caption": ["图 1-1 系统架构图"],
  "image_footnote": [],
  "bbox": [100, 150, 900, 550],
  "page_idx": 2
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `img_path` | string | ✅ | 图片文件的相对路径 |
| `image_caption` | list[string] | 否 | 图片标题文本数组 |
| `image_footnote` | list[string] | 否 | 图片脚注文本数组 |
| `sub_type` | string | 否 | 视觉子类型，如 `"seal"`（印章） |

#### equation 块详细字段

```json
{
  "type": "equation",
  "text": "$$E = mc^2$$",
  "text_format": "latex",
  "img_path": "images/equation_3_1.png",
  "bbox": [200, 400, 800, 460],
  "page_idx": 3
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `text` | string | ✅ | **LaTeX 格式**的公式文本，包裹在 `$$...$$` 中 |
| `text_format` | string | ✅ | 固定值 `"latex"` |
| `img_path` | string | ✅ | 公式截图的相对路径 |

#### code 块详细字段（VLM 后端）

```json
{
  "type": "code",
  "sub_type": "code",
  "code_body": "def main():\n    print('hello')",
  "code_caption": ["代码 3-1 示例"],
  "bbox": [100, 500, 900, 700],
  "page_idx": 4
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `sub_type` | string | ✅ | `"code"` 或 `"algorithm"` |
| `code_body` | string | ✅ | 代码文本内容 |
| `code_caption` | list[string] | 否 | 代码标题 |
| `code_footnote` | list[string] | 否 | 代码脚注 |

#### list 块详细字段（VLM 后端）

```json
{
  "type": "list",
  "sub_type": "text",
  "list_items": ["第一条内容", "第二条内容", "第三条内容"],
  "bbox": [100, 300, 900, 500],
  "page_idx": 2
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `sub_type` | string | 否 | `"text"`（普通列表）或 `"ref_text"`（参考文献列表） |
| `list_items` | array[string] | ✅ | 列表项文本数组 |

---

### 2.3 middle.json — 中间处理结果（布局信息）

**定位**：提供**最详细的布局结构**，是所有输出中布局信息最丰富的文件。适合需要精确位置信息的场景。

#### 顶层结构

```json
{
  "pdf_info": [ ... ],
  "_backend": "pipeline",
  "_version_name": "3.0.0"
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `pdf_info` | list[dict] | 逐页解析结果数组 |
| `_backend` | string | 解析模式：`"pipeline"`, `"vlm"`, `"office"` |
| `_version_name` | string | MinerU 版本号 |

#### 每页结构（`pdf_info[i]`）

```json
{
  "page_idx": 0,
  "page_size": [595.0, 842.0],
  "preproc_blocks": [ ... ],
  "para_blocks": [ ... ],
  "images": [ ... ],
  "tables": [ ... ],
  "interline_equations": [ ... ],
  "discarded_blocks": [ ... ],
  "layout_bboxes": [ ... ]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `page_idx` | int | 页码，从 0 开始 |
| `page_size` | array[2] float | 页面尺寸 `[width, height]`（绝对像素值） |
| `preproc_blocks` | list[dict] | PDF 预处理后的中间结果（未分段） |
| `para_blocks` | list[dict] | **分段后的内容块**（最终结果，推荐使用） |
| `images` | list[dict] | 图片块信息 |
| `tables` | list[dict] | 表格块信息 |
| `interline_equations` | list[dict] | 行间公式块信息 |
| `discarded_blocks` | list[dict] | 被丢弃的块（页眉/页脚/页码等） |
| `layout_bboxes` | list[dict] | 布局边界框 + 分类标签 |
| `_layout_tree` | list | 布局树（部分后端） |

#### para_blocks 块层级结构

```
Level 1 块: table | image | chart
  └── Level 2 块: table_body | table_caption | image_body | text | title | ...
      └── lines: line[]
          └── spans: span[]
```

#### Level 1 块字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | `"table"`, `"image"`, `"chart"` |
| `bbox` | array[4] float/int | 包围盒 `[x0, y0, x1, y1]`，**绝对像素坐标** |
| `blocks` | list[dict] | 包含的 Level 2 块列表 |

#### Level 2 块字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | 块类型（见下表） |
| `bbox` | array[4] float/int | 包围盒 `[x0, y0, x1, y1]`，绝对像素坐标 |
| `lines` | list[dict] | 包含的行列表 |

#### Level 2 块类型枚举

| type 值 | 说明 |
|---|---|
| `text` | 正文段落 |
| `title` | 标题 |
| `index` | 索引项 |
| `list` | 列表 |
| `image_body` | 图片主体 |
| `image_caption` | 图片标题 |
| `image_footnote` | 图片脚注 |
| `table_body` | 表格主体 |
| `table_caption` | 表格标题 |
| `table_footnote` | 表格脚注 |
| `chart_body` | 图表主体 |
| `chart_caption` | 图表标题 |
| `chart_footnote` | 图表脚注 |
| `interline_equation` | 行间公式 |
| `code` | 代码块（VLM） |
| `code_body` | 代码主体（VLM） |
| `code_caption` | 代码标题（VLM） |

#### Line（行）结构

| 字段 | 类型 | 说明 |
|---|---|---|
| `bbox` | array[4] float/int | 行的包围盒 `[x0, y0, x1, y1]` |
| `spans` | list[dict] | 行内的 Span 列表 |

#### Span（文本片段）结构

| 字段 | 类型 | 说明 |
|---|---|---|
| `bbox` | array[4] float/int | Span 包围盒 `[x0, y0, x1, y1]` |
| `type` | string | Span 类型：`"text"`, `"image"`, `"inline_equation"`, `"interline_equation"` |
| `content` | string | 文本内容（text span） |
| `image_path` | string | 图片路径（image span） |
| `score` | float | 置信度分数 |

#### layout_bboxes 布局分类字段

```json
{
  "layout_bbox": [100, 200, 900, 400],
  "layout_label": "text",
  "sub_layout": [
    { "layout_bbox": [100, 200, 900, 280], "layout_label": "title" },
    { "layout_bbox": [100, 280, 900, 400], "layout_label": "text" }
  ]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `layout_bbox` | array[4] int | 布局区域包围盒 `[x0, y0, x1, y1]` |
| `layout_label` | string | 布局分类标签（`"text"`, `"title"`, `"table"`, `"image"`, `"equation"` 等） |
| `sub_layout` | list[dict] | 子布局区域（嵌套结构） |

---

### 2.4 model.json — 模型推理结果

**定位**：原始模型检测结果，适合调试和自定义后处理。

#### Pipeline 后端

```json
[
  {
    "cls_id": 1,
    "label": "text",
    "score": 0.98,
    "bbox": [100, 200, 900, 400],
    "index": 0
  }
]
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `cls_id` | int | 分类 ID |
| `label` | string | 语义分类标签 |
| `score` | float | 置信度 0–1 |
| `bbox` | array[4] float/int | `[x0, y0, x1, y1]` 绝对像素坐标，原点左上角 |
| `index` | int | 阅读顺序索引 |

#### VLM 后端

```json
[
  [
    {
      "type": "title",
      "bbox": [0.1, 0.05, 0.9, 0.1],
      "angle": 0,
      "score": 0.95,
      "content": "第一章 绪论",
      "block_tags": null,
      "content_tags": null,
      "format": null
    }
  ]
]
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | 内容类型（`text`, `title`, `table`, `image`, `equation` 等） |
| `bbox` | array[4] float | `[x0, y0, x1, y1]` **归一化百分比 `[0,1]`** |
| `angle` | int | 旋转角度：`0`, `90`, `180`, `270` |
| `score` | float/null | 置信度 |
| `content` | string | 文本内容 |
| `block_tags` | any/null | 块级标签 |
| `format` | any/null | 格式化信息 |
| `content_tags` | any/null | 内容级标签 |

---

### 2.5 full.md — Markdown 解析结果

**定位**：人类可读的完整解析输出，适合直接作为 LangExtract 的文本输入。

#### 格式特征

- 标题使用 `#` 语法（`#`, `##`, `###`...），层级来自 `text_level`
- 表格以 Markdown 表格或 HTML `<table>` 形式输出
- 公式以 LaTeX `$$...$$` 或 `$...$` 形式输出
- 图片以 `![caption](path)` 形式输出
- 多模态模式下，图表会在截图后附加 `<details>` 折叠块展示原始内容

#### 内容顺序

按原始文档阅读顺序排列，所有页面的内容合并为一个 Markdown 文件。

---

## 3. 文档解析后的布局信息详解

> **核心应用场景**：在 GraphRAG 中精准提取表格数值、图表数据、公式结果时，布局信息用于定位、过滤和验证。

### 3.1 三套坐标体系对比

| 坐标来源 | 文件 | 坐标范围 | 原点 | 适用场景 |
|---|---|---|---|---|
| 绝对像素坐标 | `middle.json` 的 `preproc_blocks` / `para_blocks` | 实际页面像素值 | 左上角 | 精确位置计算 |
| 归一化 0–1000 | `content_list.json` | `[0, 1000]` | 左上角 | **推荐用于数值提取**，与页面尺寸解耦 |
| 百分比 `[0,1]` | VLM 后端 `model.json` | `[0.0, 1.0]` | 左上角 | 模型原生输出 |

### 3.2 bbox 坐标格式

所有 bbox 格式统一为：

```
[x0, y0, x1, y1]

x0: 左边界
y0: 上边界
x1: 右边界
y1: 下边界
```

- `width = x1 - x0`
- `height = y1 - y0`
- 原点在页面**左上角**

### 3.3 页面空间位置关系判断

利用 `content_list.json` 的 bbox（0–1000 归一化坐标），可以精确判断：

#### 同一页面内的位置关系

```
┌─────────────────────────────────────┐
│ y=0                                 │
│  ┌──────────┐  ┌──────────┐        │  ← header / aside_text 区
│  │ 页眉     │  │  边注    │        │
│  └──────────┘  └──────────┘        │
│  ┌──────────────────────────┐       │
│  │  标题 (text_level=1)     │       │  ← 左上区域
│  └──────────────────────────┘       │
│  ┌──────────────────────────┐       │
│  │  正文段落                │       │
│  │  (text, text_level=0)    │       │  ← 中部区域
│  └──────────────────────────┘       │
│  ┌────────────┐ ┌──────────┐       │
│  │  表格      │ │  图表    │       │  ← 表格/图表区域
│  │  (table)   │ │  (chart) │       │
│  └────────────┘ └──────────┘       │
│  ┌──────────────────────────┐       │
│  │  页脚 (footer)           │       │  ← 底部区域
│  └──────────────────────────┘       │
│ y=1000                              │
└─────────────────────────────────────┘
```

#### 判断规则

```python
def get_region(bbox, page_height=1000):
    """基于 bbox 判断块在页面中的区域"""
    x0, y0, x1, y1 = bbox
    center_y = (y0 + y1) / 2

    if y1 < 80:   return "header"       # 顶部 8%
    if y0 > 920:  return "footer"       # 底部 8%
    if x1 < 150:  return "aside_left"   # 左侧 15%
    if x0 > 850:  return "aside_right"  # 右侧 15%

    if center_y < 250: return "top"     # 上半部分
    if center_y > 750: return "bottom"  # 下半部分
    return "middle"                      # 中间区域
```

#### 块之间的空间关系

```python
def is_above(block_a, block_b):
    """A 是否在 B 上方"""
    return block_a["bbox"][3] < block_b["bbox"][1]  # A下边界 < B上边界

def is_adjacent(block_a, block_b, threshold=50):
    """A 和 B 是否相邻（垂直间距 < threshold）"""
    gap = block_b["bbox"][1] - block_a["bbox"][3]
    return 0 <= gap <= threshold

def same_row(block_a, block_b, threshold=20):
    """A 和 B 是否在同一水平行"""
    return abs(block_a["bbox"][1] - block_b["bbox"][1]) <= threshold
```

### 3.4 基于布局的数值精准提取策略

#### 策略 1：表格数值提取（最可靠）

```python
# 从 content_list.json 中提取所有 table 块
for block in content_list:
    if block["type"] == "table":
        html_table = block["table_body"]    # HTML 格式
        caption = block.get("table_caption") # 表格标题（定位用）
        page = block["page_idx"]
        bbox = block["bbox"]

        # 解析 HTML 表格提取单元格数值
        # 配合 caption 文本匹配确定目标表格
```

#### 策略 2：标题关联的数值提取

```python
# 利用 text_level 层级关系
# 标题 (text_level=1) → 子标题 (text_level=2) → 正文内容 (text_level=0)
for i, block in enumerate(content_list):
    if block["type"] == "text" and block.get("text_level") == 2:
        if "财务指标" in block["text"]:
            # 向后扫描直到下一个同级/上级标题
            # 提取中间的 table 和 text 块
            for next_block in content_list[i+1:]:
                if next_block.get("text_level", 0) <= 2:
                    break
                extract_values(next_block)
```

#### 策略 3：空间邻近性关联

```python
# 将 table_caption 与其 table_body 关联
# 利用 bbox 垂直相邻关系
for i, block in enumerate(content_list):
    if block["type"] == "text" and block.get("text") and "表" in block["text"]:
        # 查找下方最近的 table 块
        for j in range(i+1, min(i+5, len(content_list))):
            if content_list[j]["type"] == "table":
                if is_adjacent(block, content_list[j]):
                    # 标题与表格匹配成功
                    break
```

### 3.5 reading order（阅读顺序）

- `content_list.json` 中的数组索引 = 阅读顺序（已自动排序）
- `model.json`（pipeline）中的 `index` 字段显式标记阅读顺序
- `layout.pdf` 可视化中每个检测框的**右上角数字**即为阅读序号

---

## 4. MVP 执行的必要与必须字段

### 4.1 执行 GraphRAG MVP 的最小数据流

```
输入文件 (PDF/DOCX/XLSX/PNG...)
  │
  ▼
[MinerU 精准解析 API]
  POST /api/v4/extract/task
  │
  ▼
输出 ZIP 包 ← 以下为 MVP 必需文件
  │
  ├── ✅ content_list.json    ← 核心数据源
  ├── ✅ full.md               ← LangExtract 文本输入
  └── ⚠️ middle.json           ← 精确布局定位（进阶需要）
```

### 4.2 MVP 必须字段清单

以下字段是执行 GraphRAG 文档解析 + 数值抽取的**最小必需字段集**。

#### 从 API 响应中获取（任务状态与结果 URL）

| 字段 | 用途 | 优先级 |
|---|---|---|
| `state` | 判断任务是否完成：`"done"`, `"running"`, `"failed"` | 🔴 必须 |
| `full_zip_url` | 结果 ZIP 下载地址 | 🔴 必须 |
| `task_id` | 任务唯一标识 | 🔴 必须 |
| `err_msg` | 失败时的错误信息 | 🟡 推荐 |
| `extract_progress.extracted_pages` | 已解析页数 | 🟡 推荐 |
| `extract_progress.total_pages` | 总页数 | 🟡 推荐 |

#### 从 content_list.json 中获取（数值提取核心）

| 字段 | 用途 | 优先级 |
|---|---|---|
| `type` | 区分 text / table / image / equation / chart / list / code | 🔴 必须 |
| `page_idx` | 定位内容所在页 | 🔴 必须 |
| `bbox` | 空间定位，判断块之间的位置关系 | 🔴 必须 |
| `text`（text 块） | 段落/标题文本 → 送入 LangExtract 做实体抽取 | 🔴 必须 |
| `text_level`（text 块） | 标题层级，构建文档结构树 | 🟡 推荐 |
| `table_body`（table 块） | HTML 表格 → 结构化数值提取 | 🔴 必须 |
| `table_caption`（table 块） | 表格标题 → 语义匹配目标表格 | 🟡 推荐 |
| `text`（equation 块） | LaTeX 公式 → 公式语义提取 | 🟡 推荐 |
| `img_path`（image/table/equation 块） | 图片路径 → 多模态模型处理 | 🟢 可选 |
| `image_caption`（image 块） | 图片标题 → 图片语义定位 | 🟢 可选 |
| `list_items`（list 块） | 结构化列表内容 | 🟡 推荐 |

#### 从 full.md 中获取（LangExtract 输入）

| 用途 | 优先级 |
|---|---|
| 完整文档的 Markdown 文本 → 作为 `lx.extract(text_or_documents=md_text)` 的输入 | 🔴 必须 |

#### 从 middle.json 中获取（精确布局，进阶阶段需要）

| 字段 | 用途 | 优先级 |
|---|---|---|
| `pdf_info[].page_idx` | 页码 | 🔴 必须 |
| `pdf_info[].page_size` | 页面尺寸 `[width, height]` | 🟡 推荐 |
| `pdf_info[].para_blocks` | 分段后的内容块（含 line → span 层级） | 🟡 推荐 |
| `pdf_info[].layout_bboxes[].layout_label` | 布局分类标签 | 🟡 推荐 |
| `span.content` | 最小粒度的文本片段 + 精确 bbox | 🟢 可选 |
| `pdf_info[].discarded_blocks` | 被丢弃的页眉/页脚/页码 | 🟢 可选 |

### 4.3 MVP 字段分级决策表

| 等级 | 含义 | 使用场景 |
|---|---|---|
| 🔴 **必须** | 缺少则 MVP 无法运行 | 文档解析、文本提取、表格数值提取 |
| 🟡 **推荐** | 显著提升效果 | 结构感知抽取、标题-内容关联、布局验证 |
| 🟢 **可选** | MVP 阶段可跳过，后续迭代加入 | 多模态图片理解、页眉页脚过滤、调试可视化 |

### 4.4 MVP 最小可行调用示例

```python
import requests
import time
import zipfile
import json

# 1. 提交解析任务
response = requests.post(
    "https://mineru.net/api/v4/extract/task",
    headers={"Authorization": "Bearer YOUR_TOKEN"},
    json={
        "url": "https://example.com/document.pdf",
        "model_version": "vlm",        # 推荐 VLM 后端
        "enable_formula": True,
        "enable_table": True,
        "language": "ch",
        "is_ocr": False,
    },
)
task_id = response.json()["data"]["task_id"]

# 2. 轮询直到完成
while True:
    r = requests.get(
        f"https://mineru.net/api/v4/extract/task/{task_id}",
        headers={"Authorization": "Bearer YOUR_TOKEN"},
    )
    data = r.json()["data"]
    if data["state"] == "done":
        zip_url = data["full_zip_url"]
        break
    elif data["state"] == "failed":
        raise Exception(f"解析失败: {data.get('err_msg')}")
    time.sleep(3)

# 3. 下载并提取 MVP 必需文件
import io
zip_data = requests.get(zip_url).content
with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
    # 🔴 必须
    content_list = json.loads(zf.read("{name}_content_list.json"))
    full_md = zf.read("full.md").decode("utf-8")

    # 🟡 推荐（进阶阶段）
    # middle = json.loads(zf.read("{name}_middle.json"))

# 4. 送入 LangExtract
import langextract as lx
result = lx.extract(
    text_or_documents=full_md,
    prompt_description="提取文档中的关键数值、指标和实体...",
    examples=[...],
    model_id="gemini-3.5-flash",
)
```

---

## 附录：关键 API 端点速查

| 操作 | 方法 | 端点 |
|---|---|---|
| 提交单个 URL 任务 | POST | `/api/v4/extract/task` |
| 查询任务状态 | GET | `/api/v4/extract/task/{task_id}` |
| 申请批量上传链接 | POST | `/api/v4/file-urls/batch` |
| 批量提交 URL 任务 | POST | `/api/v4/extract/task/batch` |
| 批量查询结果 | GET | `/api/v4/extract-results/batch/{batch_id}` |

所有请求 Header：`Authorization: Bearer {token}`
