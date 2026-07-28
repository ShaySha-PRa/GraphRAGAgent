"""Doc-scoped graph QA agent with structured citations and multi-turn support.

Ported from graphrag_pipeline/graph_qa_agent.py per backend_service_architecture-v1.0.md
§3.4 / §6 and agentic_rag_architecture-v1.0.md §7.

Key differences from the standalone MVP:
1. No module-level globals — tools built per doc_id via load_kg_for_doc().
2. Three bug fixes applied (see inline comments).
3. Structured citations via with_structured_output(AgentAnswer); enrich_citations
   overwrites page_idx/bbox from KG ground truth and applies edge-bbox endpoint fallback.
4. Multi-turn conversation: LangGraph MemorySaver checkpointer per session_id.
"""

from __future__ import annotations

import json
import os
import pathlib
import threading
import uuid
from typing import Literal

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_deepseek import ChatDeepSeek
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

import vector_index

ROOT = pathlib.Path(__file__).resolve().parent.parent

_backend_env = pathlib.Path(__file__).resolve().parent / ".env"
if _backend_env.is_file():
    load_dotenv(_backend_env)
else:
    load_dotenv(ROOT / "langextract_src" / ".env")

# Fix #1: langchain_deepseek expects DEEPSEEK_API_BASE, not DEEPSEEK_BASE_URL
DEEPSEEK_API_BASE = os.getenv("DEEPSEEK_API_BASE", os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"))

llm = ChatDeepSeek(model="deepseek-chat", temperature=0, api_base=DEEPSEEK_API_BASE)

_EDGE_NO_BBOX_NOTE = (
    "关系边协议层无 bbox（见 bridge_pipeline_specification-v1.0.md §3.3.1）；"
    "坐标取自端点节点（若端点亦无坐标则为空）"
)
_EDGE_BOTH_MISSING_NOTE = (
    "关系边协议层无 bbox，且两端节点均无可用 bbox"
    "（见 bridge_pipeline_specification-v1.0.md §3.3.1）"
)

ANSWER_STRUCT_HINT = (
    "请基于以上工具返回的真实数据生成最终回答。"
    "在 citations 中列出你引用的每条数据的 node_id 与正确的 source_kind"
    "（table / graph_node / graph_edge / vector_chunk）。"
    "不要编造 page_idx 或 bbox——后处理会从知识图谱回填真实坐标。"
)

# ── Pydantic models ─────────────────────────────────────────────────


class GradeResult(BaseModel):
    relevant: bool = Field(description="工具返回的结果是否能帮助回答用户的问题")


class Citation(BaseModel):
    source_kind: Literal["graph_node", "graph_edge", "table", "vector_chunk"] = "graph_node"
    page_idx: int | None = None
    bbox: list[int] | None = None
    node_id: str | None = None
    note: str | None = None


class AgentAnswer(BaseModel):
    answer: str = Field(description="基于知识图谱数据生成的最终回答，用中文或英文取决于用户问题语言")
    citations: list[Citation] = Field(default_factory=list, description="回答中引用的所有数据来源")


class AgentState(MessagesState):
    rewrite_count: int
    structured_answer: str
    structured_citations: list[dict]


# ── System prompt ───────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "你是一个知识图谱问答助手。你可以使用以下工具查询知识图谱：\n"
    "- graph_lookup_tool: 查询实体/关系（语义类问题，支持多跳遍历）\n"
    "- table_lookup_tool: 查询表格中的精确数值（数值类问题优先使用这个工具）\n"
    "- vector_search_tool: 语义搜索原始文档文本（用于回答模糊/概念性问题、总结类问题）\n\n"
    "建议使用策略：\n"
    "- 寻找具体实体、数值、关系 → 优先用 graph_lookup_tool / table_lookup_tool\n"
    "- 概念性问题、摘要、背景信息 → 先用 graph_lookup_tool，若无结果再用 vector_search_tool\n\n"
    "工具返回的每条记录都包含 `[id:xxxx]` 标识符。\n"
    "回答时必须基于工具返回的真实数据。如果你的回答引用了某条工具返回的数据，"
    "请在 citations 数组中列出对应的 node_id。对于表格数据（block_type==table），"
    "source_kind 用 'table'；对于关系边，source_kind 用 'graph_edge'；"
    "向量检索段落用 'vector_chunk'；其余用 'graph_node'。\n"
    "如果工具明确说明未找到匹配数据，你必须如实告知用户查不到，绝不能编造答案。"
)


# ── JSONL helpers ───────────────────────────────────────────────────


def load_jsonl(path: pathlib.Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _format_provenance(prov: dict) -> str:
    page_idx = prov.get("page_idx")
    bbox = prov.get("bbox")
    bbox_str = str(bbox) if bbox is not None else "无坐标"
    return f"page_idx={page_idx}, bbox={bbox_str}"


def _format_node(node: dict) -> str:
    nid = node.get("id", "?")
    return f"[id:{nid}] [{node['label']}] {node['name']} ({_format_provenance(node['provenance'])})"


# ── Citation post-processing ────────────────────────────────────────


def _normalize_bbox(bbox) -> list[int] | None:
    if bbox is None:
        return None
    try:
        return [int(v) for v in bbox]
    except (TypeError, ValueError):
        return None


def _prov_from_node(node: dict) -> tuple[int | None, list[int] | None, bool]:
    prov = node.get("provenance") or {}
    page_idx = prov.get("page_idx")
    if page_idx is not None:
        try:
            page_idx = int(page_idx)
        except (TypeError, ValueError):
            page_idx = None
    return page_idx, _normalize_bbox(prov.get("bbox")), prov.get("block_type") == "table"


def _nodes_by_name(nodes: list[dict]) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for n in nodes:
        name = n.get("name") or ""
        if name:
            index.setdefault(name, []).append(n)
    return index


def _endpoint_provenance(
    endpoint_name: str,
    name_index: dict[str, list[dict]],
) -> tuple[int | None, list[int] | None]:
    """Pick the first endpoint node that has a usable bbox; else first with page_idx."""
    matches = name_index.get(endpoint_name) or []
    best_page: int | None = None
    for node in matches:
        page_idx, bbox, _ = _prov_from_node(node)
        if bbox is not None:
            return page_idx, bbox
        if best_page is None and page_idx is not None:
            best_page = page_idx
    return best_page, None


def _resolve_edge_endpoints(
    citation: Citation,
    nodes: list[dict],
    edges: list[dict],
    by_id: dict[str, dict],
    name_index: dict[str, list[dict]],
) -> tuple[int | None, list[int] | None, str]:
    """For graph_edge citations: never invent bbox; prefer endpoint node provenance."""
    candidate_names: list[str] = []

    if citation.node_id and citation.node_id in by_id:
        name = by_id[citation.node_id].get("name") or ""
        if name:
            candidate_names.append(name)
            for edge in edges:
                if edge.get("subject") == name:
                    candidate_names.append(edge.get("object") or "")
                elif edge.get("object") == name:
                    candidate_names.append(edge.get("subject") or "")

    note = citation.note or ""
    for edge in edges:
        subj, obj = edge.get("subject") or "", edge.get("object") or ""
        pred = edge.get("predicate") or ""
        if subj and subj in note:
            candidate_names.extend([subj, obj])
        elif obj and obj in note:
            candidate_names.extend([subj, obj])
        elif pred and pred in note:
            candidate_names.extend([subj, obj])

    seen: set[str] = set()
    page_idx: int | None = None
    bbox: list[int] | None = None
    for name in candidate_names:
        if not name or name in seen:
            continue
        seen.add(name)
        ep_page, ep_bbox = _endpoint_provenance(name, name_index)
        if ep_bbox is not None:
            return ep_page, ep_bbox, _EDGE_NO_BBOX_NOTE
        if page_idx is None and ep_page is not None:
            page_idx = ep_page

    # Fall back to the cited node itself (may still lack bbox)
    if citation.node_id and citation.node_id in by_id:
        page_idx, bbox, _ = _prov_from_node(by_id[citation.node_id])
        if bbox is not None:
            return page_idx, bbox, _EDGE_NO_BBOX_NOTE

    return page_idx, None, _EDGE_BOTH_MISSING_NOTE


def enrich_citations(
    citations: list[Citation],
    nodes: list[dict],
    edges: list[dict],
) -> list[Citation]:
    """Overwrite provenance from KG ground truth; apply edge endpoint bbox fallback.

    Model-supplied page_idx/bbox are never trusted when a matching node exists.
    """
    by_id = {n["id"]: n for n in nodes if n.get("id")}
    name_index = _nodes_by_name(nodes)
    enriched: list[Citation] = []

    for raw in citations:
        c = raw if isinstance(raw, Citation) else Citation.model_validate(raw)

        if c.source_kind == "graph_edge":
            page_idx, bbox, note = _resolve_edge_endpoints(c, nodes, edges, by_id, name_index)
            enriched.append(c.model_copy(update={
                "page_idx": page_idx,
                "bbox": bbox,
                "note": note if not (c.note and "bridge_pipeline" in c.note) else c.note,
            }))
            continue

        if c.node_id and c.node_id in by_id:
            page_idx, bbox, is_table = _prov_from_node(by_id[c.node_id])
            updates: dict = {"page_idx": page_idx, "bbox": bbox}
            if is_table:
                updates["source_kind"] = "table"
            elif c.source_kind == "table" and not is_table:
                updates["source_kind"] = "graph_node"
            enriched.append(c.model_copy(update=updates))
            continue

        # No resolvable node — strip model-invented coordinates
        if c.source_kind != "vector_chunk":
            enriched.append(c.model_copy(update={"page_idx": None, "bbox": None}))
        else:
            enriched.append(c)

    return enriched


def _extract_citations(answer_text: str, nodes: list[dict]) -> list[Citation]:
    """Fallback when structured output fails: match entity names mentioned in the answer.

    Per spec §6.2: table nodes get source_kind='table', others get 'graph_node'.
    """
    name_to_nodes: dict[str, list[dict]] = {}
    for n in nodes:
        name = n.get("name", "")
        if name:
            name_to_nodes.setdefault(name.lower(), []).append(n)

    answer_lower = answer_text.lower()
    cited: list[Citation] = []
    seen_ids: set[str] = set()

    for name_lower, matches in sorted(name_to_nodes.items(), key=lambda x: -len(x[0])):
        if name_lower in answer_lower:
            for node in matches:
                if node["id"] in seen_ids:
                    continue
                seen_ids.add(node["id"])
                page_idx, bbox, is_table = _prov_from_node(node)
                cited.append(Citation(
                    source_kind="table" if is_table else "graph_node",
                    page_idx=page_idx,
                    bbox=bbox,
                    node_id=node["id"],
                ))

    return cited


# ── Tool building (per-doc closure) ─────────────────────────────────


def _build_tools(nodes: list[dict], edges: list[dict], doc_id: str):
    name_index: dict[str, list[dict]] = {}
    for n in nodes:
        name_index.setdefault(n["name"], []).append(n)

    def resolve_endpoint(text: str) -> list[dict]:
        """Exact match first, then substring fallback.  Fix #2: skip empty-name nodes."""
        exact = name_index.get(text)
        if exact:
            return exact
        text_lower = text.lower()
        return [
            n for n in nodes
            if n["name"] and (text_lower in n["name"].lower() or n["name"].lower() in text_lower)
        ]

    @tool
    def graph_lookup_tool(entity_or_question: str, max_hops: int = 1) -> str:
        """在知识图谱中查找与给定实体或问题相关的节点和关系边，支持多跳遍历。
        返回结果包含 node id 用于生成 citations。"""
        matches = resolve_endpoint(entity_or_question)
        if not matches:
            return f"未找到与 '{entity_or_question}' 匹配的图节点。"

        lines = ["匹配到的节点:"]
        for m in matches:
            lines.append("  " + _format_node(m))

        frontier = {m["name"] for m in matches}
        visited_edges = set()
        for hop in range(max_hops):
            hop_edges = []
            for edge in edges:
                key = (edge["subject"], edge["predicate"], edge["object"])
                if key in visited_edges:
                    continue
                if edge["subject"] in frontier or edge["object"] in frontier:
                    hop_edges.append(edge)
                    visited_edges.add(key)
            if not hop_edges:
                break
            lines.append(f"第 {hop + 1} 跳关系边（边永远没有 bbox，见 bridge_pipeline_spec §3.3.1）:")
            next_frontier = set()
            for edge in hop_edges:
                prov_str = _format_provenance(edge["provenance"])
                lines.append(f"  {edge['subject']} --[{edge['predicate']}]--> {edge['object']} ({prov_str})")
                next_frontier.add(edge["subject"])
                next_frontier.add(edge["object"])
            frontier = next_frontier

        return "\n".join(lines)

    @tool
    def table_lookup_tool(row_label: str, metric: str | None = None) -> str:
        """在 Lane A 表格节点中按行标签过滤，用于确切数值查询。无 LLM 参与，无幻觉风险。
        返回结果包含 node id 用于生成 citations。"""
        row_label_lower = row_label.lower()
        metric_lower = metric.lower() if metric else None

        hits = []
        for node in nodes:
            if node.get("provenance", {}).get("block_type") != "table":
                continue
            attrs = node.get("attributes", {})
            node_row = str(attrs.get("row_label", "")).lower()
            node_metric = str(attrs.get("metric", "")).lower()
            if row_label_lower not in node_row and node_row not in row_label_lower:
                continue
            if metric_lower and metric_lower not in node_metric and node_metric not in metric_lower:
                continue
            hits.append(node)

        if not hits:
            suffix = f", metric='{metric}'" if metric else ""
            return f"未在表格数据（Lane A）中找到与 row_label='{row_label}'{suffix} 匹配的记录。"

        lines = ["匹配到的表格记录:"]
        for node in hits:
            lines.append("  " + _format_node(node))
        return "\n".join(lines)

    @tool
    def vector_search_tool(query: str, top_k: int = 5) -> str:
        """在原始文档文本中做语义搜索（基于 embedding 向量相似度）。
        用于回答概念性问题、总结性问题，或当 graph_lookup_tool 和 table_lookup_tool 都无法找到
        所需信息时使用。返回相关文本段落。
        """
        try:
            results = vector_index.search(doc_id, query, top_k=top_k)
        except Exception:
            results = []
        if not results:
            return "未在文档向量索引中找到与查询相关的文本段落。"

        lines = [f"语义搜索结果（共 {len(results)} 条相关段落）:"]
        for i, chunk in enumerate(results, 1):
            lines.append(f"--- 段落 {i} ---")
            lines.append(chunk[:600])
        return "\n".join(lines)

    return [graph_lookup_tool, table_lookup_tool, vector_search_tool]


# ── Agent building ──────────────────────────────────────────────────


def _build_agent(nodes: list[dict], edges: list[dict], doc_id: str, checkpointer: MemorySaver | None = None):
    tools = _build_tools(nodes, edges, doc_id)
    llm_with_tools = llm.bind_tools(tools)

    def generate_query_or_respond(state: AgentState):
        messages = state["messages"]
        if not any(isinstance(m, SystemMessage) for m in messages):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    def route_after_generate(state: AgentState) -> Literal["retrieve", "__end__"]:
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None):
            return "retrieve"
        return END

    def grade_documents(state: AgentState) -> Literal["generate_answer", "rewrite_question"]:
        if state.get("rewrite_count", 0) >= 2:
            return "generate_answer"

        original_question = next(
            (m.content for m in state["messages"] if isinstance(m, HumanMessage)), ""
        )
        tool_content = state["messages"][-1].content
        grader = llm.with_structured_output(GradeResult)
        result = grader.invoke(
            f"用户问题: {original_question}\n\n工具返回结果:\n{tool_content}\n\n"
            "这个结果是否包含能回答用户问题的有效信息？"
        )
        return "generate_answer" if result.relevant else "rewrite_question"

    def rewrite_question(state: AgentState):
        # Fix #3: use latest HumanMessage, not the first one
        latest_question = next(
            (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), ""
        )
        rewritten = llm.invoke(
            f"以下问题在知识图谱查询中没有得到有效结果，请换一种更适合实体检索的表达方式重新提问，"
            f"保持原意，只输出重写后的问题本身：\n{latest_question}"
        ).content
        return {
            "messages": [HumanMessage(content=rewritten)],
            "rewrite_count": state.get("rewrite_count", 0) + 1,
        }

    def generate_answer(state: AgentState):
        # Structured AgentAnswer (§7); enrich overwrites coords from KG ground truth.
        messages = list(state["messages"]) + [HumanMessage(content=ANSWER_STRUCT_HINT)]
        answer_text = ""
        citations: list[Citation] = []

        try:
            structured_llm = llm.with_structured_output(AgentAnswer)
            raw = structured_llm.invoke(messages)
            result = raw if isinstance(raw, AgentAnswer) else AgentAnswer.model_validate(raw)
            answer_text = result.answer
            citations = enrich_citations(result.citations, nodes, edges)
        except Exception:
            # Fallback: plain text + heuristic name matching, then same enrich path
            response = llm.invoke(state["messages"])
            answer_text = str(response.content)
            citations = enrich_citations(_extract_citations(answer_text, nodes), nodes, edges)

        return {
            "messages": [SystemMessage(content=answer_text)],
            "structured_answer": answer_text,
            "structured_citations": [c.model_dump() for c in citations],
        }

    graph_builder = StateGraph(AgentState)
    graph_builder.add_node("generate_query_or_respond", generate_query_or_respond)
    graph_builder.add_node("retrieve", ToolNode(tools))
    graph_builder.add_node("rewrite_question", rewrite_question)
    graph_builder.add_node("generate_answer", generate_answer)

    graph_builder.add_edge(START, "generate_query_or_respond")
    graph_builder.add_conditional_edges(
        "generate_query_or_respond", route_after_generate, {"retrieve": "retrieve", END: END}
    )
    graph_builder.add_conditional_edges(
        "retrieve", grade_documents, {"generate_answer": "generate_answer", "rewrite_question": "rewrite_question"}
    )
    graph_builder.add_edge("rewrite_question", "generate_query_or_respond")
    graph_builder.add_edge("generate_answer", END)

    if checkpointer is not None:
        return graph_builder.compile(checkpointer=checkpointer)
    return graph_builder.compile()


# ── Per-doc cache ───────────────────────────────────────────────────

_kg_cache_lock = threading.Lock()
_kg_cache: dict[str, dict] = {}

# Global checkpointer for multi-turn sessions (§6.3)
_memory = MemorySaver()


def load_kg_for_doc(doc_id: str, nodes_path: pathlib.Path, edges_path: pathlib.Path) -> dict:
    """Load + cache a document's KG and compiled agent, keyed by doc_id."""
    with _kg_cache_lock:
        cached = _kg_cache.get(doc_id)
        if cached is not None:
            return cached

        nodes = load_jsonl(nodes_path)
        edges = load_jsonl(edges_path)
        agent = _build_agent(nodes, edges, doc_id, checkpointer=_memory)

        entry = {"nodes": nodes, "edges": edges, "agent": agent}
        _kg_cache[doc_id] = entry
        return entry


def evict_doc(doc_id: str) -> None:
    with _kg_cache_lock:
        _kg_cache.pop(doc_id, None)


def ask(doc_id: str, question: str, nodes_path: pathlib.Path, edges_path: pathlib.Path,
        session_id: str | None = None) -> dict:
    """Run the QA agent against a specific document's KG.

    Returns {answer, citations, rewrite_count} per spec §7.2.5.
    If session_id is provided, conversation state is persisted for multi-turn (§6.3).
    """
    entry = load_kg_for_doc(doc_id, nodes_path, edges_path)

    config: dict = {}
    if session_id:
        config["configurable"] = {"thread_id": session_id}
    else:
        config["configurable"] = {"thread_id": uuid.uuid4().hex}

    result = entry["agent"].invoke(
        {"messages": [HumanMessage(content=question)], "rewrite_count": 0, "structured_answer": "", "structured_citations": []},
        config,
    )

    # Extract structured answer + citations from the final state
    structured_answer = result.get("structured_answer") or ""
    structured_citations = result.get("structured_citations") or []

    if structured_answer:
        return {
            "answer": structured_answer,
            "citations": structured_citations,
            "rewrite_count": result.get("rewrite_count", 0),
        }
    # Direct respond without generate_answer (no tool calls) — use last message text
    last = result["messages"][-1]
    content = getattr(last, "content", last)
    return {
        "answer": content if isinstance(content, str) else str(content),
        "citations": structured_citations,
        "rewrite_count": result.get("rewrite_count", 0),
    }
