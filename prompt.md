# Codex実装依頼プロンプト

あなたはこのリポジトリの実装担当です。`docs/` 以下の仕様書をすべて読み、研究条件を壊さないように「学習ログ駆動型AIチューター」を本格実装してください。

## 最重要ゴール

AI・情報系専門用語の概念理解支援を目的とした、誤概念タイプと学習ステージに基づく学習ログ駆動型AIチューターを、Docker環境で動くWebアプリとして実装してください。

研究上の比較は「AIあり/なし」ではありません。統制群は一般的なAI解説を受ける通常AIチューター、提案群は過去ログ、誤概念タイプ、学習ステージを使って支援を変えるAIチューターです。

## 実装対象環境

- ユーザー環境: MacBook Air M4
- 実行方式: Docker / Docker Compose
- frontend: Next.js + TypeScript
- backend: FastAPI + Python
- db: PostgreSQL
- AI backend: OpenAI APIキーは使わない
- AI backendは Codex app-server 経由で接続する
- `MockAIBackend` は自動テスト・障害切り分け専用に残す

## 必ず守ること

1. OpenAI APIキーを要求しない
2. OpenAI SDKで通常APIを直接呼ばない
3. AI呼び出しは必ず `AIBackend` インターフェース経由にする
4. 通常実行では `CodexAppServerBackend` を使い、ユーザーのChatGPT/Codexログイン済みapp-serverへ接続する
5. `MockAIBackend` は `AI_BACKEND=mock` を明示した自動テスト・障害切り分け用途だけで使う
6. ChatGPT/Codex認証情報をDBに保存しない
7. M1〜M4の内部ラベルを被験者画面に直接出さない
8. 研究ログとして、回答、出題時刻、回答時刻、回答時間、AI診断、AI応答、学習ステージ更新を保存する
9. CSVエクスポートを実装する
10. Docker Composeで一発起動できるようにする
11. 現行MVP対象用語は `llm_knowledge`（LLMに知識を与える方法）、`multi_agent`（マルチエージェント）、`memory_process`（記憶プロセス）の3項目とする
12. 事前テスト・再テスト・最終テスト・学習セッション確認問題は `backend/app/seed/content/learning_content.yml` で管理し、問題文と選択肢セットをYAMLから読み込む
13. 再テスト、最終テスト、L0確認ではチャット、ヒント、即時正解表示を禁止する
14. 再テストは各項目4バリエーションを使い、5回目以降は4問目を再利用する。学習確認問題は各学習段階・各項目5バリエーションを使い、6回目以降は5問目を再利用する
15. `l0_check` は互換・補助フェーズとして扱い、現行MVPの主導線は `/final-test` とする
16. RAGは `rag_agent_knowledge_base/` の用語別対象セクションだけを参照し、LangGraphを含むチャンクを検索結果から除外する
17. 両群に同じRAG本文を渡す。提案群だけに学習ログ、誤概念分類、足場掛け情報、過去応答を渡し、統制群には渡さない
18. Codex app-serverの設定は `CODEX_MODEL=gpt-5.6-luna`、`CODEX_REASONING_EFFORT=medium` に統一する

## Frontend

必須ページ:

- `/start`
- `/pretest`
- `/diagnosing`
- `/learning-targets`
- `/learning/[termSlug]`
- `/retest`
- `/final-test`
- `/survey`
- `/l0-check`  # 互換・補助
- `/finish`
- `/admin`

UIは研究実験用であり、派手さよりも誤操作防止、ログ完全性、被験者への条件統制を優先してください。

## Backend

必須API:

- participants API
- terms/questions API
- attempts API
- diagnosis API
- learner state API
- tutor session API
- retest API
- final test API
- evaluation summary API
- CSV export API
- Codex app-server status/login API

詳細は `docs/08_backend_api_spec.md` に従ってください。

## Database

`docs/07_data_model.md` に従って実装してください。特に以下は必須です。

- participant
- terms
- questions
- question_options
- attempts
- learner_states
- tutor_sessions
- tutor_turns
- recurrence_events
- ai_call_logs
- evaluation_summaries
- export_jobs
- audit_events

問題バリアントの識別は `questions.construct_key` と `questions.variant_key` で扱う。現行実装では `question_variants` を独立テーブルとして必須にしない。

## AI

`docs/10_ai_prompt_contracts.md` に従ってください。

AI機能は以下に分けてください。

- `diagnose_answer`
- `generate_tutoring_turn`
- `grade_response`
- `generate_feedback`
- `summarize_learner_state`

AI出力は必ず構造化JSONとして検証し、失敗時は再試行または保留状態として保存してください。

教材生成時は、両群で対象項目・学習段階・構成要素・共通RAG本文を使う。提案群では最新のM1〜M4/unknown taxonomyと学習者履歴を教授方略へ反映し、統制群では一般的な説明に限定する。taxonomyの定義はM1=誤信念、M2=欠陥メンタルモデル、M3=カテゴリー誤り、M4=欠如したスキーマであり、被験者画面には表示しない。

## Codex app-server

Codex app-server連携は `docs/06_codex_app_server_integration.md` に従ってください。

MVPでは以下を優先してください。

- Macホスト上で `codex app-server --listen ws://127.0.0.1:4500` を起動
- Docker Desktop for Mac上のbackendから `ws://host.docker.internal:4500` に接続
- WebSocket auth tokenが設定されている場合はそれもサポート
- app-server接続に失敗した通常実行はMockへ自動フォールバックせず、`ai_call_logs` に失敗を保存して管理画面に表示する

## 実装順序

1. プロジェクト雛形作成
2. Docker Compose構成
3. DB models + migrations
4. seed data
5. backend API
6. frontend flow
7. Codex app-server client
8. 評価指標とCSV export
9. MockAIBackendによる自動テスト
10. テスト
11. README整備

## 完了条件

- `docker compose up --build` で起動できる
- frontendが `http://localhost:3000` で開ける
- backendが `http://localhost:8000/api/health` で応答する
- `AI_BACKEND=codex_app_server` で、事前テスト、診断、学習、再テスト、最終テスト、CSV出力まで動く
- `AI_BACKEND=mock` は自動テストで同じ研究フローを検証できる
- proposed群では、M1〜M4に応じて教授方略が変わる
- 事前テスト、再テスト、最終テスト、学習確認問題がYAMLから読み込まれ、A〜C正答、D〜F=M1、G〜I=M3、J=unknownの判定規則が検証される
- proposed群では、正答でLが下がり、誤答でLが維持または上がる
- 同じ誤概念が再発した場合 `recurrence_flag = true` になる
- 未達0件になったら、3項目すべてを対象にした選択式・理由なしの `/final-test` へ進み、採点後 `/survey` へ進む
- 管理画面とCSVでは、テスト回答と学習ターン回答を `answer_history` として同じ回答履歴に統合する
- 評価サマリーは `pretest_score`, `retest_score`, `l0_correct_rate`, 同種誤答再発率を保存し、`l0_correct_rate` はfinal_test正答率の互換名として扱う
- 次段の評価ログ拡張では、事前テスト、再テスト1、再テスト2、最終テストの得点率推移、差分ポイント、誤概念推移、未達項目数推移を管理画面とCSVで確認できるようにする
- control群では一般解説のみになる
- app-server未接続時は分かりやすいエラーが出る
- READMEにセットアップ手順が書かれている

## 判断に迷った場合

以下を優先してください。

1. 実験ログが残ること
2. Codex app-server経由で実AI応答を使うこと
3. 再現性があること
4. MockAIBackendはテスト用途に閉じること
5. UIの豪華さより研究フローの正確さ
