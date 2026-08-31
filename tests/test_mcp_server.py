"""Direct-import tests for mcp_server.py's guardrail-exposing tools.

These call the plain functions (_guard_check / _sanitize_scan) rather than
the MCP-decorated tool wrappers, so they run fast and don't require a live
MCP client or the stdio transport -- see mcp_server.py's "MCP wiring" comment
for why the logic is split out that way.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# mcp_server.py lives at the repo root, not under tests/, so it isn't on
# sys.path by default under every pytest invocation style -- add it explicitly.
sys.path.insert(0, str(REPO_ROOT))

import mcp_server  # noqa: E402  (must follow the sys.path mutation above)


# ---------------------------------------------------------------------------
# guard_check
# ---------------------------------------------------------------------------

def test_guard_check_blocks_rm_rf_root():
    result = mcp_server._guard_check("rm -rf /")
    assert result["decision"] == "block"
    assert result["exit_code"] == 2
    assert result["reason"]  # stderr text should be non-empty on block


def test_guard_check_allows_safe_command():
    result = mcp_server._guard_check("ls -la")
    assert result["decision"] == "allow"
    assert result["exit_code"] == 0
    assert result["reason"] == ""


def test_guard_check_blocks_force_push():
    result = mcp_server._guard_check("git push --force origin x")
    assert result["decision"] == "block"
    assert result["exit_code"] == 2


# ---------------------------------------------------------------------------
# sanitize_scan
# ---------------------------------------------------------------------------

def test_sanitize_scan_clean_text():
    result = mcp_server._sanitize_scan("just some text")
    assert result["clean"] is True
    assert result["hits"] == []


def test_sanitize_scan_flags_leaked_key():
    # Built at runtime (not one contiguous literal) so this test file itself
    # doesn't trip sanitize.py's repo-wide scan (which also covers tests/) --
    # the concatenated value still matches sanitize.py's "openai-key" pattern
    # once it's passed through _sanitize_scan.
    fake_key = "leaked key: sk-" + "FAKEKEY1234567890"
    result = mcp_server._sanitize_scan(fake_key)
    assert result["clean"] is False
    assert len(result["hits"]) >= 1
