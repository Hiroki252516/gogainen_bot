# 18. Implementation Blueprint

## Backend

- FastAPI entrypoint: `backend/app/main.py`
- Experiment service: `backend/app/services/experiment.py`
- YAML loader: `backend/app/seed/content_loader.py`
- YAML test / learning v1 bank: `backend/app/seed/content/learning_content.yml`
- YAML new learning v2 bank: `backend/app/seed/content/learning_questions_v2.yml`
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

新規参加者には作成時に`participants.learning_content_version=2`を固定し、場面判断型v2を使う。既存参加者および列追加でNULLの既存行はv1のまま進行する。実際に提示した版は各`TutorTurn.diagnosis_json.learning_content_version`へ保存し、回答時もその版を使う。学習確認v2は3用語×2 stage×5場面種類（適用・予測・比較・境界判断・事例診断）の30 variantで、正解/M1/M3を3つずつ配置する。A〜Iの役割を版全体で均等化し、Jは「わからない」。テスト系問題は変更しない。

### 誤概念対応教材の生成経路

1. `content_loader.py`がYAMLの`teaching_targets`を検証し、事前テストの誤答選択肢からclaim IDと訂正メタデータを復元する。
2. 両群に用語・共通構成要素・同一検索条件のRAGを渡す。固定問題、選択肢、正答、参加者ID、群名は教材生成モデルへ渡さない。controlは一般的な通常AIチューターとして説明し、診断・学習段階・履歴・回答を参照しない。proposedだけに`pretest_target(s)`、learner state、誤概念履歴、taxonomy、足場掛け方略を追加する。
3. Codex app-serverの`generate_tutoring_turn`出力では、proposedの`teaching_contract`と`mandatory_elements`をservice側で検証し、claim対応、M1/M3/unknownの方略、本文内証拠、正答漏えいを確認する。両群の教材本文は450〜850字程度を目安とし、文字数・段落数・箇条書き数を記録するが、長さだけを理由に再生成しない。
4. 契約・安全性の欠落時は同じbackendへ最大2回再生成する。各AIログへ生成試行番号と検証結果を記録し、失敗時はMockへフォールバックせず503とする。
5. `TutorTurn.diagnosis_json`には最終契約・検証・出力長指標を、`AICallLog.request_payload.effective_request`にはCodexへ実送信した`thread/start`・`turn/start`設定と全文prompt/schema、モデル・推論レベル、prompt/taxonomy版、RAG照合情報、送信状態を保存する。認証情報は保存しない。既存DB列・CSV固定列・採点ロジック・実験遷移は変更しない。

統制群の正答要約・誤答解説も同じallowlist projectionを通し、現在の問題、選択内容、表示済み教材、共通RAGだけを残す。学習段階・診断・履歴・識別子は入力しない。前の確認問題の解説を次の教材生成へ持ち越さない。

### 学習回答後の先行生成

`TutorTurn`の回答確定処理は固定採点の結果から次ターン用の不変な生成計画を作る。計画は現在のDBオブジェクトを先に変更せず、次段階、回答、履歴の投影、固定問題の次variant、群別payloadを保持する。これを使って次教材AIを別タスクで開始し、解説AIと並行させる。

`backend/app/services/tutor_prefetch.py`のプロセス内レジストリはセッションごとに1つの先行生成を管理する。先行生成タスクはAI応答を得ても回答リクエストの成功通知までは保存ゲートで待機し、成功後にだけ別DBセッションから未回答`TutorTurn`を保存する。回答失敗、ギブアップ、タスクキャンセル時は結果を破棄する。次ターンAPIはレジストリの完了を待ち、保存済みターンを通常の生成サービスが再利用する。

## RAG

`rag_agent_knowledge_base/` はDockerからread-onlyで参照する。`retriever.py` は `chunks.jsonl`、`embeddings_sparse.npz`、`retrieval_model.joblib` を読み、用語ごとのallowed sectionとLangGraph除外を適用する。

## AI backend

通常実行は `AI_BACKEND=codex_app_server`、モデルは `gpt-5.6-luna`、推論レベルは `medium` とする。OpenAI APIキーやOpenAI SDKの直接呼び出しは使わない。app-server未接続時はMockへフォールバックせず、失敗をAPIエラーと `ai_call_logs` に残す。管理者による手動診断修正とその監査、遅延再テスト、完全な転移評価は将来対応である。参加者削除とギブアップ監査は現行実装である。

実験運用では、参加者ログの`ai_call_logs.request_payload.effective_request`を使い、Codexへ渡った実prompt/schemaと統制群の入力分離を確認する。全文promptには回答・履歴等が含まれ得るため、この監査ログは研究者だけが閲覧する。Mockの自動テストにはCodex実送信監査を付けない。
