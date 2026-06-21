# 12. Evaluation Metrics

## Main Metrics

- `pretest_score_all_terms`: 事前テスト全5概念正答率
- `retest_score_all_terms`: 再テスト全5概念正答率
- `learning_target_retest_score`: 学習対象概念の再テスト正答率
- `non_target_retest_retention_rate`: 学習対象外概念の再テスト正答維持率
- `same_misconception_recurrence_rate`: pretestとretestで同じM1〜M3を選んだ割合
- `no_material_concept_discrimination_accuracy`: フェーズ2回答単位の正答率

## Learning Metrics

- `prerequisite_required_question_accuracy`
- `prerequisite_first_attempt_accuracy`
- `prerequisite_retry_recovery_rate`
- `prerequisite_forced_resolution_rate`
- `phase1_all_questions_pass_rate`
- `phase1_forced_resolution_rate`
- `phase2_after_retry_success_rate`
- `phase2_forced_completion_rate`

## M Transitions

前提用語Mタイプは前提用語状態だけを更新する。フェーズ1・2は対象概念状態を更新する。

- same M -> persistence
- different M -> transition
- M/unknown -> correct -> resolution
- resolved -> prior M -> recurrence
- any -> unknown -> knowledge_gap

## Removed From Current Evaluation

- independent explanation success
- free-text rubric scores
- prerequisite term usage in prose
- L0 score
- transfer score

旧列はDB互換のため残してよいが、新規選択式フローの主評価には使わない。
