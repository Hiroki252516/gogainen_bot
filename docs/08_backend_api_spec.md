# 08. Backend API Spec

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

L0確認問題を返す。チャットやヒント表示はfrontendで無効化する。

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

`current_scaffolding_level_for_display` は内部L0〜L3を直接出さず、自然言語化する。

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
  "requires_learner_response": true
}
```

被験者向けresponseには内部Mラベルを含めない。

### POST /api/tutor-turns/{turn_id}/respond

学習者回答を保存し、AIフィードバックと次レベルを返す。

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
  "next_action": "move_next",
  "session_completed": false
}
```

## Scoring APIs

### POST /api/participants/{id}/score-retest

再テスト回答を採点し、再発判定とlearner_states更新を行う。

### POST /api/participants/{id}/score-l0-check

L0確認回答を採点し、`l0_success` を保存する。

### POST /api/participants/{id}/score-transfer-test

転移回答を採点し、M4判定と `transfer_success` を保存する。

各API response:

```json
{
  "status": "completed",
  "next_step": "transfer_test"
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
