# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in the `mineru-pipeline/` directory.

## Virtual environment (automatic)

A PreToolUse hook in `.claude/settings.local.json` automatically redirects bare `python`/`pip` commands to `.venv/Scripts/python.exe`. You can type `python pipeline.py` — the hook rewrites it transparently.

To run manually (outside Claude Code), use:
```bash
.venv/Scripts/python.exe pipeline.py
```

The script itself contains a guard at the top — if accidentally launched with the system Python, it exits immediately with a clear error.

## Quick start

```bash
.venv/Scripts/python.exe pipeline.py
```

Requires `.env` with `MINERU_API_TOKEN=sk-...` and `MINERU_API_BASE_URL=https://mineru.net`.

## Dependencies

Managed by `uv` (pip-compatible). Currently: `requests`, `python-dotenv`, `urllib3`.

```bash
# Install a new package into the venv
cd mineru-pipeline
python -m uv pip install --python .venv/Scripts/python.exe <package>
```
