#!/usr/bin/env python3
"""SessionEnd hook: append session summary to ~/worklog/YYYY-MM-DD.md"""
import sys
import json
import os
from datetime import datetime
from pathlib import Path


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}

    sid = data.get("session_id", "unknown")
    cwd = data.get("cwd", "unknown")
    tpath = data.get("transcript_path") or ""
    reason = data.get("reason") or ""

    now = datetime.now()
    day = now.strftime("%Y-%m-%d")
    time_s = now.strftime("%H:%M")
    logdir = Path.home() / "worklog"
    logdir.mkdir(exist_ok=True)
    log = logdir / f"{day}.md"

    sid_short = sid[:8] if sid else "unknown"

    lines = [
        "",
        "---",
        "",
        f"## {time_s} | Session `{sid_short}`",
        f"- cwd: `{cwd}`",
    ]
    if reason:
        lines.append(f"- reason: {reason}")

    if tpath and os.path.isfile(tpath):
        files = set()
        bash_ops = []
        first_prompt = None
        try:
            with open(tpath, encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                    except Exception:
                        continue
                    etype = entry.get("type")
                    msg = entry.get("message") or {}
                    content = msg.get("content")
                    if isinstance(content, list):
                        for c in content:
                            if not isinstance(c, dict):
                                continue
                            if c.get("type") == "tool_use":
                                name = c.get("name")
                                inp = c.get("input") or {}
                                if name in ("Edit", "Write", "NotebookEdit"):
                                    fp = inp.get("file_path")
                                    if fp:
                                        files.add(fp)
                                elif name == "Bash":
                                    d = inp.get("description") or inp.get("command") or ""
                                    if d and len(bash_ops) < 8:
                                        bash_ops.append(d)
                    elif isinstance(content, str) and etype == "user" and first_prompt is None:
                        first_prompt = content[:200]
        except Exception:
            pass

        if files:
            lines.append("- Changed files:")
            for fp in sorted(files)[:30]:
                lines.append(f"  - {fp}")
        if bash_ops:
            lines.append("- Bash ops:")
            for b in bash_ops:
                clean = b.replace("\n", " ").strip()[:120]
                lines.append(f"  - {clean}")
        if first_prompt:
            fp_clean = first_prompt.replace("\n", " ").strip()
            lines.append(f"- Opening prompt: {fp_clean}")

    with open(log, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
