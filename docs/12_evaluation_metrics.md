# 12. Evaluation Metrics

## 主評価指標

### 1. 同種誤答再発率

事前テストで確認されたM1〜M3誤概念と同じタイプの誤答が、再テストで再び出た割合。

```text
same_misconception_recurrence_rate =
same_type_recurrence_count / initial_misconception_count
```

分母:

- pretestで `diagnosed_status = misconception`
- misconception_type が M1, M2, M3 のいずれか
- 学習対象になった用語

分子:

- retestで同一参加者・同一用語の misconception_type がpretestと同じ
- recurrence_flag = true

`unknown` と `ambiguous` は主指標の分母に含めない。

### 2. 再テスト正答率

```text
retest_score = retest_correct_count / retest_question_count
```

再テストは現行フローの最終テストであり、選択式のみで行う。

### 3. 前提用語通過率

提案群のみ。

```text
prerequisite_pass_rate =
passed_prerequisite_count / prerequisite_count
```

### 4. 概念理解通過率

```text
concept_pass_rate =
completed_learning_session_count / learning_target_count
```

両群で、最終的に3段階学習セッションが `completed` になった割合として扱う。

### 5. 概念フェーズ1通過率

```text
concept_phase1_pass_rate =
phase1_passed_session_count / phase1_attempted_session_count
```

### 6. 教材なし概念説明成功率

```text
concept_phase2_success_rate =
phase2_passed_session_count / phase2_attempted_session_count
```

概念フェーズ2は主評価ではないが、学習セッション内で教材なしに説明できたかを見る重要な補助指標である。

## 補助指標

### pretest_score

事前テスト正答率。

### 誤概念タイプ別再発率

```text
m1_recurrence_rate = m1_recurrence_count / initial_m1_count
m2_recurrence_rate = m2_recurrence_count / initial_m2_count
m3_recurrence_rate = m3_recurrence_count / initial_m3_count
```

### Unknown継続率

```text
unknown_persistence_rate =
unknown_in_retest_count / initial_unknown_count
```

### 主観評価

事後アンケートの使いやすさ、分かりやすさ、ヒント量の適切さを補助指標として扱う。事前アンケートと事前自信度は実施しない。

### フェーズ2再支援指標

```text
phase2_after_retry_success_rate =
phase2_failed_then_later_passed_count / phase2_once_failed_session_count
```

```text
phase2_max_retry_rate =
phase2_third_attempt_session_count / phase2_attempted_session_count
```

```text
phase2_pass_retest_correct_rate =
phase2_pass_and_retest_correct_count / phase2_pass_session_count
```

```text
phase2_fail_retest_correct_rate =
phase2_fail_and_retest_correct_count / phase2_fail_session_count
```

## 旧指標の扱い

以下は旧設計・将来拡張用の互換列として残すが、現行参加者フローでは原則nullになる。

- `l0_correct_rate`
- `transfer_correct_rate`
- `m4_failure_rate`
- `l0_success`
- `transfer_success`
- `scaffolding_reduction`

## 群別比較

管理画面に記述統計を表示する。

- group_condition別 participant_count
- 平均pretest_score
- 平均retest_score
- 平均same_misconception_recurrence_rate
- 平均prerequisite_pass_rate
- 平均concept_pass_rate
- 平均concept_phase2_success_rate

小規模な卒研では統計検定より、参加者別・用語別の変化を説明できるCSVを重視する。

## CSV出力

必須CSV:

- participants.csv
- participant_surveys.csv
- term_assignments.csv
- attempts.csv
- learner_states.csv
- learning_sessions.csv
- prerequisite_terms.csv
- term_understanding_attempts.csv
- concept_understanding_attempts.csv
- tutor_sessions.csv
- tutor_turns.csv
- recurrence_events.csv
- ai_call_logs.csv
- evaluation_summary.csv

## 欠損値の扱い

- 未回答は空欄で出力する
- 途中離脱参加者は `completed = false`
- 指標の分母が0の場合はnull
- AI失敗による未診断は `requires_manual_review = true`
- 管理者手動修正済みの場合はattemptsに反映し、audit_eventsにも残す
