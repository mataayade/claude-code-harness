#!/usr/bin/env python3
"""PreToolUse hook: Block dangerous bash commands before they execute.

Exit code 0 = allow
Exit code 2 = block (stderr is sent to Claude as error message)

Inspired by Mayank Aggarwal の Claude Code course (第40章).
USER 環境用に拡張: SQL DROP / git push -f / API キー直書き等もブロック。

このフックは settings.json の permissions.deny より厳格な regex マッチを提供する。
permissions.deny は glob、こちらは regex で柔軟。
"""
import json
import sys
import re

# 絶対にブロックするコマンドパターン（regex）
BLOCKED_PATTERNS = [
    # --- 破壊的ファイル操作 ---
    (r"\brm\s+-rf\s+/\s*$", "rm -rf / (root削除)"),
    (r"\brm\s+-rf\s+~/?\s*$", "rm -rf ~ (ホーム削除)"),
    (r"\brm\s+-rf\s+\.\s*$", "rm -rf . (カレント削除)"),
    (r"\brm\s+-rf\s+\.\.\s*$", "rm -rf .. (親ディレクトリ削除)"),
    (r"\brm\s+-rf\s+\*\s*$", "rm -rf * (ワイルドカード削除)"),
    (r":\(\)\s*\{\s*:\|:&\s*\}\s*;\s*:", "fork bomb"),
    # --- ディスク・デバイス破壊 ---
    (r"\bmkfs\.\w+\b", "mkfs.* (ファイルシステム作成=ディスク初期化)"),
    (r"\bdd\b[^|;&]*\bof=/dev/(sd[a-z]|nvme|hd[a-z]|disk)", "dd of=/dev/* (デバイス直書き)"),
    (r">\s*/dev/(sd[a-z]|nvme|hd[a-z]|disk)", "> /dev/* (デバイスへリダイレクト)"),
    # --- シークレット直書き検出 ---
    (r"\bsk-[a-zA-Z0-9_-]{20,}\b", "OpenAI/Anthropic API key (sk-...) 直書き"),
    (r"\bAIza[0-9A-Za-z_-]{35}\b", "Google API key (AIza...) 直書き"),
    (r"\bxai-[a-zA-Z0-9]{20,}\b", "xAI API key (xai-...) 直書き"),
    (r"\bnvapi-[a-zA-Z0-9_-]{20,}\b", "NVIDIA NIM API key (nvapi-...) 直書き"),
    (r"\bghp_[a-zA-Z0-9]{36}\b", "GitHub Personal Access Token (ghp_...) 直書き"),
    # --- 権限昇格 ---
    (r"^\s*sudo\b", "sudo (権限昇格)"),
    (r"\bchmod\s+777\b", "chmod 777 (全権限付与)"),
    # --- パイプ攻撃 ---
    (r"\bcurl\b[^|]*\|\s*(bash|sh|zsh)\b", "curl | bash (リモートスクリプト実行)"),
    (r"\bwget\b[^|]*\|\s*(bash|sh|zsh)\b", "wget | bash"),
    # --- 破壊的 Git ---
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard (未コミット変更の破壊)"),
    # 2026-08-30: OpenCode guard.js と判定を揃えるため全ブランチの force push を遮断（parity テスト対象）
    (r"\bgit\s+push\s+(--force|--force-with-lease|-f)\b", "git push --force (履歴破壊、全ブランチ)"),
    (r"\bgit\s+push\s+--mirror\b", "git push --mirror (リモート全書換)"),
    (r"\bgit\s+filter-branch\b", "git filter-branch (履歴書換)"),
    (r"\bgit\s+clean\s+-[a-z]*f[a-z]*d\b", "git clean -fd (untracked削除)"),
    # --- 公開・本番デプロイ（取り消し不能） ---
    (r"\bnpm\s+(publish|unpublish)\b", "npm publish/unpublish (公開レジストリへの不可逆操作)"),
    (r"\bwrangler\s+deploy\b.*(--env|-e)\s+production\b", "wrangler deploy to production (本番デプロイ)"),
    # --- SQL 破壊操作 ---
    (r"\bDROP\s+TABLE\b", "SQL DROP TABLE"),
    (r"\bDROP\s+DATABASE\b", "SQL DROP DATABASE"),
    (r"\bTRUNCATE\s+TABLE\b", "SQL TRUNCATE TABLE"),
    (r"\bDELETE\s+FROM\s+\w+\s*;?\s*$", "WHERE 無し DELETE FROM"),
    # --- 設定改ざん（自分自身を無効化させない） ---
    (r"[>][>]?\s*~?/\.claude/settings\.json\b", "settings.json への書き込み (リダイレクト先として指定)"),
]


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        sys.exit(0)  # 入力壊れてたら通す（hookの責任ではない）

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}

    # Bash 系のみ判定
    if tool_name.lower() not in ("bash", "shell"):
        sys.exit(0)

    command = tool_input.get("command", "") or ""
    if not command:
        sys.exit(0)

    for pattern, reason in BLOCKED_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            print(
                f"[BLOCKED] ~/.claude/hooks/pretooluse-guard.py\n"
                f"  Reason: {reason}\n"
                f"  Pattern: {pattern}\n"
                f"  Command: {command}\n"
                f"  → 本当に必要な場合は人間が手動で実行してください。",
                file=sys.stderr,
            )
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
