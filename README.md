# 学習ログ駆動型AIチューター 開発仕様リポジトリ

このリポジトリは、卒業研究で使う「誤概念タイプと足場掛けレベルに基づく AI・情報系専門用語の概念理解支援システム」を、将来Codexに実装させるための仕様書一式です。

現時点では仕様整理だけを行い、システム実装は行いません。実装を開始するときは `prompt.md` を最初の依頼文として使い、`docs/` 以下をすべて読ませてください。

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
- まず `MockAIBackend` で研究フローを完成させる
- Codex app-server連携は後段で `CodexAppServerBackend` として差し替える
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

## Codexへの依頼

将来実装するときは、`prompt.md` をCodexの最初のプロンプトとして渡してください。実装者は必ず `docs/00_project_summary.md` から順に読み、研究条件を壊さない範囲でWebアプリを作成します。
