# 16. Implementation Tasks

## Milestone 1: Docs and Seed Alignment

- [x] `revised_experiment_flow_3phase_learning_session_v2.md` を学習セッション内部v2化の根拠としてdocsを更新
- [x] 5概念pretest/retestを維持
- [x] L0/transferをactive出題から外す
- [x] 事前アンケート導線を外す
- [x] v2原文との差分として、事前アンケートなし・転移テストなし・再テストは学習対象のみ・学習対象最大5を明記

## Milestone 2: Data Model

- [x] `learning_sessions`
- [x] `prerequisite_terms`
- [x] `term_understanding_attempts`
- [x] `concept_understanding_attempts`
- [x] phase1/phase2用カラム
- [x] prerequisite_terms.generation_reason
- [x] evaluation_summariesにgate指標列
- [x] evaluation_summariesにphase2補助指標列
- [x] CSV export対象追加

## Milestone 3: AI Backend

- [x] `generate_prerequisite_plan`
- [x] `generate_control_prerequisite_plan`
- [x] `grade_prerequisite_answer`
- [x] `generate_concept_phase1_material`
- [x] `grade_concept_phase1_answer`
- [x] `generate_concept_phase2_prompt`
- [x] `grade_concept_phase2_answer`
- [x] 旧互換: `generate_concept_material`, `grade_concept_answer`
- [x] 旧互換: `generate_control_learning_turn`, `grade_control_learning_answer`
- [x] MockAIBackendの決定論実装
- [x] CodexAppServerBackendのschema実装

## Milestone 4: Backend Flow

- [x] participant create/current-step
- [x] pretest/retest questions
- [x] pretest diagnosis
- [x] learning target selection
- [x] proposed/control learning session create
- [x] proposed prerequisite attempts, max 2
- [x] control small question attempts, no adaptive blocking
- [x] concept phase1 attempts
- [x] concept phase2 attempts
- [x] proposed phase2 fail -> phase1 retry
- [x] control phase1/phase2 no adaptive return
- [x] retest score -> post_survey
- [x] evaluation summary

## Milestone 5: Frontend

- [x] /start
- [x] /pretest
- [x] /diagnosing
- [x] /learning-targets
- [x] /learning/[termSlug] group split
- [x] proposed 3-stage UI
- [x] control 3-stage non-adaptive UI
- [x] /retest -> /survey/post
- [x] /survey/post
- [x] /finish
- [x] /admin

`/survey/pre`, `/l0-check`, `/transfer-test` は通常導線から外す。

## Milestone 6: Tests

- [x] backend proposed gate happy path
- [x] backend proposed gate fail limits
- [x] backend proposed phase1/phase2 retry limits
- [x] backend control small-question no-block behavior
- [x] backend control payload isolation
- [x] backend retest recurrence
- [x] frontend pretest/retest no reason/confidence
- [x] frontend proposed/control 3-stage learning split
- [x] phase2 metrics export smoke
- [x] CSV export smoke
- [x] docker compose build

## Guardrails

- OpenAI APIキー経路を作らない
- app-server失敗時にMockへ自動フォールバックしない
- 被験者画面にMラベルを出さない
- 統制群に誤概念・pretest選択肢・ログ・戻り制御情報を渡さない
- 仕様整理だけの依頼ではMarkdownのみを編集する
