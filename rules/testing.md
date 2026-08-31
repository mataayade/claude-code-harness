## テストフレームワーク
- Python: **pytest** (`pip install pytest pytest-asyncio`)
- JavaScript/TypeScript: **Jest** または **Vitest**
- E2E: **Playwright** (Chrome拡張・Web App とも)

## ファイル配置
- Python: `tests/` ディレクトリにソース構造をミラー
  - `src/foo.py` → `tests/test_foo.py`
- JS/TS: ソース隣接 (`foo.ts` → `foo.test.ts`)
- Chrome 拡張: `tests/e2e/` 配下に Playwright スペック

## テスト命名
- Python: `test_<関数名>_<シナリオ>` (例: `test_parse_url_with_query_params`)
- JS: `describe('<対象>', () => { it('<挙動>', ...) })`

## 必須カバレッジ
- 新規関数 1個 = 最低1テスト（ハッピーパス）
- バグ修正 = 再現テスト先に書いて pass させる (TDD)
- 公開API・外部 boundary は edge case 必須

## モック方針
- **DB はモックしない**（実DB or testcontainers）→ 過去にモック合格→prod失敗の事故あり
- 外部API は moto/responses/httpx_mock 等で stub
- 時刻は freezegun (Python) or jest fake timers (JS)

（本番システム固有のテスト方針（クローン環境・記録モード再生）はプロジェクト個別の CLAUDE.md へ）
