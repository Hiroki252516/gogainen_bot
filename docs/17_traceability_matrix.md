# 17. Traceability Matrix

この文書は、研究計画と新設計方針が、どの仕様書・実装要素へ落ちているかを示す。

## Research Plan to Spec

| 要点 | 仕様への反映 | 実装要素 |
|---|---|---|
| 専門用語は「知っているつもり」でも誤って理解する | `00`, `03` | pretest diagnosis, misconception_type |
| AIを使うかではなく支援設計を比較する | `01`, `02` | group_condition control/proposed |
| 統制群は通常AI説明 | `04`, `08`, `10` | control learning APIs |
| 提案群は前提用語ゲート型 | `02`, `04`, `07` | learning_sessions, prerequisite_terms |
| 学習中にM再判定やL更新をしない | `04`, `10` | no dynamic scaffolding update |
| 問題をそのまま使い回さない | `11` | construct_key, variant_key |
| 再テストを最終テストにする | `02`, `09`, `12` | score-retest -> post_survey |
| ログDBとCSVで分析する | `07`, `12` | export endpoints |

## Research Questions to Data

### RQ1

事前テストの誤概念タイプに基づく提案チューターは、通常チューターより同種誤答再発率を下げるか。

必要データ:

- pretest misconception_type
- retest misconception_type
- recurrence_flag
- group_condition

主要出力:

- same_misconception_recurrence_rate
- m1/m2/m3 recurrence rate

### RQ2

前提用語理解から概念理解へ段階的に支援を減らすことで、支援なし再テストで正答できるか。

必要データ:

- prerequisite_terms
- term_understanding_attempts
- concept_understanding_attempts
- retest attempts

主要出力:

- prerequisite_pass_rate
- concept_pass_rate
- retest_score

### RQ3

AI・情報系専門用語では、どの概念・誤概念タイプが再発しやすいか。

必要データ:

- term_slug
- misconception_type
- recurrence_flag

主要出力:

- term x misconception_type count
- term x recurrence rate

## Implementation Traceability

| Research Object | DB Table | Backend Service | Frontend Page |
|---|---|---|---|
| 被験者 | participants | ExperimentService | /start |
| 問題 | questions, question_options | QuestionService | /pretest, /retest |
| 回答 | attempts | ExperimentService | test pages |
| AI診断 | attempts, ai_call_logs | DiagnosisService | /diagnosing, /admin |
| 学習対象 | term_assignments, learner_states | ExperimentService | /learning-targets |
| 提案群学習 | learning_sessions, prerequisite_terms, term_understanding_attempts, concept_understanding_attempts | LearningSessionService | /learning/[termSlug] |
| 統制群学習 | tutor_sessions, tutor_turns | LearningSessionService | /learning/[termSlug] |
| 再発 | recurrence_events | EvaluationService | /admin |
| 評価 | evaluation_summaries | EvaluationService | /admin |
| CSV | export_jobs | ExportService | /admin |

## Control vs Proposed Traceability

| Behavior | control | proposed |
|---|---|---|
| AI explanation | general RAG explanation | prerequisite-gated tutoring |
| Uses pretest log for tutoring | no | yes |
| Uses M type for tutoring | no | yes |
| Generates prerequisite terms | no | yes |
| Gates concept by prerequisite pass | no | yes |
| Stores diagnosis | yes | yes |
| Stores AI logs | yes | yes |
| Includes in evaluation | yes | yes |
