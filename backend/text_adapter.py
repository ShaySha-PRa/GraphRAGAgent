"""Direct text adapter for .txt / .md uploads.

Per backend_service_architecture-v1.0.md §4.2: fabricates a single-block
content_list.json so that build_kg.py's Lane B path consumes it unchanged
without a wasted MinerU round-trip.
"""

from __future__ import annotations

import json
import pathlib


def build_fake_content_list(upload_path: pathlib.Path, doc_dir: pathlib.Path, doc_id: str) -> pathlib.Path:
    """Read a plain-text file and write a fake content_list.json under doc_dir/mineru_output/.

    Returns the mineru_output directory path (so the call site can pass it
    to build_kg.py exactly as if it were real MinerU output).
    """
    text = upload_path.read_text(encoding="utf-8", errors="replace")

    content_list = [
        {
            "type": "text",
            "text": text,
            "page_idx": 0,
            "bbox": None,  # plain text has no page coordinates — per bridge_pipeline spec §3.3.2
        }
    ]

    output_dir = doc_dir / "mineru_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    cl_path = output_dir / f"{doc_id}_content_list.json"
    with cl_path.open("w", encoding="utf-8") as f:
        json.dump(content_list, f, ensure_ascii=False, indent=2)

    return output_dir
