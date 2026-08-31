## シークレット
- **コード内ハードコード禁止**（API キー、パスワード、トークン、DB接続文字列）
- 環境変数 (`.env`) or `~/.claude/settings.local.json` の `env` を使う
- API キーは個別管理台帳で管理し、コードに転載しない

## .gitignore 必須
- `.env`, `.env.*`
- `*.key`, `*.pem`
- `secrets/`, `credentials/`
- 個人情報を含むローカル設定ファイル（`CLAUDE.local.md` 等）は公開対象なら明示除外

## API キー取扱い
- 露出した瞬間ローテーション必須
- 台帳の `key_history` に旧キー・無効化日付・理由を記録
- 提供する時は最後4桁のみで参照

## SQL
- パラメータ化必須、文字列連結禁止（SQL injection 対策）
- DROP TABLE / DROP DATABASE / WHERE 無し DELETE は PreToolUse hook でブロック済

## ユーザー入力
- バリデーション必須（型・範囲・長さ）
- XSS 対策: HTML エスケープ、`innerHTML` 使用時は sanitize-html 等
- ファイルパス: path traversal 対策 (`../` 除去)

（本番システム固有のシークレット取扱いはプロジェクト個別の CLAUDE.md へ。顧客データの外部API送信禁止はグローバル CLAUDE.md の外部モデル使い分けで担保）
