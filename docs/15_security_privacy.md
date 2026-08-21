# 15. Security and Privacy

## 個人情報

MVPでは個人名・メールアドレスを収集しない。被験者IDのみ使用する。

保存しない:

- 氏名
- メールアドレス
- 学籍番号
- 電話番号
- ChatGPT認証情報
- APIキー

## ChatGPT/Codex認証

- ChatGPT認証情報をDBに保存しない
- `~/.codex/auth.json` をアプリで直接読み取らない
- app-serverの認証状態は `account/read` で確認する
- logout機能を管理画面に置いてもよいが、誤操作防止の確認を入れる

## app-serverの公開範囲

- `127.0.0.1` のみにバインドする
- `0.0.0.0` で公開しない
- 可能なら capability token を使う
- 非ローカル公開はしない
- Docker Desktop for Mac上のbackendからは `host.docker.internal:4500` へ接続する

## 実験データ

保存する:

- 回答
- 理由記述
- 自信度は事前テストと学習セッションでは収集しない
- 回答時間
- AI診断
- AI応答
- 学習ログ
- 学習ステージ更新と互換scaffolding_level更新
- 手動修正ログ

保存しない:

- 個人名
- メールアドレス
- ChatGPTアクセストークン
- APIキー

## AI出力の注意

AI診断は誤る可能性がある。管理画面に診断信頼度とAI理由を表示し、必要に応じて手動修正できるようにする。

手動修正:

- 修正前後を `audit_events` に保存
- 修正理由を必須にする
- CSVで手動修正済みか判別可能にする

## 削除機能

管理画面に以下を実装する。

- 被験者1名分の削除
- 全実験データの削除
- CSVエクスポート後の確認

削除操作は確認ダイアログを必須にし、`audit_events` に残す。

## ローカル用途

このシステムは卒業研究用のローカル実験システムであり、インターネットに公開しない。

## ログ出力

アプリケーションログに出してよいもの:

- participant display_code
- API endpoint
- error_code
- latency

出してはいけないもの:

- ChatGPT token
- capability token
- raw auth response
- secret file pathの中身

## CSV取扱い

CSVは研究分析用データである。個人情報は含めないが、回答テキストが含まれるため、外部公開しない。

CSV出力先:

- `exports/`
- gitignore対象

## セキュリティ上の実装禁止事項

- OpenAI APIキー入力欄
- 認証トークンのDB保存
- app-serverの外部公開
- 管理画面の削除APIを確認なしで実行
- 被験者画面から管理者APIを呼べる設計
