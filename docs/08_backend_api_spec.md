# 08. Backend API Spec

FastAPIでREST APIを実装する。実験中のAI応答ストリーミングが必要な場合のみSSEを使う。

## Health

### GET /api/health

```json
{ "status": "ok" }
```

## Participants

### POST /api/participants

Request:

```json
{ "group_condition": "proposed" }
```

Response:

```json
{
  "participant_id": "uuid",
  "display_code": "P001",
  "group_condition": "proposed"
}
```

### POST /api/participants/{id}/survey

事前アンケート保存。

## Experiment Flow

### GET /api/participants/{id}/current-step

```json
{
  "step": "pretest",
  "next_url": "/experiment/pretest"
}
```

## Questions

### GET /api/experiment/{participant_id}/pretest

事前テスト問題を返す。

### POST /api/attempts

回答を保存する。

Request:

```json
{
  "participant_id": "uuid",
  "question_id": "uuid",
  "selected_option_id": "uuid",
  "reason_text": "string",
  "confidence": 3,
  "response_time_sec": 18.3
}
```

## Diagnosis

### POST /api/participants/{id}/diagnose-pretest

AI診断を実行し、learner_statesを初期化する。

## Learning Session

### GET /api/participants/{id}/learning-targets

学習対象用語を返す。

### POST /api/tutor-sessions

学習セッションを作成する。

### POST /api/tutor-sessions/{session_id}/turns

チューター発話を生成する。

### POST /api/tutor-turns/{turn_id}/respond

学習者回答を保存し、AIフィードバックと次レベルを返す。

## Retest / L0 / Transfer

- GET /api/participants/{id}/retest
- POST /api/participants/{id}/score-retest
- GET /api/participants/{id}/l0-check
- POST /api/participants/{id}/score-l0-check
- GET /api/participants/{id}/transfer-test
- POST /api/participants/{id}/score-transfer-test

## Admin

- GET /api/admin/participants
- GET /api/admin/participants/{id}/logs
- GET /api/admin/evaluation-summary
- GET /api/admin/export/{name}.csv

Allowed CSV names:

- participants
- attempts
- learner_states
- tutor_turns
- recurrence_events
- evaluation_summary

## Codex app-server

- GET /api/admin/ai/status
- POST /api/admin/ai/login/start
- POST /api/admin/ai/login/cancel
- POST /api/admin/ai/logout
