"""PostToolUse lint gate (Edit|Write).

2026-08-24: Burke Holland の hooks 動画由来。編集直後に静的チェックを走らせ、失敗なら
exit 2 + stderr で Claude に返して自己修正を強制する（人間が気づく前に直させる）。
対象は Python (.py) のみ、ruff が無ければ何もしない。危険操作ブロック系の 4 hook とは
役割が別（あちらは PreToolUse で実行前、こちらは品質で実行後）。
"""
import json
import os
import subprocess
import sys


def main():
    try:
        # utf-8-sig: PowerShell 経由のパイプは BOM 付きになるため
        data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
    except Exception:
        return 0
    path = (data.get("tool_input") or {}).get("file_path") or ""
    if not path.lower().endswith(".py") or not os.path.isfile(path):
        return 0
    # E9/F: 構文エラー・未定義名・未使用 import 等の「確実に壊れている」系だけ。
    # スタイル警告で毎回止めると邪魔なので絞る。
    try:
        r = subprocess.run(
            ["ruff", "check", "--select", "E9,F", "--no-cache", "--quiet", path],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
        )
    except FileNotFoundError:
        return 0
    except subprocess.TimeoutExpired:
        return 0
    if r.returncode == 0:
        return 0
    out = (r.stdout or "") + (r.stderr or "")
    sys.stderr.write(
        "[lint-gate] ruff が問題を検出。次の Edit で修正してから先に進むこと:\n"
        + out[-1500:]
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
