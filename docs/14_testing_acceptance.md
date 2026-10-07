# 現行受け入れ検証

```sh
cd backend && .venv/bin/pytest -q
cd frontend && npm test
cd frontend && npm run build
git diff --check
```

- seedは事前3・再15・最終3。廃止問題は非activeで保存。
- 学習はv2の30問のみ。10択・3/3/3/1・デバッグ配置・M3優先・J単独を確認。
- 採点・結果確認・再学習・ギブアップ・ロック・冪等性・先行生成の回帰検証。
- final_test未採点の直接学習開始を拒否し、廃止専用URL/APIは404。
- 旧v1/v2/未対応版は409。旧POST、cached再送、先行生成でも値が不変。
- can_resume、ブラウザ新規開始、厳密入力、参加者向け正答非公開。
- 全3タイプ/両群のprompt・Schemaに廃止教授や支援量がなく、方略enumを固定。transfer_checkは必須。
- 履歴・生AI・保存評価・CSVを保持し、再計算/群集計しない。
- 隔離DBで移行とseed再実行を確認。

実AI確認はAI_BACKEND=codex_app_serverで接続・ログインを確認し、両群教材・正答要約・誤答解説をブラウザ操作する。実送信prompt、Schema、モデル・推論、共通RAG、版、教材長と照合する。Mock成功を実AI成功とみなさない。

## 2026-10-07の検証記録

- backend全136件、frontend smoke、frontend build、git diff --checkを実施。
- 隔離SQLiteで既存スキーマへのnullable列追加・seed再実行を確認。旧行・保存評価の不変を検証。
- 実app-server（gpt-5.6-luna / medium）で両群×M1/M3/unknownの6ケースをブラウザ確認。M1ケースは両群の誤答解説・次教材・正答要約まで確認。
- 送信監査ログで方略enum、現行版、旧教授入力の不在を照合。生成の欠落/文字数違反は検証で拒否し、Mockへは切り替えなかった。
- 旧試用の閲覧専用画面をdesktop/mobileで確認。ブラウザ状態だけの新規開始、旧POST/管理者削除の409、旧ログ表示、全問正解の事前/最終結果画面、廃止ページ404を確認。
- 管理画面の両群で現行参加者数と旧試用数の分離、API群集計との一致、保存評価の試用区分を確認。旧記録は個別ログに保持したまま、全体評価の現行一覧から除外。
- 起動した検証環境はbackend/.local/old-spec-validation.dbを使用し、従来の試用DBを変更していない。
