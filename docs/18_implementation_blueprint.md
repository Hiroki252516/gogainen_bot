# 18. Implementation Blueprint

現行実装の構成を示す。新規実装時はこの構成を正とし、独自の別アーキテクチャへ分岐しない。

## Backend

- FastAPI entrypoint: `backend/app/main.py`
- DB初期化: `backend/app/db/session.py`
- Models: `backend/app/models/__init__.py`
- Experiment services: `backend/app/services/experiment.py`
- Seed: `backend/app/seed/data.py`, `backend/app/seed/seed_questions.py`
- AI backend protocol: `backend/app/ai/backend.py`
- Codex app-server backend: `backend/app/ai/codex_app_server_backend.py`
- Mock backend: `backend/app/ai/mock_backend.py`

`init_db()` は `create_all()` に加えてSQLite/PostgreSQLの既存DBへ不足カラムを追加する軽量スキーマ更新を行う。Alembicマイグレーションだけに依存しない。

## Frontend

- Main flow pages: `/start`, `/pretest`, `/diagnosing`, `/learning-targets`, `/learning/[termSlug]`, `/retest`, `/final-test`, `/survey`, `/finish`
- Admin page: `/admin`
- Test runner: `frontend/components/QuestionRunner.tsx`
- API helper: `frontend/lib/api.ts`

frontendはブラウザから相対パス `/api/...` を呼び、Next.js rewriteがbackendへプロキシする。Dockerではfrontendからbackendへ `INTERNAL_API_BASE_URL` を使う。

## Experiment Flow

1. 参加者作成
2. 事前テスト2問
3. 診断と学習対象選択
4. 未達用語だけ学習
5. 再テストは事前テスト対象の全問
6. 正答用語は学習対象から外し、誤答用語だけ残す
7. 未達0件で最終テスト2問
8. 採点後 `/survey`

現行seedは `llm_training_process` と `transformer` の2語である。L2概念理解問題・再テスト・最終テストは同一問題文と同一選択肢セットを使う。

## Logging

- `attempts`: テスト回答、選択肢、正誤、誤概念、出題時刻、回答時刻、回答時間、問題スナップショット
- `tutor_turns`: 学習ターン、教材、学習内回答、十分性判定、学習ステージ、出題時刻、回答時刻、回答時間
- `answer_history`: API/CSV/管理画面上の統合ビュー。物理テーブルではない
- `ai_call_logs`: Codex app-serverまたはMockのAI呼び出し記録
- `recurrence_events`: 同種誤概念再発
- `evaluation_summaries`: `pretest_score`, `retest_score`, `l0_correct_rate`, 再発率などの保存値。`l0_correct_rate` は互換名で、現行MVPでは `final_test` 正答率を入れる

CSVの回答行は `record_type=answer`、`source_type=test_attempt` または `source_type=learning_turn` とする。

事前テスト、再テスト1、再テスト2、最終テストの得点率推移と誤概念推移は、次段のログ拡張として扱う。現時点では `attempts` と `answer_history` から再計算できることを優先する。

## AI Backend

通常実行は `AI_BACKEND=codex_app_server` を使う。ホスト側で次を起動する。

```bash
codex app-server --listen ws://127.0.0.1:4500
```

OpenAI APIキーやOpenAI SDKの直接呼び出しは使わない。app-server未接続・未ログイン時はMockへ自動フォールバックせず、失敗を管理画面と `ai_call_logs` に残す。

## Verification

- backend: `./.venv/bin/python -m pytest -s tests/test_experiment_flow.py`
- frontend smoke: Windows Nodeで `frontend/tests/smoke.mjs`
- Docker: `docker compose up --build`
- Admin: `http://localhost:3000/admin`
