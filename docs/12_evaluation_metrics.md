# 12. Evaluation Metrics

## 主評価指標

### 1. 同種誤答再発率

事前テストで確認された誤概念と同じタイプの誤概念が、再テストで再び出た割合。

```text
same_misconception_recurrence_rate =
same_type_recurrence_count / initial_misconception_count
```

### 2. 足場掛けなし自力解答率

L0条件で正答できた割合。

```text
l0_correct_rate = l0_correct_count / l0_question_count
```

### 3. 足場掛けなし転移率

転移問題で、ヒントなしに正答できた割合。

```text
l0_transfer_rate = transfer_correct_count / transfer_question_count
```

## 補助指標

### 正答率

```text
score = correct_count / total_question_count
```

対象:

- pretest
- retest
- transfer

### 誤概念タイプ別再発率

```text
m1_recurrence_rate = m1_recurrence_count / initial_m1_count
m2_recurrence_rate = m2_recurrence_count / initial_m2_count
m3_recurrence_rate = m3_recurrence_count / initial_m3_count
m4_failure_rate = transfer_failure_count / transfer_question_count
```

### 自信度変化

```text
confidence_delta = post_confidence - pre_confidence
```

## 管理画面に表示するグラフ

- 群別 pretest vs retest 正答率
- 群別同種誤答再発率
- 群別L0正答率
- 群別転移率
- Mタイプ別出現数
- Mタイプ別再発率

## CSV出力

### evaluation_summary.csv

Columns:

- participant_id
- group_condition
- pretest_score
- retest_score
- transfer_score
- same_misconception_recurrence_rate
- l0_correct_rate
- l0_transfer_rate
- m1_recurrence_rate
- m2_recurrence_rate
- m3_recurrence_rate
- m4_failure_rate
