## 命名規則
- JavaScript/TypeScript: camelCase (変数・関数), PascalCase (型・クラス・コンポーネント)
- CSS class: kebab-case
- Python: snake_case (変数・関数), PascalCase (クラス)
- ファイル名: kebab-case 推奨、Python のみ snake_case

## コード品質
- 関数は **単一責任**、20-30 行を目安に分割
- 早期 return で nest を浅く
- マジックナンバーは定数化
- console.log / print debug は最終コードに残さない（debug flag 使う）
- 200行超のファイルは分割を検討

## エラー処理
- 例外を握りつぶさない (`except: pass` 禁止)
- ユーザーに見える形でエラー通知（silent fail 禁止）
- 境界（外部API・ユーザー入力）で validate、内部は信頼

## コメント
- WHY を書く、WHAT は書かない（コードが語る）
- ハック・workaround の理由は必ず明記
- 「TODO:」「FIXME:」は理由＋日付込み

## 禁止事項
- 頼まれてない大規模リファクタ
- 「ついで改善」(無関係箇所の変更)
- 推測でのコメント・docstring 補完
