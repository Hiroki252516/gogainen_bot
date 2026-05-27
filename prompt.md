# Codex実装依頼プロンプト

あなたはこのリポジトリの実装担当です。`docs/` 以下の仕様書をすべて読み、学習ログ駆動型AIチューターを本格的に実装してください。

## 最重要ゴール

AI・情報系専門用語の概念理解支援を目的とした、誤概念タイプと足場掛けレベルに基づく学習ログ駆動型AIチューターを、Docker環境で動くWebアプリとして実装してください。

## 環境

- ユーザー環境: MacBook Air M4
- 実行方式: Docker / Docker Compose
- frontend: Next.js + TypeScript
- backend: FastAPI + Python
- db: PostgreSQL
- AI backend: OpenAI APIキーは使わない
- AI backendは Codex app-server 経由
- ただし app-server連携は抽象化し、まずMockAIBackendで全フローを動かしてください

## 必ず守ること

1. OpenAI APIキーを要求しない
2. OpenAI SDKで通常APIを直接呼ばない
3. AI呼び出しは必ず `AIBackend` インターフェース経由にする
4. `MockAIBackend` を必ず実装し、Codex app-serverなしでも全テストが通るようにする
5. `CodexAppServerBackend` を実装し、ユーザーのChatGPT/Codexログイン済みapp-serverへ接続できるようにする
6. ChatGPT/Codex認証情報をDBに保存しない
7. M1〜M4の内部ラベルを被験者画面に直接出さない
8. 研究ログとして、回答・AI診断・AI応答・足場掛けレベル更新をすべて保存する
9. CSVエクスポートを実装する
10. Docker Composeで一発起動できるようにする

## 開発対象

### Frontend

- `/start`
- `/survey/pre`
- `/pretest`
- `/diagnosing`
- `/learning-targets`
- `/learning/[termSlug]`
- `/retest`
- `/l0-check`
- `/transfer-test`
- `/survey/post`
- `/finish`
- `/admin`

### Backend

- participants API
- surveys API
- questions API
- attempts API
- diagnosis API
- tutor session API
- retest API
- L0 check API
- transfer test API
- evaluation summary API
- CSV export API
- Codex app-server status/login API

### Database

`docs/07_data_model.md` に従って実装してください。

### AI

`docs/10_ai_prompt_contracts.md` に従って実装してください。

AI機能は以下に分けてください。

- diagnose_answer
- generate_tutoring_turn
- grade_response
- generate_feedback

## Codex app-serverについて

Codex app-server連携は `docs/06_codex_app_server_integration.md` に従ってください。

MVPでは以下の方式を優先してください。

- Macホスト上で `codex app-server --listen ws://127.0.0.1:4500` を起動
- backendコンテナから `ws://host.docker.internal:4500` に接続

WebSocket auth tokenが設定されている場合はそれもサポートしてください。

## 実装順序

以下の順で作業してください。

1. プロジェクト雛形作成
2. Docker Compose構成
3. DB models + migrations
4. seed data
5. backend API
6. frontend flow
7. MockAIBackendで実験フロー完成
8. 評価指標とCSV export
9. Codex app-server client
10. テスト
11. README整備

## 完了条件

以下を確認してください。

- `docker compose up --build` で起動できる
- frontendが http://localhost:3000 で開ける
- backendが http://localhost:8000/api/health で応答する
- MockAIBackendで、事前テスト→診断→学習→再テスト→L0→転移→CSV出力まで動く
- proposed群では、M1〜M4に応じて教授方略が変わる
- proposed群では、正答でLが下がり、誤答でLが維持/上がる
- 同じ誤概念が再発した場合 recurrence_flag が true になる
- control群では一般解説のみになる
- app-server未接続時は分かりやすいエラーが出る
- READMEにセットアップ手順が書かれている

## 重要な設計判断

Codex app-serverは仕様変更の可能性があるため、アプリの研究ロジックとapp-server接続ロジックを密結合しないでください。

まずMockAIBackendで研究システムとして完成させ、その後CodexAppServerBackendを接続してください。

## 実装中に不明点が出た場合

研究仕様は `docs/00_project_summary.md` から順に参照してください。判断に迷う場合は、以下を優先してください。

1. 実験ログが残ること
2. 再現性があること
3. MockAIBackendで動くこと
4. Codex app-server連携を差し替え可能にすること
5. UIの豪華さより研究フローの正確さ
