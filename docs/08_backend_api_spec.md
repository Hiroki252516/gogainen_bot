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
- 統制群の学習API payloadには、RAGと対象概念だけを含める

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

現行5概念の `pretest_v2` を返す。旧 `pretest_v1` は既存回答参照のため保持するがactive出題しない。選択肢は参加者ごとにランダム化し、表示順を保存する。`requires_reason=false`, `requires_confidence=false`。

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
      "learning_mode": "proposed_3phase"
    }
  ]
}
```

## Proposed Learning APIs

### POST /api/learning-sessions

対象概念の学習セッションを開始する。両群とも前提小問3件を生成し、初期statusを `prerequisite` にする。

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
  "status": "prerequisite",
  "term_label": "Attention"
}
```

### GET /api/learning-sessions/{session_id}

現在の学習状態を返す。前提小問一覧、現在の小問、概念フェーズ1教材、概念フェーズ2の軽い条件、attempt上限を返す。統制群にはpretest診断や誤概念情報を返さない。

### POST /api/learning-sessions/{session_id}/prerequisites/{prerequisite_id}/attempts

前提小問の回答を採点する。提案群はfail時に再説明して同じ小問へ戻る。統制群はfailしても次小問へ進む。

Request:

```json
{
  "learner_answer": "...",
  "attempt_kind": "normal",
  "clarification_parent_attempt_id": null
}
```

Response:

```json
{
  "is_passed": true,
  "feedback": "...",
  "supplemental_material": null,
  "next_check_question": null,
  "requires_clarification": false,
  "next_stage": "prerequisite",
  "session_status": "prerequisite"
}
```

提案群で2回fail時は `session_status=blocked` を返す。統制群では1回回答すれば次小問へ進む。

### POST /api/learning-sessions/{session_id}/concept-phase1-attempts

概念フェーズ1の教材あり説明回答を採点する。

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
  "next_stage": "prerequisite",
  "session_status": "prerequisite"
}
```

提案群ではpass時に `session_status=concept_phase2`、3回fail時に `session_status=failed_phase1` を返す。統制群ではpass/failに関係なく概念フェーズ2へ進む。

### POST /api/learning-sessions/{session_id}/concept-phase2-attempts

概念フェーズ2の教材なし・軽い条件付き説明回答を採点する。

Request:

```json
{ "learner_answer": "..." }
```

Response:

```json
{
  "is_passed": false,
  "feedback": "...",
  "return_to_phase1": true,
  "session_status": "concept_phase1"
}
```

提案群ではpass時に `completed`、fail 1〜2回目に `concept_phase1`、3回fail時に `failed_phase2` を返す。統制群ではpass/failに関係なく `completed` にする。

提案群の全回答APIでは、診断確定後に別AI呼び出しで支援を生成する。支援生成だけ失敗した場合はattemptと診断を重複作成せず、以下で再生成する。

### POST /api/learning-sessions/{session_id}/support-events/{observation_id}/retry

保存済み診断から適応支援だけを再生成する。

### POST /api/learning-sessions/{session_id}/concept-attempts

旧互換API。参加者フローでは使わない。

## Legacy Control Learning APIs

### POST /api/learning-sessions/{session_id}/control-turn

旧統制群の通常AI説明と自己説明promptを返す。現行参加者フローでは使わない。AI payloadにはRAG教材と対象概念だけを含め、誤概念タイプや過去ログは含めない。

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
- GET /api/admin/diagnoses
- POST /api/admin/diagnoses/{observation_id}/override

手動修正は完了参加者だけに許可し、元診断を変更せずoverride observationとaudit eventを追加する。

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
