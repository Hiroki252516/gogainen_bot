# 学習ログ駆動型AIチューター 開発仕様リポジトリ

このリポジトリは、卒業研究で使う「誤概念タイプと学習ステージに基づく AI・情報系専門用語の概念理解支援システム」の仕様と実装を含みます。

`docs/` 以下に研究・設計仕様、`backend/` にFastAPIアプリ、`frontend/` にNext.jsアプリがあります。現行MVPの対象用語は、`llm_knowledge`、`multi_agent`、`memory_process` の3項目です。

## 研究の要点

研究の比較対象は「AIを使うかどうか」ではありません。比較対象は「一般的なAI解説」と「学習ログに基づいて誤概念タイプ・学習ステージ・教授方略を変えるAIチューター」です。

主評価指標は次の3つです。

1. 同種誤答再発率
2. 最終テスト正答率
3. 回答時間

現行MVPでは、最終テストは上記3項目を対象にした選択式テストです。`l0_check` は互換・補助フェーズとして残っていますが、主導線は `/final-test` です。

問題は `backend/app/seed/content/learning_content.yml` で管理します。事前・最終テストは各項目1問、再テストは4バリエーション（5回目以降はv4を再利用）、学習確認問題は5バリエーション（6回目以降はv5を再利用）です。各問題はA〜Jの10選択肢で、A〜Cが正答、D〜FがM1、G〜IがM3、Jが「わからない」です。

教材生成では、両群が `rag_agent_knowledge_base/` の共通RAG本文を参照します。提案群だけが学習ログ・誤概念分類・足場掛け情報を利用し、統制群には個人の履歴やtaxonomyを渡しません。LangGraph関連のチャンクは対象外です。

## 実装で守る前提

- OpenAI APIキーは使わない
- OpenAI SDKで通常APIを直接呼ばない
- AI呼び出しは `AIBackend` 抽象インターフェース経由にする
- 通常実行では `CodexAppServerBackend` を使い、ユーザーのChatGPT/CodexログインでAIを呼び出す
- `MockAIBackend` は自動テスト・CI・app-server切り分け専用に残す
- ChatGPT/Codex認証情報をDBへ保存しない
- 被験者画面に `M1` から `M4` の内部ラベルを直接表示しない
- 回答、出題時刻、回答時刻、回答時間、AI診断、AI応答、学習ステージ更新を研究ログとして保存する
- 管理画面とCSVでは、テスト回答と学習ターン回答を `answer_history` として同じ回答履歴に統合する
- 実験分析に必要なCSVを出力できるようにする
- 再テストは毎回、事前テスト対象の3項目すべてを出題し、採点後に次周回の学習対象だけを未達項目へ絞る

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
| `docs/04_scaffolding_and_tutoring.md` | ステージ制学習、教授方略、チャット制御 |
| `docs/05_system_architecture.md` | システム構成とモジュール境界 |
| `docs/06_codex_app_server_integration.md` | Codex app-server連携方針 |
| `docs/07_data_model.md` | DBテーブル、enum、保存ルール |
| `docs/08_backend_api_spec.md` | REST API仕様 |
| `docs/09_frontend_ux_flow.md` | 画面遷移、UI要件、禁止表示 |
| `docs/10_ai_prompt_contracts.md` | AI入出力スキーマとプロンプト契約 |
| `docs/11_seed_questions.md` | 初期問題、選択肢、L2/再テスト/最終テストの同一問題運用 |
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

先にホストOSでCodex app-serverを起動します。接続先はルート`.env`で設定します。

```bash
cp .env.example .env
./scripts/start-codex-app-server.sh
```

Windows PowerShellでは次を実行します。

```powershell
Copy-Item .env.example .env
.\scripts\start-codex-app-server.ps1
```

その後、アプリを起動します。

```bash
docker compose up --build
```

- frontend: http://localhost:3000
- backend health: http://localhost:8000/api/health
- admin: http://localhost:3000/admin

DockerではPostgreSQLを使用します。backendからCodex app-serverへの接続先は`.env`の`CODEX_APP_SERVER_URL`で変更できます。Docker Desktopでは通常`ws://host.docker.internal:4500`を使います。`rag_agent_knowledge_base/` はread-onlyでbackendへマウントされ、初期seedはYAMLを検証したうえでbackend起動時に自動投入されます。

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
./scripts/start-codex-app-server.sh
```

Docker Composeではbackendコンテナからホストへ接続するため、`.env`に以下を設定します。

```env
AI_BACKEND=codex_app_server
CODEX_APP_SERVER_URL=ws://host.docker.internal:4500
CODEX_APP_SERVER_LISTEN_URL=ws://127.0.0.1:4500
CODEX_APP_SERVER_CWD=/tmp
CODEX_MODEL=gpt-5.6-luna
CODEX_REASONING_EFFORT=medium
RAG_BASE_DIR=/rag_agent_knowledge_base
```

ローカルでbackendを直接起動する場合は、backendが動くホストから到達できるURLへ`CODEX_APP_SERVER_URL`を変更します。通常は`ws://127.0.0.1:4500`です。`MockAIBackend` は `AI_BACKEND=mock` を明示したテスト用途に限ります。app-serverが未起動または未ログインの場合、AI呼び出しはMockへ自動フォールバックせず、`ai_call_logs` に失敗として記録されます。

## トラブルシューティング

- frontendからbackendへ接続できない場合は、`.env`の`FRONTEND_INTERNAL_API_BASE_URL`を確認します。Docker Desktopでは通常`http://host.docker.internal:8000`です。
- `/api/admin/ai/status` が未接続なら、`.env`の`CODEX_APP_SERVER_URL`と`CODEX_APP_SERVER_LISTEN_URL`を確認し、`scripts/start-codex-app-server.sh`または`.ps1`でapp-serverを起動します。WindowsでDockerからホストへ到達できない場合は、`CODEX_APP_SERVER_LISTEN_URL`を環境に合わせて変更し、ファイアウォールで4500番ポートを許可してください。
- AI呼び出しが `usageLimitExceeded` で503になる場合は、ChatGPT/Codexアカウントの利用枠が回復してから再実行します。通常実行ではMockへ自動切替しません。

## 管理画面ログとCSV

管理画面では、ログを全体ログと被験者別ログに分けて確認できます。

```text
GET /api/admin/logs/overview
GET /api/admin/logs/overview.csv
GET /api/admin/participants/{participant_id}/logs
GET /api/admin/participants/{participant_id}/logs.csv
```

CSVは `record_type, source_type, participant_id, display_code, phase, term_slug, event_time, question_shown_at, answered_at, response_time_sec, question_body, selected_option_body, question_body_snapshot, option_order_snapshot, summary, value_json` の形式で、回答履歴・学習状態・学習セッション・AIログなどを1ファイルにまとめます。回答単位の行は `record_type=answer`、`source_type=test_attempt` または `source_type=learning_turn` です。出力先は `exports/` です。

現行の評価サマリーは `pretest_score`, `retest_score`, `l0_correct_rate`, 同種誤答再発率、Mタイプ別再発率を中心に保存します。`l0_correct_rate` は互換名で、`final_test` がある場合は最終テスト正答率として扱います。次段の追加仕様では、事前テスト、再テスト1、再テスト2、最終テストの得点率推移、差分ポイント、誤概念推移、未達項目数推移をログ化します。
