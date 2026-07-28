"""Build a knowledge graph (nodes + edges) from a MinerU parse output using LangExtract.

Two-lane pipeline (see the MinerU->LangExtract integration plan):
  - Lane A: MinerU table blocks -> structured triples, no LLM (mineru_adapter.parse_table_block).
  - Lane B: MinerU text blocks -> concatenated per page -> lx.extract() (DeepSeek via the
    OpenAI-compatible provider, same ModelConfig pattern as test_deepseek_extract.py) ->
    char_interval traced back to page_idx/bbox via mineru_adapter.find_provenance.

Usage:
    cd langextract_src
    .venv/Scripts/python.exe build_kg.py <mineru_output_dir> [--output-dir <dir>]

<mineru_output_dir> is a MinerU ZIP-extraction directory, e.g.
../mineru-pipeline/output/financial_report.pdf_20260728_153310/

--output-dir defaults to ./output/ (this component's existing fixed path) if
omitted, for backward compatibility with existing manual/webapp usage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys

from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import langextract as lx
from langextract.core.data import ExampleData, Extraction
from langextract.factory import ModelConfig

import mineru_adapter

ROOT = pathlib.Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

API_KEY = os.getenv("DEEPSEEK_API_KEY")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

if not API_KEY:
    raise SystemExit("ERROR: DEEPSEEK_API_KEY not set in langextract_src/.env")

PROMPT_DESCRIPTION = (
    "Extract entities (organizations, financial metrics, risk factors, dates) and "
    "relations between them from this financial report excerpt. For entities, use "
    "extraction_class one of: organization, financial_metric, risk_factor, date. "
    "For a relation between two entities, use extraction_class \"relation\" with "
    "attributes subject, predicate, object (exact text spans or values from the "
    "source). Use exact text from the source for extraction_text."
)

EXAMPLES = [
    ExampleData(
        text="ACME Corp reported revenue of $10M in 2024, up 15% year over year.",
        extractions=[
            Extraction(
                extraction_class="organization",
                extraction_text="ACME Corp",
                attributes={},
            ),
            Extraction(
                extraction_class="financial_metric",
                extraction_text="$10M",
                attributes={
                    "metric": "revenue",
                    "period": "2024",
                    "change_yoy": "+15%",
                },
            ),
            Extraction(
                extraction_class="relation",
                extraction_text="reported revenue of",
                attributes={
                    "subject": "ACME Corp",
                    "predicate": "reported_revenue",
                    "object": "$10M",
                },
            ),
        ],
    ),
]

CONFIG = ModelConfig(
    model_id="deepseek-chat",
    provider="openai",
    provider_kwargs={"api_key": API_KEY, "base_url": BASE_URL},
)


def _node_id(doc_id: str, extraction_class: str, extraction_text: str) -> str:
    raw = f"{doc_id}:{extraction_class}:{extraction_text}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def extract_lane_a(table_blocks: list[dict], doc_id: str) -> list[dict]:
    """Table blocks -> KG nodes (no LLM)."""
    nodes = []
    for block in table_blocks:
        for triple in mineru_adapter.parse_table_block(block):
            extraction_text = f"{triple['row_label']} / {triple['metric']} = {triple['value']}"
            nodes.append({
                "id": _node_id(doc_id, "financial_metric", extraction_text),
                "label": "financial_metric",
                "name": extraction_text,
                "attributes": {
                    "row_label": triple["row_label"],
                    "metric": triple["metric"],
                    "value": triple["value"],
                },
                "provenance": {"doc_id": doc_id, **triple["provenance"]},
            })
    return nodes


def extract_lane_b(
    page_texts: list[mineru_adapter.PageText], doc_id: str
) -> tuple[list[dict], list[dict]]:
    """Text pages -> lx.extract() -> KG nodes + relation edges."""
    nodes = []
    edges = []

    for page in page_texts:
        if not page.text.strip():
            continue

        print(f"  -> lx.extract() on page {page.page_idx} ({len(page.text)} chars)...")
        result = lx.extract(
            text_or_documents=page.text,
            prompt_description=PROMPT_DESCRIPTION,
            examples=EXAMPLES,
            config=CONFIG,
            use_schema_constraints=False,
        )

        for ext in result.extractions:
            provenance = {"doc_id": doc_id, "page_idx": page.page_idx}
            interval = ext.char_interval
            if interval is not None and interval.start_pos is not None:
                entry = mineru_adapter.find_provenance(
                    interval.start_pos, interval.end_pos, page.offsets
                )
                if entry is not None:
                    provenance["bbox"] = entry.bbox
                provenance["char_interval"] = {
                    "start_pos": interval.start_pos,
                    "end_pos": interval.end_pos,
                }

            if ext.extraction_class == "relation":
                edges.append({
                    "subject": ext.attributes.get("subject"),
                    "predicate": ext.attributes.get("predicate"),
                    "object": ext.attributes.get("object"),
                    "provenance": provenance,
                })
            else:
                nodes.append({
                    "id": _node_id(doc_id, ext.extraction_class, ext.extraction_text),
                    "label": ext.extraction_class,
                    "name": ext.extraction_text,
                    "attributes": ext.attributes,
                    "provenance": provenance,
                })

    return nodes, edges


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mineru_output_dir")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    mineru_dir = pathlib.Path(args.mineru_output_dir).resolve()
    output_dir = pathlib.Path(args.output_dir).resolve() if args.output_dir else ROOT / "output"

    content_list_paths = sorted(mineru_dir.glob("*_content_list.json"))
    if not content_list_paths:
        raise SystemExit(f"ERROR: no *_content_list.json found in {mineru_dir}")

    content_list_path = content_list_paths[0]
    doc_id = content_list_path.name[: -len("_content_list.json")]

    print("=" * 60)
    print("MinerU -> LangExtract -> Knowledge Graph")
    print("=" * 60)
    print(f"content_list: {content_list_path}")
    print(f"doc_id: {doc_id}\n")

    page_texts, table_blocks = mineru_adapter.load_pages(content_list_path)
    print(f"Pages: {len(page_texts)}, table blocks: {len(table_blocks)}\n")

    print("Lane A (tables, no LLM):")
    lane_a_nodes = extract_lane_a(table_blocks, doc_id)
    print(f"  -> {len(lane_a_nodes)} nodes\n")

    print("Lane B (text via DeepSeek):")
    lane_b_nodes, lane_b_edges = extract_lane_b(page_texts, doc_id)
    print(f"  -> {len(lane_b_nodes)} nodes, {len(lane_b_edges)} edges\n")

    all_nodes = lane_a_nodes + lane_b_nodes
    all_edges = lane_b_edges

    output_dir.mkdir(parents=True, exist_ok=True)

    nodes_path = output_dir / "kg_nodes.jsonl"
    edges_path = output_dir / "kg_edges.jsonl"

    with nodes_path.open("w", encoding="utf-8") as f:
        for node in all_nodes:
            f.write(json.dumps(node, ensure_ascii=False) + "\n")

    with edges_path.open("w", encoding="utf-8") as f:
        for edge in all_edges:
            f.write(json.dumps(edge, ensure_ascii=False) + "\n")

    print(f"Saved nodes: {nodes_path} ({len(all_nodes)} records)")
    print(f"Saved edges: {edges_path} ({len(all_edges)} records)")
    print("\nDone.")


if __name__ == "__main__":
    main()
