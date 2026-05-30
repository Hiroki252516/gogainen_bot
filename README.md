# 学習ログ駆動型AIチューター 開発仕様リポジトリ

このリポジトリは、卒業研究で使う「誤概念タイプと足場掛けレベルに基づく AI・情報系専門用語の概念理解支援システム」の仕様と実装を含みます。

`docs/` 以下に研究・設計仕様、`backend/` にFastAPIアプリ、`frontend/` にNext.jsアプリがあります。

## 研究の要点

研究の比較対象は「AIを使うかどうか」ではありません。比較対象は「一般的なAI解説」と「学習ログに基づいて誤概念タイプ・足場掛けレベル・教授方略を変えるAIチューター」です。

主評価指標は次の3つです。

1. 同種誤答再発率
2. 足場掛けなし自力解答率
3. 足場掛けなし転移率

## 実装で守る前提

- OpenAI APIキーは使わない
- OpenAI SDKで通常APIを直接呼ばない
- AI呼び出しは `AIBackend` 抽象インターフェース経由にする
- 通常実行では `CodexAppServerBackend` を使い、ユーザーのChatGPT/CodexログインでAIを呼び出す
- `MockAIBackend` は自動テスト・CI・app-server切り分け専用に残す
- ChatGPT/Codex認証情報をDBへ保存しない
- 被験者画面に `M1` から `M4` の内部ラベルを直接表示しない
- 回答、理由、自信度、AI診断、AI応答、足場掛け更新を研究ログとして保存する
- 実験分析に必要なCSVを出力できるようにする

## 推奨構成

- frontend: Next.js + TypeScript
- backend: FastAPI + Python
- db: PostgreSQL
- ai-adapter: Codex app-server JSON-RPC client
- analysis: CSV export + pandas互換出力
- dev runtime: Docker / Docker Compose

## 仕様書一覧

| File | 内容 |
|---|---|
| `docs/00_project_summary.md` | 研究とシステムの全体像 |
| `docs/01_research_requirements.md` | 研究課題、仮説、実験条件 |
| `docs/02_experiment_flow.md` | 被験者フローと状態遷移 |
| `docs/03_misconception_taxonomy.md` | 最終M1〜M4分類と旧分類からの対応 |
| `docs/04_scaffolding_and_tutoring.md` | 足場掛け、教授方略、チャット制御 |
| `docs/05_system_architecture.md` | システム構成とモジュール境界 |
| `docs/06_codex_app_server_integration.md` | Codex app-server連携方針 |
| `docs/07_data_model.md` | DBテーブル、enum、保存ルール |
| `docs/08_backend_api_spec.md` | REST API仕様 |
| `docs/09_frontend_ux_flow.md` | 画面遷移、UI要件、禁止表示 |
| `docs/10_ai_prompt_contracts.md` | AI入出力スキーマとプロンプト契約 |
| `docs/11_seed_questions.md` | 初期問題、選択肢、転移問題在庫 |
| `docs/12_evaluation_metrics.md` | 評価指標、CSV、分析仕様 |
| `docs/13_docker_development.md` | Docker開発環境 |
| `docs/14_testing_acceptance.md` | テスト・受け入れ条件 |
| `docs/15_security_privacy.md` | セキュリティと個人情報方針 |
| `docs/16_implementation_tasks.md` | 実装タスク分解 |
| `docs/17_traceability_matrix.md` | 研究計画から仕様への対応表 |
| `docs/18_implementation_blueprint.md` | 将来実装時のディレクトリ・サービス設計 |
| `docs/19_experiment_operation_runbook.md` | 実験運用手順 |
| `docs/99_sources_and_notes.md` | PPTX由来メモ、参考文献、設計判断 |

## 起動方法

### Docker Compose

先にMacホストでCodex app-serverを起動します。

```bash
codex app-server --listen ws://127.0.0.1:4500
```

その後、アプリを起動します。

```bash
docker compose up --build
```

- frontend: http://localhost:3000
- backend health: http://localhost:8000/api/health
- admin: http://localhost:3000/admin

DockerではPostgreSQLを使用します。初期seedはbackend起動時に自動投入されます。

### ローカル開発

```bash
cp .env.example .env
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

別ターミナル:

```bash
cd frontend
npm install
npm run dev
```

ローカル開発の既定DBはSQLiteです。研究本番に近い確認はDocker Composeで行ってください。

## テスト

```bash
cd backend && pytest
cd frontend && npm test
cd frontend && npm run build
```

## AIバックエンド

通常実行の既定は `AI_BACKEND=codex_app_server` です。OpenAI APIキーは使わず、ホスト側のCodex app-serverが保持するChatGPT/Codexログインを使います。

```bash
codex app-server --listen ws://127.0.0.1:4500
```

Docker Composeではbackendコンテナからホストへ接続するため、以下を使います。

```env
AI_BACKEND=codex_app_server
CODEX_APP_SERVER_URL=ws://host.docker.internal:4500
CODEX_APP_SERVER_CWD=/tmp
```

ローカルでbackendを直接起動する場合は `CODEX_APP_SERVER_URL=ws://127.0.0.1:4500` を使います。`MockAIBackend` は `AI_BACKEND=mock` を明示したテスト用途に限ります。app-serverが未起動または未ログインの場合、AI呼び出しはMockへ自動フォールバックせず、`ai_call_logs` に失敗として記録されます。

## CSV出力

管理画面または以下のAPIから出力できます。

```text
GET /api/admin/export/participants.csv
GET /api/admin/export/attempts.csv
GET /api/admin/export/learner_states.csv
GET /api/admin/export/tutor_turns.csv
GET /api/admin/export/recurrence_events.csv
GET /api/admin/export/ai_call_logs.csv
GET /api/admin/export/evaluation_summary.csv
```

出力先は `exports/` です。
