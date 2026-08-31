#!/usr/bin/env python3
"""PreToolUse hook: 外部送信ゲート。機密データを外部APIへ送ろうとした時だけ承認を求める(ask)。

設計思想(2026-06-17): 「金・リスクだけ人間ゲート」のリスク面。個人情報/顧客データ/シークレットが
外部LLM API(特に海外API)へ漏れるのを止める。security.md「顧客情報を外部APIに送らない→local强制」準拠。

通常の外部委譲(route aggressively)は邪魔しない設計: 「外部送信 かつ 機密参照あり」の AND でのみ発火。
  - 外部送信 = ask.py の非ローカル alias、または外部LLMホストへの curl/POST
  - 機密参照 = accounts.md / CLAUDE.local.md / .env / credentials / 顧客 / customer / prod_system / 秘密鍵 等

判定は ask(承認要求)。完全な秘密直書き(sk-... 等)は別の pretooluse-guard.py が既に block 済み。
"""
import json
import sys
import re

# 外部送信の兆候
EXTERNAL_HOSTS = [
    "api.openai.com", "api.moonshot.ai", "api.deepseek.com", "api.x.ai",
    "generativelanguage.googleapis.com", "api.anthropic.com", "openrouter.ai",
]
# ask.py のローカル(無料・外部送信でない)alias 系
LOCAL_ALIAS_HINT = ("local", "qwen", "ollama", "gemma")

# 機密データの参照（ファイル名・キーワード）
SENSITIVE_REFS = [
    "accounts.md", "claude.local.md", ".env", "credentials", "secrets/",
    "id_rsa", "id_ed25519", "phone_ed25519", ".pem", ".key",
    "顧客", "customer", "個人情報", "password", "passwd", "settings.local.json",
]
# 本番顧客基盤は単語境界で（prod_system を含む無関係語の誤検知を避ける）
PROD_SYSTEM_RX = re.compile(r"\bprod_system\b", re.IGNORECASE)


def is_external_send(command: str) -> bool:
    low = command.lower()
    if any(h in low for h in EXTERNAL_HOSTS):
        return True
    m = re.search(r"\bask\.py\s+([^\s\"']+)", command)
    if m:
        alias = m.group(1).lower()
        if not any(h in alias for h in LOCAL_ALIAS_HINT):
            return True  # 非ローカル alias = 外部API
    return False


def has_sensitive_ref(command: str) -> str:
    low = command.lower()
    for ref in SENSITIVE_REFS:
        if ref in low:
            return ref
    if PROD_SYSTEM_RX.search(command):
        return "PROD_SYSTEM(本番顧客基盤)"
    return ""


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        sys.exit(0)

    if data.get("tool_name", "").lower() not in ("bash", "shell"):
        sys.exit(0)
    command = (data.get("tool_input") or {}).get("command", "") or ""
    if not command:
        sys.exit(0)

    if is_external_send(command):
        ref = has_sensitive_ref(command)
        if ref:
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": (
                        f"[外部送信ゲート] 機密データ({ref})を外部APIへ送ろうとしています。"
                        f"個人情報/顧客データの外部流出になり得ます。本当に送りますか?"
                        f"（機密ならローカル ask.py local を使うべき）"
                    ),
                }
            }))
            sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
