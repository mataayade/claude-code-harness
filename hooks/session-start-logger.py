#!/usr/bin/env python3
"""SessionStart hook: セッション開始時刻と cwd を JSONL ログに記録。

月次棚卸し (inventory-curator) で「どのプロジェクトに何分触ったか」を集計する材料。
ログ: ~/.claude/session-log.jsonl （1行 = 1 セッション）
"""
import json
import sys
import os
import datetime
import pathlib

LOG = pathlib.Path.home() / ".claude" / "session-log.jsonl"


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        data = {}

    entry = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "cwd": data.get("cwd") or os.getcwd(),
        "session_id": data.get("session_id"),
        "source": data.get("source", "unknown"),  # startup / resume / clear / compact
        "model": data.get("model"),
        "transcript_path": data.get("transcript_path"),
    }

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
