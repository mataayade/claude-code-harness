#!/usr/bin/env python3
"""PreToolUse hook: Block bash heredoc (<<EOF) to prevent tool-call corruption.

Exit code 0 = allow
Exit code 2 = block (stderr is sent to Claude as error message)

Background (2026-07-09): a multi-line `git commit -m "$(cat <<'EOF' ...)"` broke
the tool-call framing in a Claude Code session and the corrupted syntax kept
re-appearing. Heredocs in the Bash tool are the known trigger, so they are
blocked wholesale. PowerShell here-strings (@'...'@) are NOT blocked -- they
are the documented multi-line mechanism for the PowerShell tool.

Delimiter must look like a real heredoc marker (uppercase, 2+ chars, e.g. EOF,
END, HEREDOC) so bit-shifts like `1<<3` or `x<<y` do not false-positive.
"""
import json
import re
import sys

HEREDOC_RE = re.compile(r"<<-?\s*['\"]?[A-Z_][A-Z0-9_]+['\"]?")


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        sys.exit(0)  # 入力壊れてたら通す（hookの責任ではない）

    if data.get("tool_name", "").lower() not in ("bash", "shell"):
        sys.exit(0)

    command = (data.get("tool_input") or {}).get("command", "") or ""
    m = HEREDOC_RE.search(command)
    if m:
        # ASCII only: Japanese in stderr gets mojibaked by the cp932 console
        # and the message is what Claude reads to self-correct.
        print(
            "[BLOCKED] hooks/pretooluse-heredoc-gate.py\n"
            f"  Reason: bash heredoc ({m.group(0)}) is a known trigger for"
            " tool-call corruption (incident 2026-07-09).\n"
            "  Alternatives: (1) for git commit, use multiple -m flags;"
            " (2) write multi-line data to a temp file with the Write tool;"
            " (3) printf '%s\\n' per line.",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
