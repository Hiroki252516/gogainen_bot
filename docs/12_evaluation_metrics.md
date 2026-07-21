# 12. Evaluation Metrics

## 2026-06 Iterative Metrics Update

反復型フローでは、途中の再テストは全用語を対象にした形成的テストとして扱う。主な到達評価は、全用語を対象にした `final_test` の正答率と、各周回で未達項目数が減ったかで見る。正解済み用語は次周回の学習対象から除外されるため、周回ごとの負担減少も分析対象にできる。

現行MVPの `final_test` は、Transformer 1用語を対象にした10択・3つ選択式テストである。理由記述は要求しない。

時間分析では、問題表示時刻 `question_shown_at`、回答時刻 `answered_at`、回答時間秒 `response_time_sec` を使う。`created_at` はサーバー保存時刻として扱い、所要時間の主指標にはしない。

現行実装の `evaluation_summaries` は、参加者単位の `pretest_score`, `retest_score`, `l0_correct_rate`, 同種誤答再発率、Mタイプ別再発率を保存する。`l0_correct_rate` は互換名だが、`final_test` が存在する場合は `final_test` の正答率を入れる。事前テスト、再テスト1、再テスト2、最終テストの得点率推移と誤概念推移は、次段のログ拡張で追加する。

## 次段追加: 得点率推移・誤概念推移ログ

次段の評価ログ拡張では、事前テストから最終テストまでを時系列で追えるようにする。再テスト回数は固定せず、参加者ごとに `retest_1`, `retest_2`, ... と周回順で扱う。

保存・出力する主な値:

- phase別得点率: `pretest_score_rate`, `retest_1_score_rate`, `retest_2_score_rate`, `final_test_score_rate`
- 事前比得点増加量: `score_delta_from_pretest_pt`
- 直前テスト比増加量: `score_delta_from_previous_test_pt`
- 未達項目数推移: `remaining_learning_target_count_by_round`
- 誤概念タイプ推移: `pretest -> retest_n -> final_test`

得点増加量は相対率ではなく、差分ポイントで定義する。

```text
score_delta_from_pretest_pt =
(current_score_rate - pretest_score_rate) * 100

score_delta_from_previous_test_pt =
(current_score_rate - previous_test_score_rate) * 100
```

例: 事前テスト50%、最終テスト100%の場合、`score_delta_from_pretest_pt = +50pt` とする。pretestが0%でも差分ポイントは計算できるため、相対増加率のようなゼロ除算を避けられる。

誤概念変化は用語ごとに以下へ分類する。

| change_type | 意味 |
|---|---|
| `resolved` | 誤概念またはunknownから正答へ変化 |
| `same_type_recurred` | 同じMタイプが再発 |
| `changed_type` | M1からM2など、別タイプの誤概念へ変化 |
| `unknown_persisted` | unknownが継続 |
| `regressed` | 正答後に誤答へ戻った |

学習負担ログとして、再テスト回数、学習セッション数、学習ターン数、学習対象として残った回数、合計学習時間、合計テスト時間も集計候補にする。

条件統制チェックとして、control群で `teaching_strategy = general_explanation` が維持されたか、proposed群で誤概念タイプ・過去ログ・学習ステージが教授方略に使われたか、`forbidden_help_given` や `requires_manual_review` が発生したかをCSVで判別できるようにする。

## 主評価指標

### 1. 同種誤答再発率

事前テストで確認された誤概念と同じタイプの誤概念が、再テストで再び出た割合。

```text
same_misconception_recurrence_rate =
same_type_recurrence_count / initial_misconception_count
```

分母:

- pretestで `diagnosed_status = misconception`
- misconception_type が M1, M3 のいずれか
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

L0確認は互換・補助フェーズとして残るが、現行MVPの主到達評価は `final_test` を使う。実装上の保存先は既存互換のため `evaluation_summaries.l0_correct_rate` でよい。

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

現行の `retest_score` は、保存されている `retest` attempts 全体から計算する。次段のログ拡張では、複数周回の再テストを `retest_1`, `retest_2`, ... と周回別に分け、各周回の得点率を `score_timeline_json` またはCSVの `evaluation_summary` 補助行で復元できるようにする。

### 誤概念タイプ別再発率

```text
m1_recurrence_rate = m1_recurrence_count / initial_m1_count
m2_recurrence_rate = m2_recurrence_count / initial_m2_count
m3_recurrence_rate = m3_recurrence_count / initial_m3_count
m4_failure_rate = m4_failure_count / evaluated_m4_context_count
```

M4は今回のMVPでは新規判定・教材方略に使わない。

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
- 平均l0_correct_rate  # 現行MVPでは final_test 正答率として扱う

次段のログ拡張では、群別にも `score_delta_from_pretest_pt` と `score_delta_from_previous_test_pt` の平均を確認できるようにする。増加率は相対率ではなく、まず差分ポイントで扱う。

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
- 参加者別スコア推移
- 用語別スコア推移
- 誤概念タイプ推移
- 未達項目数の減少
- 最終テストまでの学習周回数

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

次段のログ拡張では、`evaluation_summary` 行の `value_json` にスコア推移、誤概念推移、未達項目数推移、学習負担ログ、条件統制チェックを含める。CSV列自体は互換性のため増やさず、詳細は `value_json` で保持する。

## 欠損値の扱い

- 未回答は空欄で出力する
- 途中離脱参加者は `completed = false`
- 指標の分母が0の場合はnull
- AI失敗による未診断は `requires_manual_review = true`
- 管理者手動修正済みの場合はattemptsに反映し、audit_eventsにも残す

## 再計算

評価指標はDB上のattempts、learner_states、recurrence_eventsから再計算可能にする。保存済みsummaryだけに依存しない。
