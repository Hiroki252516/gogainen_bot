# 08. Backend API Spec

## 2026-06 Iterative Flow API Update

反復型フローでは、`GET /api/experiment/{participant_id}/retest` は現在 `TermAssignment.is_learning_target = true` の未達用語だけを返す。`POST /api/participants/{participant_id}/score-retest` は正解済み用語を次周回対象から除外し、未達が残れば `next_url=/learning-targets`、残り0件なら `next_url=/final-test` を返す。

`GET /api/experiment/{participant_id}/final-test` と `POST /api/participants/{participant_id}/score-final-test` を追加する。最終テストは途中で除外された用語も含め、5用語すべてを出題する。採点後は `next_url=/survey` を返す。


## 2026-06 Learning-Session Misconception API Update

学習セッション内の誤概念判定は、事前テスト由来の `misconception_type` とは別に扱う。`POST /api/tutor-sessions/{session_id}/turns` は以下を追加で返す。

- `initial_misconception_type`: 事前テスト由来の誤概念タイプ
- `latest_learning_misconception_type`: 同一学習セッション内の直近回答に対する誤概念タイプ
- `latest_learning_misconception_reason`: 直近の学習内判定理由
- `session_misconception_history`: 構成用語または概念理解ごとの学習内判定履歴

`POST /api/tutor-turns/{turn_id}/respond` は以下を追加で返す。

- `learning_misconception_type`
- `learning_misconception_confidence`
- `learning_misconception_reason`

保存先は `tutor_turns.grading_json` とする。既存DBカラムは追加しない。


## 2026-06 Stage-Based Learning API Update

`POST /api/tutor-sessions/{session_id}/turns` は、既存フィールドに加えて以下を返す。

- `learning_stage`: `term_understanding` または `concept_understanding`
- `learning_stage_label`: 被験者向け段階名
- `component_term`: 用語理解段階で確認中の構成用語
- `component_index`: 0始まりの構成用語インデックス
- `component_total`: 構成用語数
- `stage_completed`: 生成直後は `false`

`POST /api/tutor-turns/{turn_id}/respond` は、既存フィールドに加えて以下を返す。

- `learning_stage`
- `stage_completed`
- `next_learning_stage`
- `component_term`
- `component_index`
- `component_total`
- `next_component_index`

`session_completed` は、`concept_understanding` の回答が十分だった場合だけ `true` になる。用語理解段階で `is_sufficient = true` になっても、次の構成用語または概念理解段階へ進むだけでセッションは終了しない。


FastAPIでREST APIを実装する。実験中のAI応答ストリーミングが必要な場合のみSSEを使う。MVPでは同期APIでよい。

## 共通ルール

- JSON request/response
- idはUUID文字列
- 作成・回答保存系APIは `Idempotency-Key` headerを受け付ける
- エラーは `error_code`, `message`, `details` を返す
- 被験者向けAPIは内部Mラベルを返さない
- 管理者向けAPIは内部Mラベルを返してよい

## Health

### GET /api/health

```json
{ "status": "ok" }
```

## Participants

### POST /api/participants

Request:

```json
{
  "group_condition": "proposed",
  "assignment_method": "manual",
  "consent_checked": true
}
```

`group_condition` が未指定ならランダム割当する。

Response:

```json
{
  "participant_id": "uuid",
  "display_code": "P001",
  "group_condition": "proposed",
  "current_step": "pretest"
}
```

### GET /api/participants/{id}/current-step

```json
{
  "step": "pretest",
  "next_url": "/pretest",
  "completed_steps": ["start"]
}
```

## Questions

### GET /api/experiment/{participant_id}/pretest

事前テスト問題を返す。選択肢は参加者ごとにランダム化し、表示順をDBに保存する。

Response:

```json
{
  "phase": "pretest",
  "questions": [
    {
      "question_id": "uuid",
      "term_slug": "attention",
      "term_label": "Attention",
      "body": "TransformerにおけるAttentionの説明として、最も適切なものはどれか。",
      "options": [
        { "option_id": "uuid", "label": "A", "body": "..." }
      ],
      "requires_reason": false
    }
  ]
}
```

内部の `misconception_type` は返さない。

### GET /api/experiment/{participant_id}/retest

学習対象用語の再テスト問題を返す。同じ `construct_key` の別 `variant_key` を選ぶ。

### GET /api/experiment/{participant_id}/l0-check

確認テスト問題を返す。チャットやヒント表示はfrontendで無効化する。

## Attempts

### POST /api/attempts

回答を保存する。

Request:

```json
{
  "participant_id": "uuid",
  "question_id": "uuid",
  "phase": "pretest",
  "selected_option_id": "uuid",
  "free_text_answer": null,
  "reason_text": null,
  "response_time_sec": 18.3
}
```

Response:

```json
{
  "attempt_id": "uuid",
  "saved": true,
  "is_complete_for_question": true
}
```

テストフェーズでは正誤を返さない。

## Diagnosis

### POST /api/participants/{id}/diagnose-pretest

AI診断を実行し、learner_statesを初期化する。

Response:

```json
{
  "status": "completed",
  "learning_target_count": 4,
  "next_step": "learning_targets"
}
```

被験者向けresponseにはMラベルを含めない。管理者向けログには含める。

## Learning Targets

### GET /api/participants/{id}/learning-targets

Response:

```json
{
  "targets": [
    {
      "term_slug": "attention",
      "term_label": "Attention",
      "summary_for_learner": "人間の注意ではなく、モデル内部の重み付けとして確認します。",
      "current_scaffolding_level_for_display": "しっかり確認"
    }
  ]
}
```

`current_scaffolding_level_for_display` は互換表示用に残す。学習セッション画面の進行表示は `learning_stage` と構成用語進捗を正とする。

## Tutor Sessions

### POST /api/tutor-sessions

Request:

```json
{
  "participant_id": "uuid",
  "term_slug": "attention"
}
```

Response:

```json
{
  "tutor_session_id": "uuid",
  "session_index": 1,
  "max_turns": 3
}
```

### POST /api/tutor-sessions/{session_id}/turns

チューター発話を生成する。

Request:

```json
{
  "requested_action": "start_or_continue"
}
```

Response:

```json
{
  "turn_id": "uuid",
  "tutor_message": "...",
  "learner_prompt": "...",
  "practice_question": {
    "body": "...",
    "requires_response": true
  },
  "requires_learner_response": true,
  "turn_index": 1,
  "max_turns": 3,
  "learning_stage": "term_understanding",
  "learning_stage_label": "用語理解",
  "component_term": "Attention",
  "component_index": 0,
  "component_total": 3,
  "stage_completed": false,
  "misconception_type": "M1",
  "scaffolding_level": "L3",
  "teaching_strategy": "category_reorientation"
}
```

学習セッションではデバッグ用に `misconception_type`, `learning_stage`, `teaching_strategy` を通常レスポンスへ含める。`scaffolding_level` は互換ログ用に返すが、被験者画面の進行表示や教材説明量の制御には使わない。教材本文やAIフィードバック本文には内部Mラベルを混ぜない。

### POST /api/tutor-turns/{turn_id}/respond

学習者回答を保存し、AIフィードバック、回答十分性、backend決定後の次レベルを返す。

Request:

```json
{
  "learner_response": "未知データで性能が下がることが重要だと思います。"
}
```

Response:

```json
{
  "feedback": "...",
  "next_action": "continue",
  "is_sufficient": false,
  "session_completed": false,
  "learning_stage": "term_understanding",
  "stage_completed": false,
  "next_learning_stage": "term_understanding",
  "component_term": "Attention",
  "component_index": 0,
  "component_total": 3,
  "next_component_index": 1,
  "next_scaffolding_level": "L2",
  "turn_index": 1,
  "max_turns": 3
}
```

`feedback` はログ保存、次ステージ教材への統合、セッション完了時の教材フィードバック画面に使う。ターン継続時は回答直後に単独表示しない。セッション完了時は問題を出さず、`feedback` と次へボタンだけを表示する。`next_learning_stage` と `next_component_index` はbackendの決定論的更新結果であり、画面進行に使う。`next_scaffolding_level` は互換ログ用に返す。

## Scoring APIs

### POST /api/participants/{id}/score-retest

再テスト回答を採点し、再発判定とlearner_states更新を行う。

### POST /api/participants/{id}/score-l0-check

確認テスト回答を採点し、`l0_success` を保存する。

各API response:

```json
{
  "status": "completed",
  "next_step": "finish"
}
```

テストフェーズ中は個別の正誤を被験者に返さない。

## Evaluation

### POST /api/participants/{id}/evaluation-summary/recalculate

参加者単位で評価指標を再計算する。

### GET /api/admin/evaluation-summary

管理画面用に群別集計を返す。

```json
{
  "groups": [
    {
      "group_condition": "proposed",
      "participant_count": 10,
      "same_misconception_recurrence_rate": 0.22,
      "l0_correct_rate": 0.71,
    }
  ]
}
```

## Admin

- GET /api/admin/participants
- GET /api/admin/participants/{id}
- GET /api/admin/participants/{id}/logs
- GET /api/admin/participants/{id}/learner-states
- PATCH /api/admin/attempts/{attempt_id}/diagnosis
- DELETE /api/admin/participants/{id}
- DELETE /api/admin/experiment-data

手動修正APIは `audit_events` に必ず保存する。

## CSV Export

### GET /api/admin/export/{name}.csv

Allowed CSV names:

- participants
- term_assignments
- questions
- attempts
- learner_states
- tutor_sessions
- tutor_turns
- recurrence_events
- ai_call_logs
- evaluation_summary

## Codex app-server

### GET /api/admin/ai/status

```json
{
  "ai_backend": "codex_app_server",
  "app_server_reachable": true,
  "logged_in": true,
  "account_label": "ChatGPT",
  "last_error": null
}
```

### POST /api/admin/ai/login/start

```json
{
  "flow": "chatgptDeviceCode"
}
```

Response:

```json
{
  "login_id": "...",
  "verification_url": "https://...",
  "user_code": "ABCD-EFGH"
}
```

### POST /api/admin/ai/login/cancel

### POST /api/admin/ai/logout

## Error Response

```json
{
  "error_code": "schema_validation_failed",
  "message": "AI出力を検証できませんでした。",
  "details": {
    "ai_call_log_id": "uuid"
  }
}
```

## APIで返してはいけないもの

被験者向けAPIでは返さない。

- `misconception_type`
- `diagnosis_confidence`
- `teaching_strategy`
- `scaffolding_level`
- `recurrence_flag`
- `is_correct` in test phases
- AI raw JSON

管理者向けAPIでは返してよい。

## RAG教材参照

学習ターン生成と学習回答フィードバックでは、`rag_ready_教材` のローカルTF-IDF検索結果を `rag_context` としてAIBackend payloadへ渡す。OpenAI APIキーや外部vector storeは通常実行に使わない。RAG資産が見つからない場合は空のcontextとして扱い、実験フローを停止しない。