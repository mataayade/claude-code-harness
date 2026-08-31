# claude-code-harness

[![test](https://github.com/mataayade/claude-code-harness/actions/workflows/test.yml/badge.svg)](https://github.com/mataayade/claude-code-harness/actions/workflows/test.yml)

Claude Code を一人で本番運用するための「箱」（ハーネス = 実行基盤）。
hook による決定論ゲート、実装と判定の分離、モデル振り分けによるコスト制御を、実際の事故から積み上げたもの。

A solo-operator harness for Claude Code: deterministic guardrails (hooks), separated implementer/evaluator agents, and cost-aware model routing. Built incrementally from real incidents (see `docs/incidents.md`). Japanese-first; English summary at the end.

---

## これは何か

- 2026-05 から継続運用中（セッション 225 回、作業ログ 70 日分）の個人環境から、機密を除去して切り出したもの
- 対象は「AI にタスクを委譲し、結果を検証し、壊れたら仕組みで直す」運用そのもの。アプリではない
- 構成要素は 4 つ: `hooks/`（ゲート）、`agents/`（役割分離）、`scripts/ask.py`（外部モデル振り分け）、`rules/` + `CLAUDE.md`（運用ルール）

## 設計思想（3 本）

### 1. 確率で守らず、決定論で守る

「絶対に起きてはいけないこと」（破壊的コマンド・決済・本番データの外部送信）は、プロンプトの指示（守られる確率 95〜99%）ではなく PreToolUse hook（100%）で止める。
指示で守っているだけの箇所を見つけたら hook 化する。逆に、頻度が低く可逆なものは運用ルールに留める。この取捨選択は `docs/incidents.md` の「ステータス」列に現れている。

| 守る対象 | 手段 | hook |
|---|---|---|
| `rm -rf` / `DROP TABLE` / `git push --force`（全ブランチ）/ `npm publish` / 本番 `wrangler deploy` / 秘密鍵の直書き | 拒否 (exit 2) | `hooks/pretooluse-guard.py` |
| 課金を伴う操作（決済 API、有料サービス起動） | 人間に承認を求める (permissionDecision=ask) | `hooks/pretooluse-cost-gate.py` |
| 機密ファイル参照 + 外部 API 送信が同一コマンドに共存 | 人間に承認を求める | `hooks/pretooluse-external-send-gate.py` |
| Bash heredoc（ツール呼び出し破損の実績あり） | 拒否 + 代替手順を提示 | `hooks/pretooluse-heredoc-gate.py` |
| Python の構文エラー・未定義名 | 編集直後に ruff で検出 (exit 2) | `hooks/posttooluse-lint-gate.py` |

拒否メッセージには必ず「正しい代替手順」を書く。AI が正規ルートを選ぶ方が、抜け道より判断が少なくなるように設計する。

### 2. 実装と判定を分ける

実装した agent が自分の変更を自分で合格にしない。`agents/evaluator.md` はコード変更権限を持たず、Playwright で実機操作して PASS / FAIL と差し戻し項目だけを返す。
sub-agent は「2〜3 ツール・単一責務・親には要約と判定だけ返す」に統一。直列 10 ステップで成功率が大きく落ちる（コンテキスト汚染）ため、長工程は親が分割する。

### 3. コストは設計で下げる

| 作業の種類 | 振り分け先 | 理由 |
|---|---|---|
| 探索・要約・雛形 | 軽量モデル (haiku 相当) | 頻度 80〜90% を最安で回す |
| 通常実装 | 中位モデル (sonnet 相当) | 品質と単価の均衡 |
| 設計・監査・難所 | 上位モデル | 委譲が割に合わない箇所だけ |
| 要約・翻訳・機密混じり | ローカル LLM (Ollama / llama.cpp) | 単価 0、データが外に出ない |
| 最新情報・セカンドオピニオン | 外部 API (`scripts/ask.py`) | 単独判断の誤りを外部で検証 |

## 構成

```
+-------------------+      PreToolUse       +----------------------+
|  Claude Code CLI  | --------------------> |  hooks/ (5 gates)    |
|  (main session)   | <-- exit 0/2, ask --- |  guard / cost / send |
+---------+---------+                       |  heredoc / lint      |
          |                                 +----------------------+
          | Agent tool
          v
+-------------------+   summary + verdict   +----------------------+
|  agents/          | --------------------> |  main session        |
|  evaluator        |   (no raw logs)       |  (integrates, judges)|
|  external-researcher                      +----------------------+
|  codex-implementer|
+---------+---------+
          | Bash
          v
+-------------------+
|  scripts/ask.py   | --> cloud APIs (per-task alias) / local Ollama (127.0.0.1)
+-------------------+
```

## トレードオフ表（何を捨てて何を取ったか）

| 判断 | 取ったもの | 捨てたもの | 根拠 |
|---|---|---|---|
| hook で機械的に拒否 | 事故率 0 | 誤検知で正当な操作が止まる（代替手順の提示で吸収） | 2026-07-09 heredoc 破損 |
| heredoc 全面禁止 | ツール呼び出しの安定 | 複数行コマンドの利便性 | 同上 |
| 意見・判断は外部 AI で検証してから出す | 単独妄想による撤回を削減 | 1 回 10〜60 秒の遅延と API 費 | 2026-05 の連続誤判断 |
| 特定プロバイダをクロスチェックから除外 | 検証品質 | 無料枠の活用 | 実運用で指摘の具体性が低かった |
| ローカル LLM を機密処理の既定に | データ流出リスク 0、API 費 0 | 応答品質・速度（14B: 46 tok/s、35B MoE: 38 tok/s、RTX 4070 12GB 実測） | 顧客データを含む処理の存在 |
| sub-agent は要約だけ返す | 親コンテキストの汚染防止 | 試行錯誤の可視性 | 長工程での成功率低下 |
| 運用ルールは CLAUDE.md、絶対禁止は hook | 保守コスト | 100% 強制の範囲 | `docs/incidents.md` 補足参照 |

## 実測値（出典付き・推定なし）

| 指標 | 値 | 出典 |
|---|---|---|
| セッション数 | 225（2026-05-23〜08-29） | `session-start-logger.py` の JSONL |
| 作業ログ | 70 日分（2026-04-21〜08-29） | `session-end-worklog.py` の日次 md |
| hook 発火の記録 | 19 件 / 11 日 | 作業ログ内の BLOCKED 記録 |
| 蓄積した運用ルール (memory) | 73 件（うち feedback 37） | memory ディレクトリ（本リポジトリには含めない） |
| ローカル推論速度 | 14B 46 tok/s / 35B-A3B 38 tok/s | RTX 4070 12GB、llama.cpp / Ollama 実測 |
| テスト | 23 passed | `pytest -q`（hook 18 + MCP サーバー 5） |

**未計測（正直に）**: 外部 API の総コストとモデル振り分けによる削減額。プロバイダ横断の使用量台帳が無く、算出できない。次の改善項目。

## 使い方

```bash
pip install -r requirements-dev.txt
pytest -q                      # hook の挙動をサンプル入力で検証
python sanitize.py             # 公開前ゲート: 禁止語が残っていれば exit 1
```

自分の環境に入れる場合は `hooks/` を `~/.claude/hooks/` へ、`settings.example.json` の `hooks` 節を `~/.claude/settings.json` へ写す。`scripts/ask.py` のプロバイダ alias と環境変数名は自分のものに書き換える（キーは環境変数のみ、コードに書かない）。

## MCP サーバー

`mcp_server.py` は上記の hook ゲートを MCP (Model Context Protocol、AI とツールを繋ぐ標準プロトコル) のツールとして公開する。Claude Code に限らず、MCP に対応した任意のクライアントから呼び出せる。ネットワーク通信・機密読み書きなし、stdio (標準入出力) トランスポートのみ。

- `guard_check(command)` — `hooks/pretooluse-guard.py` に判定させ、`{"decision": "allow"|"block", "reason": ..., "exit_code": ...}` を返す
- `sanitize_scan(text)` — `sanitize.py` の禁止パターンをテキスト1件だけに対して走らせ（リポジトリ全体はスキャンしない）、`{"clean": bool, "hits": [...]}` を返す

Claude Code へ登録する場合:

```bash
claude mcp add claude-code-harness -- python /path/to/claude-code-harness-public/mcp_server.py
```

または `.mcp.json` に直接:

```json
{
  "mcpServers": {
    "claude-code-harness": {
      "command": "python",
      "args": ["/path/to/claude-code-harness-public/mcp_server.py"]
    }
  }
}
```

事前に `pip install -r requirements.txt`（`mcp` パッケージのみ）が必要。

## 機密除去について

このリポジトリは本番環境のコピーを `sanitize.py` に通したもの。本番システム名・個人名・メール・金額・ドメイン・ローカル設定 (`CLAUDE.local.md`)・memory は含まない。
「公開文書に個人情報を書かない」という運用ルールを、人の注意力ではなくスクリプトで強制している（設計思想 1 と同じ考え方）。

## 限界

- 利用者 1 人の環境。マルチユーザー・チーム運用での検証はしていない
- Windows 中心（PowerShell / .bat の罠が `docs/incidents.md` に多い）。CI は Linux で毎 push 実行
- hook で 100% 強制しているのは「絶対禁止」の 2 系統だけで、残りは運用ルール（`CLAUDE.md` / `rules/`）依存

## 関連ドキュメント

- `docs/incidents.md` — 事故 → 根本原因 → 再発防止の対応表
- `rules/` — コーディング / セキュリティ / テスト / 用語表記のルール
- `CLAUDE.md` — メインセッションの運用指示（振り分け・確認ルール・エージェント設計則）

---

## English summary

A production harness for running Claude Code as a solo operator since 2026-05 (225 sessions). Three principles: (1) enforce must-never-happen actions with PreToolUse hooks (deterministic) rather than prompt instructions (probabilistic); (2) separate the implementing agent from the evaluating agent, which has no write access and returns only verdicts; (3) route work by cost — light models for high-frequency tasks, local LLMs for anything confidential, external APIs for second opinions. Every guardrail here was added after a real incident, documented in `docs/incidents.md`. `pytest` exercises each hook with sample tool inputs; `sanitize.py` is the pre-publish gate that keeps private data out. Known gap: no cross-provider cost ledger yet.

License: MIT
