# 18. Implementation Blueprint

## Backend

- FastAPI entrypoint: `backend/app/main.py`
- Experiment service: `backend/app/services/experiment.py`
- YAML loader: `backend/app/seed/content_loader.py`
- YAML seed: `backend/app/seed/content/learning_content.yml`
- DB seed: `backend/app/seed/seed_questions.py`
- AI protocol: `backend/app/ai/backend.py`
- Codex backend: `backend/app/ai/codex_app_server_backend.py`
- Mock backend: `backend/app/ai/mock_backend.py`
- Runtime taxonomy: `backend/app/ai/misconception_taxonomy.py`
- Teaching contract: `backend/app/ai/teaching_contract.py`
- RAG retriever: `backend/app/rag/retriever.py`

`init_db()` とseed処理は既存DB・既存ログを削除しない。旧Termは非アクティブ化し、新規のTerm/question queryから除外する。

## Frontend

- Main pages: `/start`, `/consent`, `/pretest`, `/diagnosing`, `/learning-targets`, `/learning/[termSlug]`, `/retest`, `/final-test`, `/survey`, `/l0-check`, `/finish`
- Test runner: `frontend/components/QuestionRunner.tsx`
- Learning page: `frontend/app/learning/[termSlug]/page.tsx`

## Experiment flow（現行）

1. 管理者から伝えられたA/B参加コードを`/start`へ入力
2. `/consent`で同意し、backendがコードを内部群へ変換して参加者作成
3. 3用語のpretest
4. 診断と学習対象選択
5. 未達用語の学習・確認問題
6. 用語ごとのretest（v1〜v4、以後v4再利用）
7. 未達があれば `current_step=learning_targets` に戻す。追加周回はクライアントまたは研究者が再開し、自動反復ループはない
8. 初回テストで学習対象がなかった場合、3用語の`final_test`（参加者向け表示は「再テスト1」）
9. `/survey`で仮アンケートを保存

再テストで3用語がすべて正解なら、`learning_targets`や`final_test`を経由せず`survey`へ進む。再テストで不正解がある場合は`learning_targets`へ戻るが、backendが次の再テスト周回を自動開始することはない。
10. `/finish`

learning確認は`enrichment` / `conceptual_change`のstage・用語ごとにv1〜v5を使う。確認問題は`questions`へseedせず、`TutorTurn.practice_question_json`に保存する。学習確認では`variant_key`を保存し、テスト問題が使う`construct_key`/`variant_key`の命名と互換性を保つ。L3/L2は内部`scaffolding_level`互換値であり、参加者向けstageではない。

### 誤概念対応教材の生成経路

1. `content_loader.py`がYAMLの`teaching_targets`を検証し、事前テストの誤答選択肢からclaim IDと訂正メタデータを復元する。
2. proposedだけに`pretest_target(s)`、learner state、誤概念履歴、taxonomy、足場掛け方略を追加する。controlは用語・共通構成要素・固定問題・共通RAGだけを受け取る。
3. Codex app-serverの`generate_tutoring_turn`出力へ`teaching_contract`を追加し、service側でclaim対応、M1/M3/unknownの方略、本文内証拠、正答漏えいを検証する。
4. 欠落時は同じbackendへ最大2回再生成する。失敗時はMockへフォールバックせず503とし、`AICallLog`へ失敗payloadを残す。
5. `TutorTurn.diagnosis_json`と`AICallLog.request_payload`に`teaching_contract`、`taxonomy_version`、`prompt_contract_version`をJSONとして保存する。既存DB列・採点ロジック・実験遷移は変更しない。

## RAG

`rag_agent_knowledge_base/` はDockerからread-onlyで参照する。`retriever.py` は `chunks.jsonl`、`embeddings_sparse.npz`、`retrieval_model.joblib` を読み、用語ごとのallowed sectionとLangGraph除外を適用する。

## AI backend

通常実行は `AI_BACKEND=codex_app_server`、モデルは `gpt-5.6-luna`、推論レベルは `medium` とする。OpenAI APIキーやOpenAI SDKの直接呼び出しは使わない。app-server未接続時はMockへフォールバックせず、失敗をAPIエラーと `ai_call_logs` に残す。管理者による手動診断修正とその監査、遅延再テスト、完全な転移評価は将来対応である。参加者削除とギブアップ監査は現行実装である。
