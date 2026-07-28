#!/usr/bin/env python3
"""
MinerU MVP Pipeline
====================
本地 PDF -> 云端 MinerU 解析 -> 本地结果存储

流程:
  1. 扫描本地 PDF 文件
  2. 申请 MinerU 批量上传链接
  3. PUT 文件到 OSS 预签名 URL
  4. 轮询等待解析完成
  5. 下载 ZIP 并解压
  6. 打印解析摘要

用法: python pipeline.py
"""

from __future__ import annotations

# --- venv guard (must run before any third-party imports) ---
import sys as _sys
if _sys.prefix == _sys.base_prefix:
    _sys.exit(
        "ERROR: pipeline.py must run inside mineru-pipeline\\.venv\\\n"
        "Use: mineru-pipeline\\.venv\\Scripts\\python.exe mineru-pipeline\\pipeline.py\n"
        "Or:  cd mineru-pipeline && source .venv\\Scripts\\activate && python pipeline.py"
    )
# -----------------------------------------------------------

import json
import os
import pathlib
import sys
import time
import zipfile
from datetime import datetime
from io import BytesIO
from typing import Any

import urllib3
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

# Windows UTF-8 emoji support
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Suppress SSL warnings when verify=False is used
urllib3.disable_warnings()

# ── Paths ──────────────────────────────────────────────────
ROOT = pathlib.Path(__file__).resolve().parent
ENV = ROOT / ".env"
TEST_DOCS = ROOT / "test_documents"
OUTPUT = ROOT / "output"

# ── Config from .env ────────────────────────────────────────
load_dotenv(ENV)

BASE_URL = os.getenv("MINERU_API_BASE_URL", "https://mineru.net")
TOKEN = os.getenv("MINERU_API_TOKEN", "")
MODEL = os.getenv("MINERU_MODEL_VERSION", "vlm")
POLL_INTERVAL = int(os.getenv("MINERU_POLL_INTERVAL", "3"))
POLL_MAX = int(os.getenv("MINERU_POLL_MAX_RETRIES", "200"))
SSL_VERIFY = os.getenv("MINERU_SSL_VERIFY", "true").lower() != "false"

AUTH = {"Authorization": f"Bearer {TOKEN}"}

# ── API endpoints ───────────────────────────────────────────
BATCH_UPLOAD = f"{BASE_URL}/api/v4/file-urls/batch"
BATCH_RESULT = f"{BASE_URL}/api/v4/extract-results/batch"


# ── Retry helper (exponential backoff for SSL / network issues) ─
def _get_with_retry(
    url: str, headers: dict, timeout: int = 30, max_tries: int = 3
) -> requests.Response:
    """GET with exponential backoff on SSL / connection errors.

    Tries up to ``max_tries`` times (1s, 2s, 4s backoff).
    Falls back to ``verify=False`` on the final attempt if SSL fails.
    """
    last_err: Exception | None = None
    for attempt in range(1, max_tries + 1):
        try:
            return requests.get(url, headers=headers, timeout=timeout,
                                verify=SSL_VERIFY)
        except (requests.exceptions.SSLError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as exc:
            last_err = exc
            if attempt == max_tries:
                # Final attempt: try without SSL verification
                print(f"\n    [!] SSL error after {max_tries} retries, "
                      f"retrying with verify=False ...")
                return requests.get(url, headers=headers, timeout=timeout,
                                    verify=False)
            wait = 2 ** (attempt - 1)  # 1, 2, 4 seconds
            print(f"\n    [!] {type(exc).__name__}, retrying in {wait}s "
                  f"({attempt}/{max_tries}) ...", end="", flush=True)
            time.sleep(wait)
    raise last_err  # type: ignore[misc]


# ══════════════════════════════════════════════════════════════
# Phase 1: Discover local PDFs
# ══════════════════════════════════════════════════════════════

def discover_pdfs(directory: pathlib.Path) -> list[pathlib.Path]:
    """Scan directory for PDF files (case-insensitive, deduplicated)."""
    files = sorted(set(
        list(directory.glob("*.pdf")) + list(directory.glob("*.PDF"))
    ))
    if not files:
        raise FileNotFoundError(f"No PDF files found in {directory}")

    print(f"\n{'='*60}")
    print(f"  [Phase 1/4] Scanning: {directory}")
    print(f"  Found {len(files)} PDF(s):")
    for f in files:
        print(f"    - {f.name} ({f.stat().st_size/1024:.1f} KB)")
    print(f"{'='*60}")
    return files


# ══════════════════════════════════════════════════════════════
# Phase 2: Request upload URLs + PUT files to OSS
# ══════════════════════════════════════════════════════════════

def request_upload_urls(pdfs: list[pathlib.Path]) -> dict[str, Any]:
    """POST /api/v4/file-urls/batch to get pre-signed OSS upload URLs.

    Returns API response `data` dict with keys: batch_id, file_urls.
    """
    payload = {
        "files": [{"name": f.name, "size": f.stat().st_size} for f in pdfs]
    }

    print(f"\n  [Phase 2/4] Requesting upload URLs...")
    for item in payload["files"]:
        print(f"    - {item['name']} ({item['size']:,} bytes)")

    r = requests.post(BATCH_UPLOAD, json=payload, headers=AUTH, timeout=30)
    body = r.json()

    if body.get("code") != 0:
        raise RuntimeError(
            f"Upload URL request failed: code={body.get('code')}, "
            f"msg={body.get('msg')}"
        )

    data = body["data"]
    print(f"    Batch ID: {data['batch_id']}")
    print(f"    Upload URLs received: {len(data['file_urls'])}")
    return data


def upload_pdfs(pdfs: list[pathlib.Path], file_urls: list[str]) -> None:
    """PUT each local PDF to its corresponding OSS pre-signed URL.

    IMPORTANT: Do NOT add custom headers (Content-Type etc.) —
    the OSS signature was computed without them.
    """
    for idx, url in enumerate(file_urls):
        fpath = pdfs[idx]
        size = fpath.stat().st_size
        print(f"    Uploading: {fpath.name} ({size:,} bytes)...", end=" ", flush=True)

        with open(fpath, "rb") as fh:
            r = requests.put(url, data=fh, timeout=120)

        if r.status_code in (200, 201, 204):
            print("done")
        else:
            raise RuntimeError(
                f"Upload failed (HTTP {r.status_code}): {r.text[:300]}"
            )


# ══════════════════════════════════════════════════════════════
# Phase 3: Poll until parsing complete
# ══════════════════════════════════════════════════════════════

def poll_results(batch_id: str) -> list[dict[str, Any]]:
    """GET /api/v4/extract-results/batch/{batch_id} until all files done."""

    print(f"\n  [Phase 3/4] Waiting for parsing...")
    print(f"    Poll interval: {POLL_INTERVAL}s, max retries: {POLL_MAX}")

    url = f"{BATCH_RESULT}/{batch_id}"

    for attempt in range(1, POLL_MAX + 1):
        r = _get_with_retry(url, headers=AUTH, timeout=30)
        body = r.json()

        if body.get("code") != 0:
            raise RuntimeError(f"Poll failed: {body.get('msg')}")

        results = body.get("data", {}).get("extract_result", [])

        # Count states
        states: dict[str, int] = {}
        for res in results:
            s = res.get("state", "unknown")
            states[s] = states.get(s, 0) + 1

        state_str = ", ".join(f"{k}:{v}" for k, v in states.items())
        print(f"    [{attempt:>3}/{POLL_MAX}] {state_str}")

        # Check for failures
        failed = [r for r in results if r.get("state") == "failed"]
        if failed:
            details = [f"{f['file_name']}: {f.get('err_msg')}" for f in failed]
            raise RuntimeError(f"Parsing failed: {details}")

        # All done?
        if all(r.get("state") == "done" for r in results) and results:
            print(f"    All done!")
            return results

        time.sleep(POLL_INTERVAL)

    raise TimeoutError(
        f"Timeout after {POLL_MAX * POLL_INTERVAL}s ({POLL_MAX} retries)"
    )


# ══════════════════════════════════════════════════════════════
# Phase 4: Download ZIPs and extract
# ══════════════════════════════════════════════════════════════

def download_and_extract(
    results: list[dict[str, Any]], output_dir: pathlib.Path
) -> list[pathlib.Path]:
    """Download full_zip_url for each result and extract to output_dir."""

    print(f"\n  [Phase 4/4] Downloading & extracting results...")

    output_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[pathlib.Path] = []

    for res in results:
        fname = res.get("file_name", "unknown")
        zip_url = res.get("full_zip_url", "")
        progress = res.get("extract_progress", {})

        pages_done = progress.get("extracted_pages", "?")
        pages_total = progress.get("total_pages", "?")

        if not zip_url:
            print(f"    SKIP {fname}: no full_zip_url")
            continue

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = output_dir / f"{fname}_{ts}"
        dest.mkdir(parents=True, exist_ok=True)

        print(f"    Downloading: {fname} ({pages_done}/{pages_total} pages)...",
              end=" ", flush=True)

        zr = requests.get(zip_url, timeout=120)
        zr.raise_for_status()

        with zipfile.ZipFile(BytesIO(zr.content)) as zf:
            zf.extractall(dest)

        file_count = len(list(dest.rglob("*")))
        print(f"done ({file_count} files)")

        # Print file tree
        for item in sorted(dest.rglob("*")):
            if item.is_file():
                sz = item.stat().st_size
                rel = item.relative_to(dest)
                print(f"      {rel} ({sz:,} bytes)")

        extracted.append(dest)

    return extracted


# ══════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════

def print_summary(dirs: list[pathlib.Path]) -> None:
    """Print content statistics for each extracted result."""

    print(f"\n{'='*60}")
    print(f"  Summary")
    print(f"{'='*60}")

    for d in dirs:
        print(f"\n  {d.name}/")

        # --- full.md ---
        md_files = list(d.glob("**/full.md")) or list(d.glob("*.md"))
        if md_files:
            text = md_files[0].read_text(encoding="utf-8")
            lines = text.split("\n")
            print(f"    full.md: {len(lines)} lines, {len(text):,} chars")
            print(f"    Preview (first 15 lines):")
            for line in lines[:15]:
                if line.strip():
                    print(f"      | {line[:100]}")

        # --- content_list.json ---
        cl_files = list(d.glob("**/*_content_list.json"))
        if cl_files:
            cl = json.loads(cl_files[0].read_text(encoding="utf-8"))
            counts: dict[str, int] = {}
            for block in cl:
                t = block.get("type", "?")
                counts[t] = counts.get(t, 0) + 1
            print(f"    content_list.json: {len(cl)} blocks")
            for t, c in sorted(counts.items(), key=lambda x: -x[1]):
                print(f"      {t}: {c}")

        # --- middle.json ---
        mid_files = list(d.glob("**/*_middle.json"))
        if mid_files:
            mid = json.loads(mid_files[0].read_text(encoding="utf-8"))
            pages = len(mid.get("pdf_info", []))
            backend = mid.get("_backend", "?")
            version = mid.get("_version_name", "?")
            print(f"    middle.json: {pages} pages (backend={backend}, v{version})")

        # --- images ---
        img_dirs = list(d.glob("**/images"))
        if img_dirs:
            n = len(list(img_dirs[0].rglob("*")))
            print(f"    images/: {n} files")


# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════

def main() -> None:
    print(f"\n{'='*60}")
    print(f"  MinerU MVP Pipeline")
    print(f"  API: {BASE_URL}  |  Model: {MODEL}")
    print(f"{'='*60}")

    if not TOKEN:
        sys.exit("ERROR: Set MINERU_API_TOKEN in .env")

    # 1. Discover
    pdfs = discover_pdfs(TEST_DOCS)

    # 2. Upload
    data = request_upload_urls(pdfs)
    batch_id = data["batch_id"]
    file_urls = data["file_urls"]
    upload_pdfs(pdfs, file_urls)

    # 3. Poll
    results = poll_results(batch_id)

    # 4. Download
    dirs = download_and_extract(results, OUTPUT)

    # 5. Summary
    print_summary(dirs)

    print(f"\n{'='*60}")
    print(f"  Pipeline complete!")
    print(f"  Results: {OUTPUT}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
