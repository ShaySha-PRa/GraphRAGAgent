# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in the `langextract_src/` directory.

## Virtual environment (required before anything runs)

This component has its own **uv-managed virtual environment** at `.venv/`, isolated from `langextract/` (the source clone), `mineru-pipeline/`, and the system Python. **Any Python or pip invocation for this component must go through `.venv/`** — do not run bare `python`/`pip` here.

A PreToolUse hook in the project root's `.claude/settings.local.json` automatically redirects bare `python`/`pip` commands to `.venv/Scripts/python.exe`. You can type `python test_deepseek_extract.py` — the hook rewrites it transparently. A "No .venv/ found" denial means the hook could not discover this venv (e.g. you are outside `langextract_src/` and no `.venv/pyvenv.cfg` is found walking up from cwd).

To run manually (outside Claude Code, or to bypass the hook), use:
```bash
.venv/Scripts/python.exe test_deepseek_extract.py
```

## IMPORTANT: run scripts from `langextract_src/`, not the project root

The project root (`GraphRAGAgent/`) contains a directory literally named `langextract/` (the source clone). If a script under this venv is invoked with cwd = project root, Python's default `PathFinder` resolves `import langextract` as an **empty PEP 420 namespace package** rooted at that directory — silently shadowing the real editable install before its finder is ever consulted. Symptom: `AttributeError: module 'langextract' has no attribute 'extract'` (or any other real attribute), even though the package is correctly installed.

Fix: always `cd langextract_src` (or otherwise ensure cwd is not the project root) before running `.venv/Scripts/python.exe ...`.

## What's installed

`langextract` is installed in **editable mode** (`pip install -e ../langextract`) — it points directly at the source in `../langextract/langextract/`, so edits there take effect immediately without reinstalling. Core deps + the `openai` extra (17 core packages + `openai>=1.50.0`, 58 total resolved) are installed per `../langextract/pyproject.toml`.

```bash
# Install a new package into this venv
cd langextract_src
python -m uv pip install --python .venv/Scripts/python.exe <package>
```

## Configuration

`.env` (not committed — see root `.gitignore`) holds provider API keys, e.g.:
```
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

See `langextract/docs/langextract_specification-v1.0.md` for the verified pipeline flow, parameter reference, and actual output file formats.

## Quick start

```bash
cd langextract_src
.venv/Scripts/python.exe test_deepseek_extract.py
```

Requires `DEEPSEEK_API_KEY` in `.env`. Output (JSONL + HTML visualization) is written to `output/`.
