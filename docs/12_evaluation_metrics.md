# 12. Evaluation Metrics

## 主評価指標

### 1. 同種誤答再発率

事前テストで確認された誤概念と同じタイプの誤概念が、再テストで再び出た割合。

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

`unknown` と `ambiguous` は主指標の分母に含めない。ただし補助指標として集計する。

### 2. 足場掛けなし自力解答率

L0条件で正答できた割合。

```text
l0_correct_rate = l0_correct_count / l0_question_count
```

分母:

- l0_check phaseで出題された問題数

分子:

- `l0_success = true`
- `is_correct = true`

### 3. 足場掛けなし転移率

転移問題で、ヒントなしに正答できた割合。

```text
l0_transfer_rate = transfer_correct_count / transfer_question_count
```

分母:

- transfer phaseで出題された問題数

分子:

- `transfer_success = true`
- `is_correct = true`

## 補助指標

### 正答率

```text
score = correct_count / total_question_count
```

対象:

- pretest
- retest
- l0_check
- transfer

### 誤概念タイプ別再発率

```text
m1_recurrence_rate = m1_recurrence_count / initial_m1_count
m2_recurrence_rate = m2_recurrence_count / initial_m2_count
m3_recurrence_rate = m3_recurrence_count / initial_m3_count
m4_failure_rate = transfer_m4_failure_count / transfer_question_count
```

M4は転移失敗として主にtransfer phaseで集計する。

### Unknown継続率

```text
unknown_persistence_rate =
unknown_in_retest_count / initial_unknown_count
```

これは誤概念再発ではなく、知識不足が残った割合として扱う。

### 主観理解度変化

```text
understanding_delta = post_understanding - pre_understanding
```

用語別にも全体平均でも出せるようにする。

### 支援減少量

```text
scaffolding_reduction =
initial_scaffolding_numeric - final_scaffolding_numeric
```

数値化:

- L3 = 3
- L2 = 2
- L1 = 1
- L0 = 0

## 群別比較

MVPでは管理画面に記述統計を表示する。

- group_condition別 participant_count
- 平均pretest_score
- 平均retest_score
- 平均same_misconception_recurrence_rate
- 平均l0_correct_rate
- 平均transfer_correct_rate

小規模な卒研では統計検定より、参加者別・用語別の変化を説明できるCSVを重視する。必要なら外部分析で以下を行う。

- 比率比較
- Fisherの正確確率検定
- McNemar検定
- 用語別クロス集計

## 管理画面に表示するグラフ

- 群別 pretest vs retest 正答率
- 群別同種誤答再発率
- 群別L0正答率
- 群別転移率
- Mタイプ別出現数
- Mタイプ別再発率
- 用語別誤概念分布
- AI診断信頼度の分布

## CSV出力

### participants.csv

Columns:

- participant_id
- display_code
- group_condition
- assignment_method
- current_step
- started_at
- completed_at

### attempts.csv

Columns:

- attempt_id
- participant_id
- display_code
- group_condition
- term_slug
- term_label
- phase
- question_id
- construct_key
- variant_key
- selected_option_id
- selected_option_body
- reason_text
- free_text_answer
- response_time_sec
- is_correct
- score
- diagnosed_status
- misconception_type
- secondary_misconception_type
- misconception_confidence
- recurrence_flag
- l0_success
- transfer_success
- requires_manual_review
- created_at

### tutor_turns.csv

Columns:

- tutor_turn_id
- participant_id
- term_slug
- session_index
- turn_index
- group_condition
- scaffolding_level
- teaching_strategy
- previous_teaching_strategy
- strategy_changed
- tutor_message
- learner_response
- ai_feedback
- next_scaffolding_level
- forbidden_help_given
- created_at

### learner_states.csv

Columns:

- participant_id
- term_slug
- current_status
- primary_misconception
- secondary_misconception
- scaffolding_level
- teaching_strategy
- stable_correct_count
- recurrence_count
- l0_success_count
- transfer_success_count
- updated_at

### evaluation_summary.csv

Columns:

- participant_id
- display_code
- group_condition
- pretest_score
- retest_score
- l0_correct_rate
- transfer_correct_rate
- same_misconception_recurrence_rate
- m1_recurrence_rate
- m2_recurrence_rate
- m3_recurrence_rate
- m4_failure_rate
- unknown_persistence_rate
- learning_target_count
- completed
- created_at

## 欠損値の扱い

- 未回答は空欄で出力する
- 途中離脱参加者は `completed = false`
- 指標の分母が0の場合はnull
- AI失敗による未診断は `requires_manual_review = true`
- 管理者手動修正済みの場合はattemptsに反映し、audit_eventsにも残す

## 再計算

評価指標はDB上のattempts、learner_states、recurrence_eventsから再計算可能にする。保存済みsummaryだけに依存しない。
