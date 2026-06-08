# 16. Implementation Tasks

## Milestone 1: Docs and Seed Alignment

- [x] `revised_experiment_flow_term_concept_stages_FINAL.md` を根拠としてdocsを更新
- [x] 5概念pretest/retestを維持
- [x] L0/transferをactive出題から外す
- [x] 事前アンケート導線を外す

## Milestone 2: Data Model

- [x] `learning_sessions`
- [x] `prerequisite_terms`
- [x] `term_understanding_attempts`
- [x] `concept_understanding_attempts`
- [x] evaluation_summariesにgate指標列
- [x] CSV export対象追加

## Milestone 3: AI Backend

- [x] `generate_prerequisite_plan`
- [x] `grade_prerequisite_answer`
- [x] `generate_concept_material`
- [x] `grade_concept_answer`
- [x] `generate_control_learning_turn`
- [x] `grade_control_learning_answer`
- [x] MockAIBackendの決定論実装
- [x] CodexAppServerBackendのschema実装

## Milestone 4: Backend Flow

- [x] participant create/current-step
- [x] pretest/retest questions
- [x] pretest diagnosis
- [x] learning target selection
- [x] proposed learning session create
- [x] prerequisite attempts, max 2
- [x] concept attempts, max 4
- [x] control learning session
- [x] retest score -> post_survey
- [x] evaluation summary

## Milestone 5: Frontend

- [x] /start
- [x] /pretest
- [x] /diagnosing
- [x] /learning-targets
- [x] /learning/[termSlug] group split
- [x] proposed gate UI
- [x] control general tutor UI
- [x] /retest -> /survey/post
- [x] /survey/post
- [x] /finish
- [x] /admin

`/survey/pre`, `/l0-check`, `/transfer-test` は通常導線から外す。

## Milestone 6: Tests

- [x] backend proposed gate happy path
- [x] backend proposed gate fail limits
- [x] backend control payload isolation
- [x] backend retest recurrence
- [x] frontend pretest/retest no reason/confidence
- [x] frontend proposed/control learning split
- [x] CSV export smoke
- [x] docker compose build

## Guardrails

- OpenAI APIキー経路を作らない
- app-server失敗時にMockへ自動フォールバックしない
- 被験者画面にMラベルを出さない
- 統制群に誤概念・ログ・前提用語ゲート情報を渡さない
- 仕様整理だけの依頼ではMarkdownのみを編集する
