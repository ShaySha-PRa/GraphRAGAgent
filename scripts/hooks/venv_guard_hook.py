#!/usr/bin/env python3
"""
PreToolUse hook: enforce that all Python/pip commands run inside a project venv.

Invoked by Claude Code's hook system. Receives JSON on stdin with the tool call
details, inspects the Bash command, and either:
- Passes through (non-Python commands, already-venv-pathed, uv commands)
- Auto-rewrites bare python/pip to use the nearest .venv/Scripts/python.exe
- Denies if no .venv/ is discoverable anywhere up the directory tree

Uses the SYSTEM Python (hardcoded in settings.local.json as the hook command)
since this script is infrastructure, not user code.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(r"I:\Users\Joshu\desktop\GraphRAGAgent")

# ── Detection helpers ──────────────────────────────────────────

_VENV_PYTHON_RE = re.compile(r"(?:^|[\s;&|(])(python3?|pip3?)(?:\s|$)")
_ALREADY_VENV_RE = re.compile(r"[\\/]\.venv[\\/]")


def _is_target(cmd: str) -> bool:
    """True if *cmd* invokes bare python/pip but is NOT already venv-pathed."""
    if _ALREADY_VENV_RE.search(cmd):
        return False
    stripped = cmd.strip()
    if stripped.startswith("uv "):
        return False
    return bool(_VENV_PYTHON_RE.search(stripped))


# ── Venv discovery ─────────────────────────────────────────────

def _find_venv(cmd: str) -> Path | None:
    """Walk upward from the command's script-path or cwd to find .venv/pyvenv.cfg."""
    # Extract a .py script path from the command if present
    tokens = cmd.split()
    script_path: str | None = None
    for tok in tokens:
        if tok.endswith(".py"):
            script_path = tok
            break

    start = (
        Path(script_path).resolve().parent
        if script_path
        else Path(os.getcwd()).resolve()
    )

    for parent in [start] + list(start.parents):
        venv_cfg = parent / ".venv" / "pyvenv.cfg"
        if venv_cfg.is_file():
            return parent / ".venv"
        # Stop once we leave the project tree
        if parent == PROJECT_ROOT.parent:
            break

    return None


# ── Command rewriting ──────────────────────────────────────────

def _rewrite(cmd: str, venv: Path) -> str:
    """Replace python/pip with the venv-pathed executable."""
    python_exe = str(venv / "Scripts" / "python.exe").replace("\\", "/")
    rewritten = re.sub(r"\bpython3?\b", python_exe, cmd, count=1)
    rewritten = re.sub(r"\bpip3?\b", f"{python_exe} -m pip", rewritten, count=1)
    return rewritten


# ── Hook entry point ───────────────────────────────────────────

def main() -> None:
    raw = sys.stdin.read()
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        print(json.dumps({"permissionDecision": "allow"}))
        return

    # Only intercept Bash tool calls
    if msg.get("tool_name", "") != "Bash":
        print(json.dumps({"permissionDecision": "allow"}))
        return

    command = msg.get("tool_input", {}).get("command", "")
    if not command or not _is_target(command):
        print(json.dumps({"permissionDecision": "allow"}))
        return

    venv = _find_venv(command)
    if venv is None:
        print(
            json.dumps(
                {
                    "permissionDecision": "deny",
                    "systemMessage": (
                        "VENV GUARD: No .venv/ found for this Python command. "
                        "Create a venv first or cd into a directory that has one. "
                        "See CLAUDE.md for instructions."
                    ),
                }
            )
        )
        return

    new_cmd = _rewrite(command, venv)
    print(
        json.dumps(
            {
                "permissionDecision": "allow",
                "updatedInput": {"command": new_cmd},
                "systemMessage": f"[venv guard] redirected: {new_cmd}",
            }
        )
    )


if __name__ == "__main__":
    main()
