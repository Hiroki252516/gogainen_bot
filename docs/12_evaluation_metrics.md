# 12. Evaluation Metrics

## 2026-06 Iterative Metrics Update

反復型フローでは、途中の再テストは全用語を対象にした形成的テストとして扱う。主な到達評価は、全用語を対象にした `final_test` の正答率と、各周回で未達項目数が減ったかで見る。正解済み用語は次周回の学習対象から除外されるため、周回ごとの負担減少も分析対象にできる。

現行MVPの `final_test` は、TransformerとLLMの学習段階の2用語すべてを対象にした選択式テストである。理由記述は要求しない。

時間分析では、問題表示時刻 `question_shown_at`、回答時刻 `answered_at`、回答時間秒 `response_time_sec` を使う。`created_at` はサーバー保存時刻として扱い、所要時間の主指標にはしない。

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

### 2. 最終テスト正答率

最終テストでヒントなし・即時フィードバックなしで正答できた割合。

```text
final_test_correct_rate = final_test_correct_count / final_test_question_count
```

分母:

- final_test phaseで出題された問題数

分子:

- `is_correct = true`

L0確認は互換・補助フェーズとして残るが、現行MVPの主到達評価は `final_test` を使う。

## 補助指標

### 正答率

```text
score = correct_count / total_question_count
```

対象:

- pretest
- retest
- final_test
- l0_check は補助・互換指標

### 誤概念タイプ別再発率

```text
m1_recurrence_rate = m1_recurrence_count / initial_m1_count
m2_recurrence_rate = m2_recurrence_count / initial_m2_count
m3_recurrence_rate = m3_recurrence_count / initial_m3_count
m4_failure_rate = m4_failure_count / evaluated_m4_context_count
```

M4は再テストや最終テストで文脈適用の失敗が明確な場合に内部集計する。

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

### 支援段階変化量

```text
scaffolding_reduction =
initial_scaffolding_numeric - final_scaffolding_numeric
```

数値化:

- L3 = 3
- L2 = 2

現行運用では `scaffolding_level` は `L3/L2` のみを使う。したがって支援段階変化量は `L3 -> L2` の1段階変化までを扱う。
## 群別比較

MVPでは管理画面に記述統計を表示する。

- group_condition別 participant_count
- 平均pretest_score
- 平均retest_score
- 平均same_misconception_recurrence_rate
- 平均confirmation_correct_rate

小規模な卒研では統計検定より、参加者別・用語別の変化を説明できるCSVを重視する。必要なら外部分析で以下を行う。

- 比率比較
- Fisherの正確確率検定
- McNemar検定
- 用語別クロス集計

## 管理画面に表示するグラフ

- 群別 pretest vs retest 正答率
- 群別同種誤答再発率
- 群別最終テスト正答率
- Mタイプ別出現数
- Mタイプ別再発率
- 用語別誤概念分布
- AI診断信頼度の分布

## 管理画面ログとCSV

現行の管理画面では、テーブル別CSVを主導線にしない。代わりに以下を使う。

- 全体ログ: 全参加者の進捗、最近の統合回答履歴、AI呼び出し、再発イベント、評価サマリーを見る
- 全体ログCSV: `overview.csv`
- 全体ログCSV Excel版: `overview_excel.csv`
- 被験者別ログ: 1人の統合回答履歴、学習状態、学習セッション詳細、AI呼び出し、再発イベントを見る
- 被験者別ログCSV: 1人分のログCSV
- 被験者別ログCSV Excel版: 1人分のUTF-8 BOM付きログCSV

ログCSVは1ファイルにまとめ、行ごとに `record_type` を持たせる。

```text
record_type, source_type, participant_id, display_code, phase, term_slug, event_time, question_shown_at, answered_at, response_time_sec, question_body, selected_option_body, question_body_snapshot, option_order_snapshot, summary, value_json
```

回答単位の行は `record_type=answer` とし、`source_type=test_attempt` または `source_type=learning_turn` で区別する。`learner_state`, `tutor_session`, `ai_call`, `recurrence`, `evaluation_summary` は補助行として同じCSVに入る。学習ターン回答は `answer` 行として統合するため、重複する `record_type=tutor_turn` 行は出さない。

## 欠損値の扱い

- 未回答は空欄で出力する
- 途中離脱参加者は `completed = false`
- 指標の分母が0の場合はnull
- AI失敗による未診断は `requires_manual_review = true`
- 管理者手動修正済みの場合はattemptsに反映し、audit_eventsにも残す

## 再計算

評価指標はDB上のattempts、learner_states、recurrence_eventsから再計算可能にする。保存済みsummaryだけに依存しない。
