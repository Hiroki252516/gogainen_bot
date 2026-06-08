# 08. Backend API Spec

FastAPIでREST APIを実装する。MVPでは同期APIでよい。

## 共通ルール

- JSON request/response
- idはUUID文字列
- 作成・回答保存系APIは `Idempotency-Key` headerを受け付ける
- 被験者向けAPIは内部Mラベルを返さない
- 管理者向けAPIは内部Mラベルを返してよい
- 両群のAI payloadにはRAG教材を含める
- 提案群だけ、pretest診断、誤概念、学習履歴をAI payloadに含める

## Participants

### POST /api/participants

`group_condition` が未指定なら `control | proposed` をランダム割当する。responseの `current_step` は `pretest`。

### GET /api/participants/{id}/current-step

`pretest`, `learning_targets`, `retest`, `post_survey`, `finish` を現行導線として返す。`l0_check` と `transfer` は現行導線から外す。

## Surveys

### POST /api/participants/{id}/survey

事後アンケートだけを保存する。事前アンケートは実施しない。

## Questions

### GET /api/experiment/{participant_id}/pretest

現行5概念の事前テスト問題を返す。選択肢は参加者ごとにランダム化し、表示順を保存する。`requires_reason=false`, `requires_confidence=false`。

### GET /api/experiment/{participant_id}/retest

学習対象用語の正式再テスト問題を返す。`variant_key = retest_v1` のみactive出題する。`requires_reason=false`, `requires_confidence=false`。

### GET /api/experiment/{participant_id}/l0-check

旧互換API。現行参加者フローでは使わず、active問題は返さない。

### GET /api/experiment/{participant_id}/transfer-test

旧互換API。現行参加者フローでは使わず、active問題は返さない。

## Attempts and Diagnosis

### POST /api/attempts

テスト回答を保存する。テストフェーズでは正誤を返さない。

### POST /api/participants/{id}/diagnose-pretest

事前テスト回答を診断し、`learner_states` と `term_assignments` を作成する。`stable_correct` は学習対象外、その他は全件学習対象にする。

## Learning Targets

### GET /api/participants/{id}/learning-targets

学習対象一覧を返す。被験者向けresponseにはMラベルを含めない。

Response:

```json
{
  "targets": [
    {
      "term_slug": "attention",
      "term_label": "Attention",
      "summary_for_learner": "人間の注意ではなく、モデル内部の重み付けとして確認します。",
      "learning_mode": "proposed_gate"
    }
  ]
}
```

## Proposed Learning APIs

### POST /api/learning-sessions

対象概念の学習セッションを開始する。提案群では前提用語計画を生成し、統制群では通常チューター用セッションを作る。

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
  "learning_session_id": "uuid",
  "group_condition": "proposed",
  "status": "term_understanding",
  "term_label": "Attention"
}
```

### GET /api/learning-sessions/{session_id}

現在の学習状態を返す。提案群では前提用語一覧、現在の用語、概念教材、attempt上限を返す。統制群では通常説明ターンを返す。

### POST /api/learning-sessions/{session_id}/prerequisites/{prerequisite_id}/attempts

提案群の用語理解回答を採点する。

Request:

```json
{ "learner_answer": "..." }
```

Response:

```json
{
  "is_passed": true,
  "feedback": "...",
  "remediation_material": null,
  "next_stage": "term_understanding",
  "session_status": "term_understanding"
}
```

2回fail時は `session_status=blocked` を返す。

### POST /api/learning-sessions/{session_id}/concept-attempts

提案群の概念理解回答を採点する。

Request:

```json
{ "learner_answer": "..." }
```

Response:

```json
{
  "is_passed": false,
  "feedback": "...",
  "missing_prerequisite_ids": ["uuid"],
  "review_prerequisite_ids": ["uuid"],
  "next_stage": "term_understanding",
  "session_status": "term_understanding"
}
```

pass時は `session_status=completed` を返す。4回fail時は `session_status=failed` を返す。

## Control Learning APIs

### POST /api/learning-sessions/{session_id}/control-turn

統制群の通常AI説明と自己説明promptを返す。AI payloadにはRAG教材だけを含め、誤概念タイプや過去ログは含めない。

### POST /api/learning-sessions/{session_id}/control-answer

統制群の自己説明を保存し、一般的フィードバックを返す。

## Scoring APIs

### POST /api/participants/{id}/score-retest

再テスト回答を採点し、再発判定を保存する。完了後 `next_step=post_survey` を返す。

### POST /api/participants/{id}/score-l0-check

旧互換API。現行フローでは呼び出さない。

### POST /api/participants/{id}/score-transfer-test

旧互換API。現行フローでは呼び出さない。

## Evaluation and Admin

- POST /api/participants/{id}/evaluation-summary/recalculate
- GET /api/admin/evaluation-summary
- GET /api/admin/participants
- GET /api/admin/export/{name}.csv
- GET /api/admin/ai/status
- POST /api/admin/ai/login/start
- POST /api/admin/ai/login/cancel
- POST /api/admin/ai/logout

Allowed CSV names include:

- participants
- participant_surveys
- term_assignments
- attempts
- learner_states
- learning_sessions
- prerequisite_terms
- term_understanding_attempts
- concept_understanding_attempts
- tutor_sessions
- tutor_turns
- recurrence_events
- ai_call_logs
- evaluation_summary

## APIで返してはいけないもの

被験者向けAPIでは返さない。

- `misconception_type`
- `diagnosis_confidence`
- `recurrence_flag`
- `is_correct` in test phases
- AI raw JSON
- 統制群向け学習response内のpretest診断情報

管理者向けAPIでは返してよい。
