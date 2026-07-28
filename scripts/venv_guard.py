"""
Venv guard utility for the GraphRAGAgent project.

Two usage modes:
1.  Inline snippet in Python scripts (no import needed):
        import sys
        if sys.prefix == sys.base_prefix:
            sys.exit("ERROR: must run inside a virtual environment. See CLAUDE.md.")

2.  Importable guard for scripts that have reliable import paths:
        from scripts.venv_guard import guard_venv
        guard_venv()
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def find_project_venv(
    script_path: str | None = None,
    cwd: str | None = None,
) -> Path | None:
    """Walk upward from *script_path* or *cwd* looking for .venv/pyvenv.cfg."""
    start = (
        Path(script_path).resolve().parent
        if script_path
        else Path(cwd or os.getcwd()).resolve()
    )
    for parent in [start] + list(start.parents):
        candidate = parent / ".venv" / "pyvenv.cfg"
        if candidate.is_file():
            return parent / ".venv"
    return None


_VENV_PYTHON_RE = re.compile(r"(?:^|[\s;&|(])(python3?|pip3?)(?:\s|$)")
_ALREADY_VENV_RE = re.compile(r"[\\/]\.venv[\\/]")


def is_bare_python_command(cmd: str) -> bool:
    """True if *cmd* invokes python/pip but is NOT already using a venv path."""
    if _ALREADY_VENV_RE.search(cmd):
        return False
    if cmd.strip().startswith("uv "):
        return False
    return bool(_VENV_PYTHON_RE.search(cmd))


def rewrite_for_venv(cmd: str, venv_path: Path) -> str:
    """Rewrite *cmd* so python/pip invocations point at *venv_path*."""
    python_exe = str(venv_path / "Scripts" / "python.exe").replace("\\", "/")
    rewritten = re.sub(r"\bpython3?\b", python_exe, cmd, count=1)
    rewritten = re.sub(r"\bpip3?\b", f"{python_exe} -m pip", rewritten, count=1)
    return rewritten


def guard_venv() -> None:
    """Call at the top of a script. Exits if NOT running inside any venv."""
    if sys.prefix != sys.base_prefix:
        return  # already inside a venv

    script = Path(sys.argv[0]).resolve()
    venv = find_project_venv(str(script))
    if venv:
        python_exe = venv / "Scripts" / "python.exe"
        sys.exit(
            f"ERROR: Not running inside a virtual environment.\n"
            f"       Use: {python_exe} {script.relative_to(PROJECT_ROOT)}\n"
            f"       Or:  cd {venv.parent} && source .venv/Scripts/activate"
            f" && python {script.name}"
        )
    sys.exit(
        "ERROR: Not running inside a virtual environment and no .venv/ found.\n"
        "       Create a venv first, then re-run. See CLAUDE.md."
    )
