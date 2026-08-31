#!/usr/bin/env python3
"""MCP (Model Context Protocol) server exposing this harness's deterministic
guardrails as tools, so any MCP client (Claude Code or otherwise) can call
them the same way Claude Code's own hooks do -- without needing a running
Claude Code session or shelling out by hand.

Two tools:
  - guard_check(command):   would hooks/pretooluse-guard.py allow or block
                             this shell command?
  - sanitize_scan(text):    does this string trip sanitize.py's forbidden
                             pattern list (secrets / personal info)?

No network calls, no secrets read or written, stdio transport only. Runnable
directly as `python mcp_server.py`.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Resolve every path off this file's location (not the CWD) so the server
# behaves the same in CI, in a fresh clone, or run from an arbitrary directory.
REPO_ROOT = Path(__file__).resolve().parent
GUARD_HOOK = REPO_ROOT / "hooks" / "pretooluse-guard.py"

# sanitize.py lives at the repo root as a script, not a package -- add the
# repo root to sys.path so it can be imported and its pattern list / scan
# logic reused, instead of re-declaring the forbidden-pattern regexes here.
sys.path.insert(0, str(REPO_ROOT))
import sanitize  # noqa: E402  (must follow the sys.path mutation above)


def _guard_check(command: str) -> dict:
    """Run hooks/pretooluse-guard.py as a subprocess and structure its verdict.

    The hook stays a standalone script (its actual contract with Claude Code's
    PreToolUse hook mechanism) rather than being imported -- running it as a
    subprocess here exercises the exact same code path Claude Code invokes,
    so the MCP tool can never drift from the hook's real behavior.
    """
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    proc = subprocess.run(
        [sys.executable, str(GUARD_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
    )
    decision = "block" if proc.returncode == 2 else "allow"
    return {
        "decision": decision,
        "reason": proc.stderr.strip() if decision == "block" else "",
        "exit_code": proc.returncode,
    }


def _sanitize_scan(text: str) -> dict:
    """Run sanitize.py's forbidden-pattern scan against a single string.

    Writes `text` to a temp file inside a temp dir and calls sanitize.py's own
    scan_file() on just that file (never the whole repo), so this reuses the
    exact pattern list and matching logic behind `python sanitize.py` -- an
    arbitrary caller-supplied string never touches the real repo tree.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / "sanitize_scan_input.txt"
        tmp_path.write_text(text, encoding="utf-8")
        raw_hits = sanitize.scan_file(str(tmp_path))

    hits = [
        {"pattern": label, "match": match}
        for (_path, _lineno, label, match) in raw_hits
    ]
    return {"clean": len(hits) == 0, "hits": hits}


# --- MCP wiring --------------------------------------------------------
# Thin on purpose: the decorated tools below just adapt the plain functions
# above to the MCP tool-call contract. Tests import and call _guard_check /
# _sanitize_scan directly, so they don't need a running MCP client or stdio
# transport to exercise the actual logic.
from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("claude-code-harness")


@mcp.tool()
def guard_check(command: str) -> dict:
    """Check whether hooks/pretooluse-guard.py would allow or block a shell command."""
    return _guard_check(command)


@mcp.tool()
def sanitize_scan(text: str) -> dict:
    """Scan a string for sensitive patterns (secrets, personal info) this repo's sanitize.py forbids."""
    return _sanitize_scan(text)


if __name__ == "__main__":
    mcp.run(transport="stdio")
