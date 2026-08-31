#!/usr/bin/env python3
"""PreToolUse hook: コストゲート。課金が発生する操作の前に人間の承認を求める(ask)。

リスクガード(pretooluse-guard.py)とは役割が別:
  - guard      : 破壊的操作・シークレット直書きを BLOCK (exit 2 / deny)
  - cost-gate  : 金がかかる操作だけ止めて承認を求める (exit 0 + permissionDecision=ask)

設計思想(2026-06-17 確定): 「自律デフォルト + 金・リスクだけ人間ゲート」。
自律を壊さないため微課金(ask.py 単発)は通し、青天井のエージェント実行と実購入だけゲートする(案A)。
承認ダイアログは settings.json の auto モードより優先される(hook 決定がsettingsに勝つ)ため、
自律運転中でも「金の所だけ」確実に人間に承認を求められる。
"""
import json
import sys
import re

# === 線引き設定（ここだけ編集すれば 案A <-> 案B を切替） ===
# False = 案A(自律重視): 青天井実行と実購入だけ承認、微課金 ask.py は自由
# True  = 案B(統制重視): ask.py の有料 alias 呼び出しも毎回承認
GATE_ASKPY_PAID = False

# 案B用: 課金される ask.py alias（ローカル/無料は除外。gemini-flash は無料tierなので除外）
PAID_ASKPY_ALIASES = (
    "codex", "grok", "kimi", "deepseek", "gemini", "gpt5",
    "sonnet-direct", "opus-direct", "haiku-direct",
)
FREE_ALIAS_HINTS = ("local", "ollama", "qwen", "gemma", "gemini-flash")

# 案A: 常に承認を求める操作（青天井のエージェント実行 + 実購入）
# NOTE: opencode はコマンドとして実行される時だけマッチさせる。行頭/シェル区切り直後に限定し、
#   ask.py 等のプロンプト文字列中に "OpenCode" と書いただけで誤発火しないようにする(2026-06-22 修正)。
COST_PATTERNS = [
    (r"(?:^|[;&|]|\n)\s*opencode\b",
     "OpenCode 実行（自律エージェントループ=トークン大量消費）。"
     "Max サブスクなら追加課金は無いが、週次の利用枠を食う点に注意"),
    (r"\brecharge\b", "残高チャージ（実購入）"),
    (r"api\.stripe\.com", "Stripe 決済（実購入）"),
    (r"/v1/(checkout|charges|payment)", "決済 API（実購入）"),
]


def ask(reason):
    """承認ダイアログを出して終了。"""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": f"[コストゲート] {reason} — 承認しますか?",
        }
    }))
    sys.exit(0)


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        sys.exit(0)  # 入力が壊れていたら通常フローに委ねる

    if data.get("tool_name", "").lower() not in ("bash", "shell"):
        sys.exit(0)

    command = (data.get("tool_input") or {}).get("command", "") or ""
    if not command:
        sys.exit(0)

    # 案A: 青天井実行・実購入は常にゲート
    for pattern, reason in COST_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            ask(reason)

    # 案B: ask.py の有料 alias もゲート（フラグ ON 時のみ）
    if GATE_ASKPY_PAID:
        m = re.search(r"\bask\.py\s+([^\s\"']+)", command)
        if m:
            alias = m.group(1).lower()
            is_free = any(h in alias for h in FREE_ALIAS_HINTS)
            is_paid = any(a in alias for a in PAID_ASKPY_ALIASES)
            if is_paid and not is_free:
                ask(f"ask.py 有料モデル呼び出し（{alias} = 外部API課金）")

    # 何もヒットしなければ通常の権限フローに委ねる
    sys.exit(0)


if __name__ == "__main__":
    main()
