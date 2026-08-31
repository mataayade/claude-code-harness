"""Subprocess-level tests for hooks/*.py.

Each hook is a standalone script that reads a JSON blob on stdin (the Claude
Code hook payload: tool_name / tool_input) and signals its decision either via
exit code (0 = allow, 2 = block) or via a JSON `permissionDecision` on stdout
("ask" = request human approval). These tests exercise that contract directly,
without needing a running Claude Code session.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "hooks"


def run_hook(script_name, payload, env=None):
    """Run a hook script as a subprocess, feeding it `payload` as JSON on stdin."""
    script_path = HOOKS_DIR / script_name
    proc = subprocess.run(
        [sys.executable, str(script_path)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    return proc


def bash_input(command):
    return {"tool_name": "Bash", "tool_input": {"command": command}}


# ---------------------------------------------------------------------------
# pretooluse-guard.py
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("command", [
    "rm -rf /",
    "DROP TABLE users",
    "git push -f origin main",
])
def test_guard_blocks_dangerous_commands(command):
    proc = run_hook("pretooluse-guard.py", bash_input(command))
    assert proc.returncode == 2
    assert "[BLOCKED]" in proc.stderr


@pytest.mark.parametrize("command", [
    "ls -la",
    "git status",
])
def test_guard_allows_safe_commands(command):
    proc = run_hook("pretooluse-guard.py", bash_input(command))
    assert proc.returncode == 0


# ---------------------------------------------------------------------------
# pretooluse-cost-gate.py
# ---------------------------------------------------------------------------

def test_cost_gate_asks_for_stripe_checkout():
    proc = run_hook("pretooluse-cost-gate.py", bash_input("curl https://api.stripe.com/v1/charges"))
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_cost_gate_passes_plain_command():
    proc = run_hook("pretooluse-cost-gate.py", bash_input("echo hi"))
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


# ---------------------------------------------------------------------------
# pretooluse-external-send-gate.py
# ---------------------------------------------------------------------------

def test_external_send_gate_asks_when_host_and_sensitive_ref_both_present():
    cmd = 'python ask.py grok "summarize the contents of accounts.md"'
    proc = run_hook("pretooluse-external-send-gate.py", bash_input(cmd))
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_external_send_gate_passes_external_send_only():
    # non-local ask.py alias, but no sensitive file/keyword reference
    cmd = 'python ask.py grok "what is the weather like today"'
    proc = run_hook("pretooluse-external-send-gate.py", bash_input(cmd))
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_external_send_gate_passes_sensitive_ref_only():
    # sensitive file reference, but no external send (no host, no ask.py alias)
    cmd = "cat accounts.md"
    proc = run_hook("pretooluse-external-send-gate.py", bash_input(cmd))
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


# ---------------------------------------------------------------------------
# pretooluse-heredoc-gate.py
# ---------------------------------------------------------------------------

def test_heredoc_gate_blocks_heredoc():
    proc = run_hook("pretooluse-heredoc-gate.py", bash_input("cat <<EOF\nhello\nEOF"))
    assert proc.returncode == 2
    assert "[BLOCKED]" in proc.stderr


def test_heredoc_gate_allows_printf():
    proc = run_hook("pretooluse-heredoc-gate.py", bash_input("printf '%s\\n' x"))
    assert proc.returncode == 0


# ---------------------------------------------------------------------------
# posttooluse-lint-gate.py
# ---------------------------------------------------------------------------

RUFF_AVAILABLE = shutil.which("ruff") is not None


@pytest.mark.skipif(not RUFF_AVAILABLE, reason="ruff not installed")
def test_lint_gate_blocks_syntax_error(tmp_path):
    bad_py = tmp_path / "broken.py"
    bad_py.write_text("def foo(:\n    pass\n", encoding="utf-8")
    proc = run_hook("posttooluse-lint-gate.py", {"tool_input": {"file_path": str(bad_py)}})
    assert proc.returncode == 2


@pytest.mark.skipif(not RUFF_AVAILABLE, reason="ruff not installed")
def test_lint_gate_passes_clean_file(tmp_path):
    good_py = tmp_path / "clean.py"
    good_py.write_text("def foo():\n    return 1\n", encoding="utf-8")
    proc = run_hook("posttooluse-lint-gate.py", {"tool_input": {"file_path": str(good_py)}})
    assert proc.returncode == 0


# ---------------------------------------------------------------------------
# session-start-logger.py / session-end-worklog.py
#
# Both hardcode their log path off Path.home() (no env-var override built in).
# Python's expanduser("~") reads HOME/USERPROFILE from the environment, so we
# redirect both to a tmp dir for the subprocess to avoid writing into the
# real user's ~/.claude or ~/worklog during a test run.
# ---------------------------------------------------------------------------

def _home_redirect_env(tmp_path):
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path)
    return env


def test_session_start_logger_runs_clean(tmp_path):
    env = _home_redirect_env(tmp_path)
    payload = {"cwd": str(tmp_path), "session_id": "test-session", "source": "startup"}
    proc = run_hook("session-start-logger.py", payload, env=env)
    assert proc.returncode == 0


def test_session_end_worklog_runs_clean(tmp_path):
    env = _home_redirect_env(tmp_path)
    payload = {"session_id": "test-session", "cwd": str(tmp_path), "reason": "test"}
    proc = run_hook("session-end-worklog.py", payload, env=env)
    assert proc.returncode == 0


def test_session_start_logger_handles_empty_stdin(tmp_path):
    env = _home_redirect_env(tmp_path)
    proc = run_hook("session-start-logger.py", {}, env=env)
    assert proc.returncode == 0


def test_session_end_worklog_handles_empty_stdin(tmp_path):
    env = _home_redirect_env(tmp_path)
    proc = run_hook("session-end-worklog.py", {}, env=env)
    assert proc.returncode == 0
