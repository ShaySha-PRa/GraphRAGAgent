#!/usr/bin/env python3
"""Parse a single PDF through MinerU (reuses pipeline.py's verified phase functions).

Usage:
    parse_one.py <pdf_path> <output_dir>

Imports request_upload_urls/upload_pdfs/poll_results/download_and_extract from
pipeline.py unchanged - this file only adapts the single-file/custom-output-dir
CLI shape needed by the webapp, it doesn't reimplement any MinerU API logic.

On success prints a final `RESULT_DIR=<path>` line so a caller (webapp/server.py)
can locate the extracted output directory without parsing human-readable text.
"""

from __future__ import annotations

import sys as _sys
if _sys.prefix == _sys.base_prefix:
    _sys.exit(
        "ERROR: parse_one.py must run inside mineru-pipeline\\.venv\\\n"
        "Use: mineru-pipeline\\.venv\\Scripts\\python.exe mineru-pipeline\\parse_one.py <pdf> <output_dir>"
    )

import pathlib
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pipeline import (
    TOKEN,
    download_and_extract,
    poll_results,
    request_upload_urls,
    upload_pdfs,
)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: parse_one.py <pdf_path> <output_dir>")

    pdf_path = pathlib.Path(sys.argv[1]).resolve()
    output_dir = pathlib.Path(sys.argv[2]).resolve()

    if not pdf_path.is_file():
        raise SystemExit(f"ERROR: not a file: {pdf_path}")
    if not TOKEN:
        raise SystemExit("ERROR: Set MINERU_API_TOKEN in mineru-pipeline/.env")

    pdfs = [pdf_path]

    data = request_upload_urls(pdfs)
    upload_pdfs(pdfs, data["file_urls"])
    results = poll_results(data["batch_id"])
    dirs = download_and_extract(results, output_dir)

    if not dirs:
        raise SystemExit("ERROR: MinerU produced no extracted output directory")

    print(f"RESULT_DIR={dirs[0]}")


if __name__ == "__main__":
    main()
