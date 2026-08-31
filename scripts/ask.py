#!/usr/bin/env python3
"""OpenRouter helper for routing prompts to non-Claude models.

Usage:
    python ask.py <alias> "<prompt>"

Aliases (see MODELS below). Reads OPENROUTER_API_KEY from env; falls back to
Windows User env via PowerShell when the current shell snapshot is stale.
"""
import sys
import os
import io
import json
import subprocess
import urllib.request
import urllib.error

# Force UTF-8 on Windows cp932 consoles
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)
except Exception:
    pass

MODELS = {
    # Coding / reasoning
    "codex": "openai/gpt-5",
    "gpt5": "openai/gpt-5",
    "gpt5-mini": "openai/gpt-5-mini",
    "gpt4o": "openai/gpt-4o",
    # Research / multimodal / long context
    "gemini": "google/gemini-2.5-pro",
    "gemini-flash": "google/gemini-2.5-flash",
    # Realtime / broad knowledge
    "grok": "x-ai/grok-4-fast",
    "grok-beta": "x-ai/grok-beta",
    # Anthropic (for comparison)
    "sonnet": "anthropic/claude-sonnet-4.6",
    "opus": "anthropic/claude-opus-4.7",
    # Open / cheap
    "deepseek": "deepseek/deepseek-chat",
    "llama": "meta-llama/llama-3.3-70b-instruct",
}

# Gemini direct API model mapping (used when GEMINI_API_KEY is set)
# 2026-07-26: 2.5 系は 3世代遅れだったため -latest エイリアスへ移行。
# Google 側が最新世代を指し続けるので、以後この表のメンテが不要になる（追従作業の削減が目的）。
# 世代を固定したい時のために 3.x の実 ID も残す。
GEMINI_DIRECT = {
    "gemini": "gemini-pro-latest",
    "gemini-flash": "gemini-flash-latest",
    "gemini-flash-lite": "gemini-flash-lite-latest",
    # 世代固定したい場合用（2026-07-26 時点の実在 ID）
    "gemini-3.6-flash": "gemini-3.6-flash",
    "gemini-3.5-flash": "gemini-3.5-flash",
    "gemini-3.1-pro": "gemini-3.1-pro-preview",
    "google/gemini-2.5-pro": "gemini-2.5-pro",
    "google/gemini-2.5-flash": "gemini-2.5-flash",
}

# Local Ollama model mapping (used when Ollama is running on localhost:11434)
# 2026-05-17: デフォルトを qwen3:14b に変更。
#   - 14b (8.3GB, Q4_K_M): 推論・コーディング・ツール呼び出し優秀、~60 t/s
#   - 8b (5.2GB, Q4_K_M): 軽バケ用、~77 t/s でレスポンス速い
OLLAMA_LOCAL = {
    "local": "qwen3:14b",
    "local-qwen": "qwen3:14b",
    "qwen-local": "qwen3:14b",
    # 軽量・高速用（小タスク・大量処理向け）
    "local-fast": "qwen3:8b",
    "qwen-8b": "qwen3:8b",
    # 無検閲（abliterated）。2026-07-26 追加:
    # CLAUDE.md に「外部AIに拒否されたらローカル無検閲へフォールバック」と書かれていたが、
    # local (qwen3:14b) は検閲ありで記述通りに動かなかった。実体へのエイリアスを新設して解消。
    "local-nc": "huihui_ai/qwen2.5-coder-abliterate:14b",
    "local-uncensored": "huihui_ai/qwen2.5-coder-abliterate:14b",
}

# Local llama.cpp server (Desktop/<internal-project>-server.bat): Qwen3.6-35B-A3B heretic via
# --n-cpu-moe, OpenAI-compatible on 127.0.0.1:8080.
# 2026-07-26 に「<internal-project>-server.bat 消滅」として無効化したが誤判定だった（デスクトップ直下
# ではなく Desktop/projects/<internal-project>/ 配下に存在（2026-08-29 移動）、モデル 21.8GB も健在）。
# 2026-08-23 復活: サーバ未起動なら call_llama_server が bat を自動起動して /health を待つ。
# これが死んでいた間、audition-queue の Qwen 系自動審査が全て 0/5 の偽陰性になっていた。
LLAMA_SERVER_BAT = os.path.expanduser("~/Desktop/projects/<internal-project>/<internal-project>-server.bat")
LLAMA_SERVER = {
    "local-smart": "<internal-project>-35b",
    "local-35b": "<internal-project>-35b",
}

# Anthropic direct API model mapping (used when ANTHROPIC_API_KEY is set).
# Pro プラン($20)解約後の Claude 従量課金経路。
# 2026-07-26 更新: Opus 5 / Sonnet 5 世代へ。価格は $/1M (入力/出力)。
#   claude-opus-5   $5 / $25   1M context — Fable 5 に近い性能を半額で
#   claude-sonnet-5 $3 / $15   1M context (2026-08-31 まで導入価格 $2 / $10)
#   claude-haiku-4-5 $1 / $5   200K context
#   claude-fable-5  $10 / $50  最上位。単価が倍なので明示指定時のみ
ANTHROPIC_DIRECT = {
    "haiku-direct": "claude-haiku-4-5",
    "sonnet-direct": "claude-sonnet-5",
    "opus-direct": "claude-opus-5",
    "claude-haiku": "claude-haiku-4-5",
    "claude-sonnet": "claude-sonnet-5",
    "claude-opus": "claude-opus-5",
    "claude-fable": "claude-fable-5",
}

# xAI direct API model mapping (used when XAI_API_KEY is set)
# 2026-07-26 更新: grok-4-fast / grok-4 は xAI のモデル一覧から消えており（応答はするが
# 退役間近と判断）、旧 ID は明示指定時のみ残置。
# 既定は grok-4.3 — コスパで 4.5 に勝るため（$/1M 入力/出力）:
#   grok-4.3  1.25 / 2.50  1M context   ← 既定
#   grok-4.5  2.00 / 6.00  500K context  出力が 2.4倍高く、文脈長は半分
# 素の能力が要る時だけ grok-4.5 を明示指定する。
XAI_DIRECT = {
    "grok": "grok-4.3",
    "grok-4.3": "grok-4.3",
    "grok-43": "grok-4.3",
    "grok-fast": "grok-4.3",
    "grok-4.5": "grok-4.5",
    "grok-45": "grok-4.5",
    "grok-pro": "grok-4.5",
    # 旧世代（一覧から消滅済み。動かなくなったら削除する）
    "grok-4-fast": "grok-4-fast",
    "grok-4": "grok-4",
    "x-ai/grok-4.5": "grok-4.5",
    "x-ai/grok-4.3": "grok-4.3",
}

# Grok Live Search モード (X+Web リアルタイム検索を有効化)
# 既存の grok エイリアスは LLM only (安い)、grok-live は Live Search 有効 (1検索$0.005追加)。
# 2026-06-03 追加: ask.py 既存のgrok呼び出しはchat/completions経由でLive Search不可だったため。
XAI_LIVE = {
    "grok-live": "grok-4.3",
    "grok-x": "grok-4.3",
    "grok-search": "grok-4.3",
    "grok-live-pro": "grok-4.5",
}

# NVIDIA NIM direct API — DEPRECATED 2026-05-23
# NIM 上の Kimi 系は全モデル EOL/消失（2026-05-12 確認）:
#   kimi-k2-instruct   → HTTP 410 "end of life on 2026-05-12"
#   kimi-k2-thinking   → HTTP 410 "end of life on 2026-05-12"
#   kimi-k2.5          → HTTP 404 (NIM カタログから削除)
#   kimi-k2-instruct-0905 → HTTP 404
# kimi/kimi-fast/kimi-pro 等の alias は下の OPENAI_DIRECT で gpt-5.4-mini に再配線済。
# Moonshot 本家直API（platform.moonshot.cn）は有料だが、codex-mini で代替十分のため未採用。
# OpenAI direct API model mapping (used when OPENAI_API_KEY is set).
# <budget> チャージ、<budget>/月 budget 上限設定済。
# 普段使いは gpt-5.4-mini（Kimi並に安い）、本気レビューは gpt-5.4。
# 2026-07-26 更新: 主力を GPT-5.6 (Sol/Terra/Luna の3階層ファミリー) へ。
# 数字が世代、Sol/Terra/Luna が能力ティア。価格は $/1M (入力/出力):
#   gpt-5.6-sol   $5 / $30   フラッグシップ。エージェント型コーディングで SOTA
#   gpt-5.6-terra $2.50 / $15 日常主力。GPT-5.5 と同等性能で半額（OpenAI 公称）
#   gpt-5.6-luna  $1 / $6    高速・低コスト枠
#   gpt-5.4-mini  $0.75 / $4.50  現時点でも最安クラス → codex は据え置き
# gpt-5.5 ($5/$30) と gpt-5.5-pro ($30/$180) は 5.6 に価格性能で劣るため主力から外した。
OPENAI_DIRECT = {
    "codex": "gpt-5.4-mini",           # 普段使い。luna($1/$6)より安いので据え置き
    "codex-pro": "gpt-5.6-terra",      # 本気レビュー。5.5 同等性能で半額
    "codex-max": "gpt-5.6-sol",        # 最上位フラッグシップ
    "gpt5.6-sol": "gpt-5.6-sol",
    "gpt5.6-terra": "gpt-5.6-terra",
    "gpt5.6-luna": "gpt-5.6-luna",
    "gpt5.5": "gpt-5.5",               # 旧世代。比較用に残置
    "gpt5.5-pro": "gpt-5.5-pro",       # $30/$180 と高額。sol で足りるはず
    # NOTE: gpt-5.3-codex (2026-02 リリース、xhigh モード) は登録済みだが、
    # 本アカウント（2026-04 取得・<budget>チャージ）では Usage Tier の都合で
    # /v1/chat/completions が 404 "not a chat model" を返す（要 Tier 上げ または別エンドポイント検証）。
    # Tier アップ後にこのまま使える想定で残置。
    "codex-5.3": "gpt-5.3-codex",
    "gpt5.3-codex": "gpt-5.3-codex",
    "gpt-5.3-codex": "gpt-5.3-codex",
    "openai/gpt-5.3-codex": "gpt-5.3-codex",
    "gpt5": "gpt-5.4-mini",
    "gpt5-pro": "gpt-5.6-terra",
    "gpt5-mini": "gpt-5.4-mini",
    "gpt5-nano": "gpt-5.4-nano",
    "gpt5.4": "gpt-5.4",
    "gpt5.4-mini": "gpt-5.4-mini",
    "openai/gpt-5.4": "gpt-5.4",
    "openai/gpt-5.4-mini": "gpt-5.4-mini",
    "openai/gpt-5-mini": "gpt-5.4-mini",
    "openai/gpt-5": "gpt-5.4-mini",
}

# 旧 kimi* alias は gpt-5.4-mini 再配線で codex と純重複だったため廃止 (2026-07-08)。
# main() 冒頭で警告を出して停止する。Kimi K2.7 本家は MOONSHOT_DIRECT の kimi-k2.7 を使う。
DEPRECATED_ALIASES = {
    "kimi": "codex (同一モデル gpt-5.4-mini) か kimi-k2.7 (Moonshot 本家)",
    "kimi-fast": "codex",
    "kimi-pro": "codex-pro",
    "kimi-k2.5": "kimi-k2.7",
    "kimi-thinking": "codex",
    "kimi-0905": "kimi-k2.7",
}

# OpenAI モデル別の reasoning_effort デフォルト指定。
# gpt-5.3-codex は xhigh で評価実施されたモデルなので xhigh を既定にする。
OPENAI_REASONING_EFFORT = {
    "gpt-5.3-codex": "xhigh",
}

# DeepSeek 直 API model mapping (used when DEEPSEEK_API_KEY is set)。
# OpenAI 互換、base = https://api.deepseek.com/v1/chat/completions
# 2026-07-26 確認: v4-pro が現行最新。新たに v4-flash（軽量・低価格枠）が追加されたので登録。
# 旧コメントにあった「プロモ価格 2026-05-05 まで」は期限切れ。実価格は公式ページで要確認。
DEEPSEEK_DIRECT = {
    "deepseek": "deepseek-v4-pro",
    "deepseek-pro": "deepseek-v4-pro",
    "deepseek-v4-pro": "deepseek-v4-pro",
    "deepseek-flash": "deepseek-v4-flash",
    "deepseek-v4-flash": "deepseek-v4-flash",
    "deepseek/deepseek-v4-pro": "deepseek-v4-pro",
}

NIM_DIRECT = {}  # All Kimi NIM models EOL/removed 2026-05-12. See header comment above.

# Moonshot 公式直 API（OpenAI 互換, base = https://api.moonshot.ai/v1）。
# 2026-06-12 公開の Kimi K2.7-Code（1T MoE / 32B active / 256K）をクラウド経由で利用。
# 旧 kimi* alias（gpt-5.4-mini フォールバック）とは衝突しない新規キーのみ。
# 要 MOONSHOT_API_KEY（platform.moonshot.ai 発行）。API 価格 $0.95/M in, $4.00/M out。
MOONSHOT_DIRECT = {
    "kimi-k2.7": "kimi-k2.7-code",
    "kimi-code": "kimi-k2.7-code",
    "kimi-k2.7-code": "kimi-k2.7-code",
    "kimi-k3": "kimi-k3",
}

# 智譜AI (Zhipu / Z.ai) 公式直 API（OpenAI 互換, base = https://api.z.ai/api/paas/v4）。
# GLM-5.2: 1M context / 128K output, コーディング向け。要 ZAI_API_KEY（z.ai 発行、id.secret 形式）。
ZHIPU_DIRECT = {
    "glm": "glm-5.2",
    "glm-5.2": "glm-5.2",
    "glm-5-turbo": "glm-5-turbo",
    "glm-4.6": "glm-4.6",
}


def get_gemini_key():
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    try:
        r = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "[Environment]::GetEnvironmentVariable('GEMINI_API_KEY', 'User')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        k = (r.stdout or "").strip()
        if k:
            return k
    except Exception:
        pass
    return None


def call_gemini_direct(model_id, prompt, max_tokens, key):
    body = json.dumps(
        {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        }
    ).encode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={key}"
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {err_body}", file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(4)

    candidates = resp.get("candidates") or []
    if not candidates:
        print(f"No candidates in response: {resp}", file=sys.stderr)
        sys.exit(5)
    parts = candidates[0].get("content", {}).get("parts", [])
    content = "".join(p.get("text", "") for p in parts)
    usage = resp.get("usageMetadata") or {}
    print(content)
    meta = f"[model={model_id} provider=gemini-direct tokens={usage.get('totalTokenCount', '?')} cost=free]"
    print(meta, file=sys.stderr)


def get_anthropic_key():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    try:
        r = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "[Environment]::GetEnvironmentVariable('ANTHROPIC_API_KEY', 'User')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        k = (r.stdout or "").strip()
        if k:
            return k
    except Exception:
        pass
    return None


def call_anthropic_direct(model_id, prompt, max_tokens, key):
    body = json.dumps(
        {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {err_body}", file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(4)

    content_list = resp.get("content") or []
    if not content_list:
        print(f"No content in response: {resp}", file=sys.stderr)
        sys.exit(5)
    content = content_list[0].get("text", "")
    usage = resp.get("usage") or {}
    in_t = usage.get("input_tokens", 0)
    out_t = usage.get("output_tokens", 0)
    # Anthropic 公式価格（2026-06 想定、$/1M tokens）。
    if "opus" in model_id:
        in_rate, out_rate = 15.00, 75.00
    elif "sonnet" in model_id:
        in_rate, out_rate = 3.00, 15.00
    elif "haiku" in model_id:
        in_rate, out_rate = 0.80, 4.00
    else:
        in_rate, out_rate = 3.00, 15.00
    cost = in_t / 1_000_000 * in_rate + out_t / 1_000_000 * out_rate
    print(content)
    meta = (
        f"[model={model_id} provider=anthropic-direct tokens={in_t}+{out_t} "
        f"cost=${cost:.5f}]"
    )
    print(meta, file=sys.stderr)


def get_xai_key():
    key = os.environ.get("XAI_API_KEY")
    if key:
        return key
    try:
        r = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "[Environment]::GetEnvironmentVariable('XAI_API_KEY', 'User')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        k = (r.stdout or "").strip()
        if k:
            return k
    except Exception:
        pass
    return None


def call_xai_direct(model_id, prompt, max_tokens, key):
    body = json.dumps(
        {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.x.ai/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {err_body}", file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(4)

    choices = resp.get("choices") or []
    if not choices:
        print(f"No choices in response: {resp}", file=sys.stderr)
        sys.exit(5)
    content = choices[0].get("message", {}).get("content", "")
    usage = resp.get("usage") or {}
    in_t = usage.get("prompt_tokens", 0)
    out_t = usage.get("completion_tokens", 0)
    # xAI 公式価格（$/1M tokens）。2026-07-26 に grok-4.5 を追加。
    # 4.3 / 4.5 とも入力200K超で倍料金になるが、簡易のため基本料金で計算（超えるケースは稀）。
    if model_id == "grok-4.5":
        in_rate, out_rate = 2.00, 6.00   # 500K context。4.3 より出力が 2.4 倍高い
    elif model_id == "grok-4.3":
        in_rate, out_rate = 1.25, 2.50   # 1M context。コスパ最良のため既定
    elif model_id == "grok-4":
        in_rate, out_rate = 3.00, 15.00
    elif "fast" in model_id:  # grok-4-fast / grok-4.1-fast
        in_rate, out_rate = 0.20, 0.50
    else:  # 未知モデルは高めに見積り（安く見せて驚かせない）
        in_rate, out_rate = 3.00, 15.00
    cost = in_t / 1_000_000 * in_rate + out_t / 1_000_000 * out_rate
    print(content)
    meta = (
        f"[model={model_id} provider=xai-direct tokens={in_t}+{out_t} "
        f"cost=${cost:.5f}]"
    )
    print(meta, file=sys.stderr)

    # grok-4.3 trial logging (2026-06-08 〜 +7日)
    if model_id == "grok-4.3":
        try:
            from datetime import datetime
            from pathlib import Path
            log_dir = Path.home() / ".claude" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            entry = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "cwd": os.getcwd(),
                "model": model_id,
                "prompt_preview": prompt[:120],
                "prompt_len": len(prompt),
                "response_len": len(content),
                "tokens_in": in_t,
                "tokens_out": out_t,
                "cost_usd": round(cost, 5),
            }
            with (log_dir / "grok-pro-trial.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass


def call_xai_live_search(model_id, prompt, max_tokens, key):
    """Live Search 有効化: /v1/responses + tools=[web_search, x_search]。
    1検索あたり $0.005 追加。レスポンス形式が chat/completions と異なるため別関数。
    """
    body = json.dumps(
        {
            "model": model_id,
            "input": [{"role": "user", "content": prompt}],
            "tools": [
                {"type": "web_search"},
                {"type": "x_search"},
            ],
            "max_output_tokens": max_tokens,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.x.ai/v1/responses",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {err_body}", file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(4)

    # /v1/responses のレスポンス形式: output[].content[].text (OpenAI Responses API 類似)
    content = ""
    output = resp.get("output") or []
    for item in output:
        for part in (item.get("content") or []):
            t = part.get("text") or part.get("output_text") or ""
            if t:
                content += t
    if not content:
        # fallback: 形式不明時は生レスポンスを出して確認
        content = json.dumps(resp, ensure_ascii=False, indent=2)
        print("WARN: unexpected response shape, dumping raw:", file=sys.stderr)

    usage = resp.get("usage") or {}
    in_t = usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0)
    out_t = usage.get("output_tokens", 0) or usage.get("completion_tokens", 0)
    # トークン課金 (fast = $0.20/$0.50)
    if "fast" in model_id:
        in_rate, out_rate = 0.20, 0.50
    elif model_id == "grok-4.3":
        in_rate, out_rate = 1.25, 2.50
    else:
        in_rate, out_rate = 3.00, 15.00
    token_cost = in_t / 1_000_000 * in_rate + out_t / 1_000_000 * out_rate
    # Live Search 課金: $5/1000 calls = $0.005/call
    # レスポンスからsearch回数を取得 (フィールド名はxAI仕様により異なる可能性、見つからなければ未集計)
    search_count = (
        usage.get("num_sources_used")
        or usage.get("search_count")
        or resp.get("num_searches")
        or 0
    )
    search_cost = search_count * 0.005
    total_cost = token_cost + search_cost
    print(content)
    meta = (
        f"[model={model_id} provider=xai-live-search tokens={in_t}+{out_t} "
        f"searches={search_count} cost=${total_cost:.5f} "
        f"(tokens=${token_cost:.5f}+search=${search_cost:.5f})]"
    )
    print(meta, file=sys.stderr)


def get_openai_key():
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    try:
        r = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "[Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'User')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        k = (r.stdout or "").strip()
        if k:
            return k
    except Exception:
        pass
    return None


# OpenAI 実価格表 ($/1M, 入力/出力)。2026-07-26 に公開価格で全面是正。
# 旧コードは mini を 3.6倍・nano を 5倍・上位モデルを最大12倍 過小表示していた
# （$0.25/$1.25 などリリース当初の推定値が残っていたため）。
OPENAI_PRICING = {
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.6-luna": (1.00, 6.00),
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.6-terra": (2.50, 15.00),
    "gpt-5.5": (5.00, 30.00),
    "gpt-5.6-sol": (5.00, 30.00),
    "gpt-5.5-pro": (30.00, 180.00),
    "gpt-5.3-codex": (1.25, 10.00),  # 未検証（Tier 制約で実利用できていない）
}


def openai_cost(model_id, in_t, out_t):
    """モデルIDから概算コストを返す。未知のモデルは最長一致で近いものを使い、
    それも無ければ最上位単価で見積もる（安く見せて驚くより高めに出す）。"""
    rate = OPENAI_PRICING.get(model_id)
    if rate is None:
        matches = [k for k in OPENAI_PRICING if model_id.startswith(k)]
        rate = OPENAI_PRICING[max(matches, key=len)] if matches else (5.00, 30.00)
    return in_t / 1_000_000 * rate[0] + out_t / 1_000_000 * rate[1]


def call_openai_direct(model_id, prompt, max_tokens, key, reasoning_effort=None):
    """OpenAI /v1/chat/completions を直接叩く（OpenRouter経由しない）。
    store=false で履歴を残さない（機密配慮）。
    reasoning_effort: "low" / "medium" / "high" / "xhigh" を指定すると body に追加。
    gpt-5.3-codex は xhigh で評価実施なので OPENAI_REASONING_EFFORT で自動指定される。
    """
    # gpt-5 系は max_completion_tokens を使う（max_tokens は廃止）。
    # temperature もデフォルト固定、custom不可の制約が来るケース多い。
    body_dict = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": max_tokens,
        "store": False,
    }
    if reasoning_effort:
        body_dict["reasoning_effort"] = reasoning_effort
    body = json.dumps(body_dict).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {err_body}", file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(4)

    choices = resp.get("choices") or []
    if not choices:
        print(f"No choices in response: {resp}", file=sys.stderr)
        sys.exit(5)
    content = (choices[0].get("message") or {}).get("content", "") or ""
    print(content)
    usage = resp.get("usage") or {}
    in_t = usage.get("prompt_tokens", 0)
    out_t = usage.get("completion_tokens", 0)
    cost = openai_cost(model_id, in_t, out_t)
    extra = f" reasoning={reasoning_effort}" if reasoning_effort else ""
    print(f"[model={model_id} provider=openai-direct tokens={in_t}+{out_t} cost=${cost:.5f}{extra}]", file=sys.stderr)


def get_deepseek_key():
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    try:
        r = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "[Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY', 'User')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        k = (r.stdout or "").strip()
        if k:
            return k
    except Exception:
        pass
    return None


def call_deepseek_direct(model_id, prompt, max_tokens, key):
    """DeepSeek /v1/chat/completions を直接叩く（OpenAI 互換）。
    プロモ価格（2026-05-31 15:59 UTC まで 75%OFF）:
      cache-miss 入力 $0.435/M, cache-hit 入力 $0.003625/M, 出力 $0.87/M
    フル価格（プロモ終了後）: cache-miss 入力 $1.74/M, 出力 $3.48/M
    """
    body = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {err_body}", file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(4)

    choices = resp.get("choices") or []
    if not choices:
        print(f"No choices in response: {resp}", file=sys.stderr)
        sys.exit(5)
    content = (choices[0].get("message") or {}).get("content", "") or ""
    print(content)
    usage = resp.get("usage") or {}
    in_t = usage.get("prompt_tokens", 0)
    out_t = usage.get("completion_tokens", 0)
    # cache hit/miss を分けて計算（usage に prompt_cache_hit_tokens / prompt_cache_miss_tokens がある）
    cache_hit_t = usage.get("prompt_cache_hit_tokens", 0)
    cache_miss_t = usage.get("prompt_cache_miss_tokens", in_t - cache_hit_t)
    # 2026-07-26 修正: 旧コードは 2026-05-31 に終了した 75%OFF プロモ単価のままで、
    # 実コストを 1/4 に過小表示していた。accounts.md 記載のフル価格に是正。
    #   cache-miss $1.74/M, output $3.48/M（accounts.md pricing_full）
    #   cache-hit  $0.0145/M（プロモ時 $0.003625 × 4。miss/output が正確に 4 倍なので同率で換算）
    cost = (
        cache_miss_t / 1_000_000 * 1.74
        + cache_hit_t / 1_000_000 * 0.0145
        + out_t / 1_000_000 * 3.48
    )
    cache_info = f" cache_hit={cache_hit_t}" if cache_hit_t else ""
    print(
        f"[model={model_id} provider=deepseek-direct tokens={in_t}+{out_t}{cache_info} cost=${cost:.5f}]",
        file=sys.stderr,
    )


def get_moonshot_key():
    key = os.environ.get("MOONSHOT_API_KEY")
    if key:
        return key
    try:
        r = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "[Environment]::GetEnvironmentVariable('MOONSHOT_API_KEY', 'User')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        k = (r.stdout or "").strip()
        if k:
            return k
    except Exception:
        pass
    return None


def call_moonshot_direct(model_id, prompt, max_tokens, key):
    """Moonshot /v1/chat/completions を直接叩く（OpenAI 互換）。
    価格: 入力 $0.95/M, 出力 $4.00/M（2026-06 時点）。
    """
    body = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 1.0,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.moonshot.ai/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {err_body}", file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(4)

    choices = resp.get("choices") or []
    if not choices:
        print(f"No choices in response: {resp}", file=sys.stderr)
        sys.exit(5)
    content = (choices[0].get("message") or {}).get("content", "") or ""
    print(content)
    usage = resp.get("usage") or {}
    in_t = usage.get("prompt_tokens", 0)
    out_t = usage.get("completion_tokens", 0)
    cost = in_t / 1_000_000 * 0.95 + out_t / 1_000_000 * 4.00
    print(
        f"[model={model_id} provider=moonshot-direct tokens={in_t}+{out_t} cost=${cost:.5f}]",
        file=sys.stderr,
    )


def get_zhipu_key():
    key = os.environ.get("ZAI_API_KEY")
    if key:
        return key
    try:
        r = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "[Environment]::GetEnvironmentVariable('ZAI_API_KEY', 'User')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        k = (r.stdout or "").strip()
        if k:
            return k
    except Exception:
        pass
    return None


def call_zhipu_direct(model_id, prompt, max_tokens, key):
    """智譜AI (Z.ai) /paas/v4/chat/completions を直接叩く（OpenAI 互換, Bearer 認証）。
    料金は z.ai/pricing 参照（モデルにより変動するため固定計算しない）。
    """
    body = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.6,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.z.ai/api/paas/v4/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {err_body}", file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(4)

    choices = resp.get("choices") or []
    if not choices:
        print(f"No choices in response: {resp}", file=sys.stderr)
        sys.exit(5)
    content = (choices[0].get("message") or {}).get("content", "") or ""
    print(content)
    usage = resp.get("usage") or {}
    in_t = usage.get("prompt_tokens", 0)
    out_t = usage.get("completion_tokens", 0)
    print(
        f"[model={model_id} provider=zhipu-direct tokens={in_t}+{out_t} cost=see z.ai/pricing]",
        file=sys.stderr,
    )


def get_nim_key():
    key = os.environ.get("NVIDIA_NIM_API_KEY")
    if key:
        return key
    try:
        r = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "[Environment]::GetEnvironmentVariable('NVIDIA_NIM_API_KEY', 'User')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        k = (r.stdout or "").strip()
        if k:
            return k
    except Exception:
        pass
    return None


def call_nim_direct(model_id, prompt, max_tokens, key):
    """NVIDIA NIM の OpenAI互換エンドポイントを叩く。thinking系モデルは
    chat_template_kwargs.thinking=True を自動付与、それ以外は非thinking(=速い)。
    """
    is_thinking = "thinking" in model_id
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.6,
        "top_p": 0.95,
        "stream": False,
    }
    if is_thinking:
        payload["chat_template_kwargs"] = {"thinking": True}
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://integrate.api.nvidia.com/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {err_body}", file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(4)

    choices = resp.get("choices") or []
    if not choices:
        print(f"No choices in response: {resp}", file=sys.stderr)
        sys.exit(5)
    msg = choices[0].get("message") or {}
    content = msg.get("content", "") or ""
    reasoning = msg.get("reasoning_content", "") or ""
    # thinking付きモデルは reasoning_content に思考が入る。表示は本文だけ。
    print(content)
    usage = resp.get("usage") or {}
    meta_bits = [f"model={model_id}", "provider=nim-direct", f"tokens={usage.get('total_tokens', '?')}"]
    if reasoning:
        meta_bits.append(f"reasoning={len(reasoning)}chars(hidden)")
    meta_bits.append("cost=free")
    print("[" + " ".join(meta_bits) + "]", file=sys.stderr)


def call_ollama_local(model_id, prompt, max_tokens):
    body = json.dumps(
        {
            "model": model_id,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {"num_predict": max_tokens},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(
            f"ERROR: Ollama not reachable on 127.0.0.1:11434. Is it running? ({e})",
            file=sys.stderr,
        )
        sys.exit(6)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(4)

    content = resp.get("response", "")
    eval_count = resp.get("eval_count", 0)
    eval_duration_ns = resp.get("eval_duration", 1)
    tps = eval_count / (eval_duration_ns / 1e9) if eval_duration_ns else 0
    print(content)
    meta = f"[model={model_id} provider=ollama-local tokens={eval_count} speed={tps:.1f}tok/s cost=free]"
    print(meta, file=sys.stderr)


def _llama_server_healthy():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def ensure_llama_server(wait_sec=180):
    """サーバ未起動なら <internal-project>-server.bat を別ウィンドウで起動し、/health が 200 になるまで待つ。
    35B の GGUF ロードに 30-90 秒かかるため長めに待つ。無人の自動審査でも失敗しないための措置。"""
    if _llama_server_healthy():
        return True
    if not os.path.isfile(LLAMA_SERVER_BAT):
        print(f"ERROR: {LLAMA_SERVER_BAT} が見つからない", file=sys.stderr)
        return False
    print("[llama-server] 未起動のため自動起動中 (最大 %ds 待機)..." % wait_sec, file=sys.stderr)
    # `cmd /c start ... <bat>` は日本語パス + 混在スラッシュで無言失敗したため、
    # bat を直接 cmd /c で起動し、新規コンソール + デタッチで親と切り離す（実証済み）。
    bat = os.path.normpath(LLAMA_SERVER_BAT)
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)  # DETACHED_PROCESS と併用不可
    subprocess.Popen(["cmd", "/c", bat], creationflags=flags, close_fds=True)
    import time
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        if _llama_server_healthy():
            return True
        time.sleep(3)
    return False


def call_llama_server(model_id, prompt, max_tokens):
    """Local llama.cpp server (<internal-project>-server.bat): OpenAI-compatible chat endpoint for
    the 35B via --n-cpu-moe. Thinking is forced off (this model over-reasons) so it
    returns the answer/code directly."""
    if not ensure_llama_server():
        print("ERROR: local 35B server could not be started (127.0.0.1:8080).", file=sys.stderr)
        sys.exit(6)
    body = json.dumps(
        {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.3,
            "chat_template_kwargs": {"enable_thinking": False},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8080/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(
            "ERROR: local 35B server not reachable on 127.0.0.1:8080. "
            f"Start Desktop/<internal-project>-server.bat first. ({e})",
            file=sys.stderr,
        )
        sys.exit(6)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(4)

    content = resp["choices"][0]["message"].get("content", "")
    t = resp.get("timings", {})
    tps = t.get("predicted_per_second", 0)
    print(content)
    meta = f"[model={model_id} provider=llama-server-local tokens={t.get('predicted_n', '?')} speed={tps:.1f}tok/s cost=free]"
    print(meta, file=sys.stderr)


def get_api_key():
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    try:
        r = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "[Environment]::GetEnvironmentVariable('OPENROUTER_API_KEY', 'User')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        k = (r.stdout or "").strip()
        if k:
            return k
    except Exception:
        pass
    return None


def main():
    if len(sys.argv) < 3 or sys.argv[1] in ("-h", "--help"):
        print("Usage: ask.py <alias> <prompt>")
        print(f"Aliases (OpenRouter): {', '.join(MODELS.keys())}")
        direct_aliases = sorted(set(
            list(OPENAI_DIRECT) + list(DEEPSEEK_DIRECT) + list(MOONSHOT_DIRECT)
            + list(ZHIPU_DIRECT) + list(ANTHROPIC_DIRECT) + list(XAI_DIRECT)
            + list(GEMINI_DIRECT) + list(OLLAMA_LOCAL) + list(LLAMA_SERVER)
        ))
        print(f"Aliases (direct API/local): {', '.join(direct_aliases)}")
        print("Or pass a full model id (e.g. x-ai/grok-4-fast)")
        sys.exit(1 if len(sys.argv) < 3 else 0)

    alias = sys.argv[1]
    if alias in DEPRECATED_ALIASES:
        print(
            f"[DEPRECATED] alias '{alias}' は 2026-07-08 に廃止されました。"
            f"代わりに '{DEPRECATED_ALIASES[alias]}' を使ってください。",
            file=sys.stderr,
        )
        sys.exit(2)
    prompt = sys.argv[2]
    model = MODELS.get(alias, alias)
    # Third positional arg overrides max_tokens; default keeps OpenRouter credit gate happy
    try:
        max_tokens = int(sys.argv[3]) if len(sys.argv) > 3 else 4000
    except ValueError:
        max_tokens = 4000

    # Route the local 35B aliases to the fast llama.cpp server (--n-cpu-moe) on :8080
    server_model = LLAMA_SERVER.get(alias)
    if server_model:
        call_llama_server(server_model, prompt, max_tokens)
        return

    # Route local aliases to Ollama HTTP API on 127.0.0.1:11434
    ollama_model = OLLAMA_LOCAL.get(alias)
    if ollama_model:
        call_ollama_local(ollama_model, prompt, max_tokens)
        return

    # Route OpenAI aliases (codex/gpt5) to direct OpenAI API when OPENAI_API_KEY is set
    openai_model = OPENAI_DIRECT.get(alias) or OPENAI_DIRECT.get(model)
    if openai_model:
        okey = get_openai_key()
        if okey:
            reasoning = OPENAI_REASONING_EFFORT.get(openai_model)
            call_openai_direct(openai_model, prompt, max_tokens, okey, reasoning_effort=reasoning)
            return

    # Route DeepSeek aliases to direct DeepSeek API when DEEPSEEK_API_KEY is set
    deepseek_model = DEEPSEEK_DIRECT.get(alias) or DEEPSEEK_DIRECT.get(model)
    if deepseek_model:
        dkey = get_deepseek_key()
        if dkey:
            call_deepseek_direct(deepseek_model, prompt, max_tokens, dkey)
            return

    # Route Kimi K2.7 aliases to Moonshot 公式直 API（OpenAI 互換）
    moonshot_model = MOONSHOT_DIRECT.get(alias) or MOONSHOT_DIRECT.get(model)
    if moonshot_model:
        mkey = get_moonshot_key()
        if not mkey:
            print(
                "ERROR: MOONSHOT_API_KEY not set. Register via PowerShell: "
                'setx MOONSHOT_API_KEY "sk-..." '
                "(platform.moonshot.ai で発行)",
                file=sys.stderr,
            )
            sys.exit(2)
        call_moonshot_direct(moonshot_model, prompt, max_tokens, mkey)
        return

    # Route GLM aliases to 智譜AI (Z.ai) 公式直 API（OpenAI 互換）
    zhipu_model = ZHIPU_DIRECT.get(alias) or ZHIPU_DIRECT.get(model)
    if zhipu_model:
        zkey = get_zhipu_key()
        if not zkey:
            print(
                "ERROR: ZAI_API_KEY not set. Register via PowerShell: "
                'setx ZAI_API_KEY "id.secret" (z.ai で発行)',
                file=sys.stderr,
            )
            sys.exit(2)
        call_zhipu_direct(zhipu_model, prompt, max_tokens, zkey)
        return

    # Route Kimi aliases to NVIDIA NIM direct API when NVIDIA_NIM_API_KEY is set
    nim_model = NIM_DIRECT.get(alias) or NIM_DIRECT.get(model)
    if nim_model:
        nkey = get_nim_key()
        if nkey:
            call_nim_direct(nim_model, prompt, max_tokens, nkey)
            return

    # Route Anthropic aliases to direct Anthropic API when ANTHROPIC_API_KEY is set.
    # Pro プラン解約後の Claude 従量経路: haiku-direct / sonnet-direct / opus-direct
    anthropic_model = ANTHROPIC_DIRECT.get(alias) or ANTHROPIC_DIRECT.get(model)
    if anthropic_model:
        akey = get_anthropic_key()
        if akey:
            call_anthropic_direct(anthropic_model, prompt, max_tokens, akey)
            return

    # Route Grok Live Search aliases (X+web リアルタイム検索有効) を先に判定
    xai_live_model = XAI_LIVE.get(alias) or XAI_LIVE.get(model)
    if xai_live_model:
        xkey = get_xai_key()
        if xkey:
            call_xai_live_search(xai_live_model, prompt, max_tokens, xkey)
            return

    # Route Grok aliases to xAI direct API when XAI_API_KEY is set
    xai_model = XAI_DIRECT.get(alias) or XAI_DIRECT.get(model)
    if xai_model:
        xkey = get_xai_key()
        if xkey:
            call_xai_direct(xai_model, prompt, max_tokens, xkey)
            return

    # Route Gemini aliases to direct Google API when GEMINI_API_KEY is available
    gemini_model = GEMINI_DIRECT.get(alias) or GEMINI_DIRECT.get(model)
    if gemini_model:
        gkey = get_gemini_key()
        if gkey:
            call_gemini_direct(gemini_model, prompt, max_tokens, gkey)
            return

    key = get_api_key()
    if not key:
        print(
            "ERROR: OPENROUTER_API_KEY not set. Register via PowerShell: "
            'setx OPENROUTER_API_KEY "sk-or-v1-..."',
            file=sys.stderr,
        )
        sys.exit(2)

    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://claude-code",
            "X-Title": "Claude Code Router Helper",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {err_body}", file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(4)

    choices = resp.get("choices") or []
    if not choices:
        print(f"No choices in response: {resp}", file=sys.stderr)
        sys.exit(5)
    content = choices[0].get("message", {}).get("content", "")
    usage = resp.get("usage") or {}
    print(content)
    meta = f"[model={model} tokens={usage.get('total_tokens', '?')} cost=${resp.get('usage', {}).get('cost', '?')}]"
    print(meta, file=sys.stderr)


if __name__ == "__main__":
    main()
