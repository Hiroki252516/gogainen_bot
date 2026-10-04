# 12. Evaluation Metrics

## 2026-06 Iterative Metrics Update

現行フローでは、学習後の各再テストを3用語対象の形成的確認として扱う。`final_test`は全員共通の事後テストではなく、pretestで学習対象がなかった参加者に使う内部フェーズである。学習対象があった参加者は再テストを受け、3用語すべて正解した場合は追加の確認を省略してsurveyへ進む。このため実際の到達時スコアは、利用可能な`final_test`、互換`l0_check`、または最終再テスト満点から得られ、測定経路が参加者間で異なる。`l0_correct_rate`を全参加者共通の同一時点事後テストとして解釈してはならない。研究上、群間の共通事後測定が必要な場合は、全員に同じテストを受けさせるフロー変更を別途行う。

現行MVPの `final_test` は、3用語を対象にしたA〜Jの10選択肢から、A〜Iの3つまたはJ「わからない」単独を選ぶテストである。理由記述は要求しない。

時間分析では、問題表示時刻 `question_shown_at`、回答時刻 `answered_at`、回答時間秒 `response_time_sec` を使う。`created_at` はサーバー保存時刻として扱い、所要時間の主指標にはしない。

現行実装の `evaluation_summaries` は、参加者単位の `pretest_score`, `retest_score`, `l0_correct_rate`, 同種誤答再発率、Mタイプ別再発率に加えて、`test`、`retest_1`、`retest_2` 以降の得点推移、誤概念推移、学習負担、条件統制のJSONを保存する。`l0_correct_rate` は互換名で、通常は `final_test`、それがなければ互換 `l0_check`、さらに両方がなく再テスト満点で最終テストを省略した場合は最新の再テスト3用語の正答率を入れる。`score_timeline_json` と `condition_check_json` に `final_test_skipped_after_retest_mastery` と `final_score_source` を保存する。`transfer_correct_rate`、`m4_failure_rate`、`unknown_persistence_rate` など固定問題や集計処理が未提供の値は `null` になり得る。

## 現行保存値: 得点率推移・誤概念推移ログ

現行の再計算処理は、事前テスト、再テスト、最終テスト、L0確認の既存attemptsを時系列としてまとめる。再テストの自動周回ループはなく、複数回分が存在する場合に保存済み回答を周回順に集計する。

`score_timeline_json["rounds"]`の各要素へ、次のキーを保存・出力する。固定のトップレベルキー（`test_score_rate`など）を別々に作る形式ではない。

- 周回識別: `round`、`phase`、`attempt_index`
- 問題数・正答数・得点率: `question_count`、`correct_count`、`score_rate`
- 事前比・直前テスト比の差分ポイント: `score_delta_from_pretest_pt`、`score_delta_from_previous_test_pt`
- 未達項目数: `remaining_learning_target_count`
- 回答時刻: `event_time`
- 誤概念タイプ推移: 別の`misconception_timeline_json`に`test -> retest_n`として保存

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
| `same_type_recurred` | 同じ誤概念タイプが再発 |
| `changed_type` | 別タイプの誤概念へ変化（現行固定問題ではM1とM3の間の変化を扱う） |
| `unknown_persisted` | unknownが継続 |
| `regressed` | 正答から誤概念へ変化（管理画面の表示名: 誤概念） |
| `unclassified` | 事前テスト後の再テスト等が未実施、または判定材料が不足 |

## 群別誤概念推移集計

管理画面の `control` / `proposed` 群タブでは、参加者別評価サマリーを回答ログから自動計算したうえで、`misconception_timeline_json` を用語ごとに集計する。集計対象は、その用語の採点済み事前テストイベントを持つ参加者とし、未受験者・途中離脱者など事前テスト結果がない参加者は `missing_count` に分ける。

群・用語ごとに `resolved`、`same_type_recurred`、`changed_type`、`unknown_persisted`、`regressed`、`unclassified` の人数と割合を返す。割合の分母は群全体ではなく、その用語の `eligible_count` とする。集計値は自動更新された参加者別評価サマリーから算出し、新しいDB列は追加しない。`regressed` は研究用の内部コードを維持し、画面では「誤概念」と表示する。

学習負担ログとして、再テスト回数、学習セッション数、学習ターン数、学習対象として残った回数、合計学習時間、合計テスト時間も集計候補にする。`remaining_learning_target_count`は、現行の再計算処理では各テスト周回の不正解件数を記録しており、`TermAssignment`の現在件数を直接参照する値ではない。

条件統制チェックとして、control群では `control_general_explanation_maintained` により`teaching_strategy = general_explanation`の維持を確認し、proposed群では`proposed_adaptive_strategy_used`、`strategy_changed_count`、`forbidden_help_count`、`manual_review_count`を保存する。誤概念タイプ・過去ログ・学習ステージなど、実際に渡されたpayloadの詳細は`AICallLog`のrequest payloadで確認する。評価サマリーの条件統制JSONだけで、payload内の各入力項目の利用を個別に証明するわけではない。
現行の新規学習ターンでは`TutorTurn.strategy_changed`が常に`false`の互換項目として保存されるため、`strategy_changed_count`は通常0になる。将来、方略変更を実装した場合にこの指標を再利用できる。

## 主評価指標

### 1. 同種誤答再発率

事前テストで確認された誤概念と同じタイプの誤概念が、再テストで再び出た割合。

```text
same_misconception_recurrence_rate =
same_type_recurrence_count / initial_misconception_count
```

分母（現行MVP）:

- pretestで `diagnosed_status = misconception`
- `misconception_type` が M1またはM3
- 学習対象になった用語

分子:

- retestで同一参加者・同一用語の misconception_type がpretestと同じ
- recurrence_flag = true

`unknown` と `ambiguous` は主指標の分母に含めない。M2/M4はtaxonomyには存在するが、現行固定問題の選択肢からは判定しないため、M2/M4の再発率は将来の固定診断問題を追加した後に算出する。

### 2. 最終テスト正答率

最終テストでヒントなし・即時フィードバックなしで正答できた割合。

```text
final_test_correct_rate = final_test_correct_count / final_test_question_count
```

分母:

- final_test phaseで出題された問題数

分子:

- `is_correct = true`

L0確認は互換・補助フェーズとして残る。`evaluation_summaries.l0_correct_rate`は互換列であり、集計可能な回答がある場合は`final_test`、それがなければ互換`l0_check`、両方がなく再テスト満点で最終確認を省略した場合は再テスト満点を代用する。したがって、同列の値だけでは参加者が受けた測定フェーズを特定できず、`final_score_source`等と合わせて読む。

## 補助指標

以下のうち、`retest_score` と同種誤答再発率などは現行ログから利用できる。一方、M2/M4を固定問題で評価する指標、unknown継続率、主観理解度差分、支援段階変化量の式は、研究計画上の将来指標であり、現行MVPの自動集計結果ではない。

### 正答率

```text
score = correct_count / total_question_count
```

対象:

- pretest
- retest
- final_test
- l0_check は補助・互換指標

現行の `retest_score` は、保存されている `retest` attempts 全体から計算する。複数周回の再テストが存在する場合は、`score_timeline_json` とCSVの `evaluation_summary` 補助行から、存在する順序で得点率を確認できる。backendが自動で周回を生成するわけではない。

### 誤概念タイプ別再発率（M1/M3は現行、M2/M4は将来）

```text
m1_recurrence_rate = m1_recurrence_count / initial_m1_count
m3_recurrence_rate = m3_recurrence_count / initial_m3_count

# 将来の固定診断問題を追加した場合の定義
m2_recurrence_rate = m2_recurrence_count / initial_m2_count
m4_failure_rate = m4_failure_count / evaluated_m4_context_count
```

現行の `recalculate_evaluation` はM1/M3の分母だけを対象にし、M2の再発率は入力がないため通常 `null`、M4失敗率は未算出である。M2/M4は内部taxonomy・ログ・将来分析の分類値として保持する。

### Unknown継続率

```text
unknown_persistence_rate =
unknown_in_retest_count / initial_unknown_count
```

これは誤概念再発ではなく、知識不足が残った割合として扱う。

現行の `recalculate_evaluation` は `unknown_persistence_rate` を算出せず、未提供値として `null` を保存する。上式は将来の補助指標の定義である。

### 主観理解度変化

```text
understanding_delta = post_understanding - pre_understanding
```

用語別にも全体平均でも出せるようにする。

現行モデルにアンケート値を保存する領域はあるが、理解度差分を評価サマリーへ自動算出する処理は未実装である。

### 支援段階変化量

```text
scaffolding_reduction =
initial_scaffolding_numeric - final_scaffolding_numeric
```

数値化:

- L3 = 3
- L2 = 2

現行運用では `scaffolding_level` は内部互換・ログ値として `L3/L2` を使う。ただし、`scaffolding_reduction` を評価サマリーへ自動保存する処理は未実装であり、`L3 -> L2` の変化量は将来指標として扱う。参加者向けの学習段階は`enrichment`、`conceptual_change`、`final_feedback`で表す。

## 群別比較

現行MVPの管理サマリーでは、群別に次の集計を表示する。

- group_condition別 participant_count
- 平均same_misconception_recurrence_rate
- 平均l0_correct_rate  # final_test正答率（通常）、互換l0_check正答率、または最終テスト省略時の再テスト満点
- 平均score_delta_from_pretest_pt  # 最終テストまたはL0確認の事前比差分。再テスト満点で最終テストを省略した場合はその再テストを使用

参加者別の評価サマリーとCSVには`pretest_score`、`retest_score`も保存・出力されるが、現行の群別管理サマリーにはこれらの平均値を含めない。詳細なグラフ表示や周回別の群間グラフは将来対応である。

小規模な卒研では統計検定より、参加者別・用語別の変化を説明できるCSVを重視する。必要なら外部分析で以下を行う。

- 比率比較
- Fisherの正確確率検定
- McNemar検定
- 用語別クロス集計

## 将来の管理画面グラフ

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

- 全体ログ: 全参加者の進捗、最近の統合回答履歴、評価サマリーを見る
- 全体ログCSV: `overview.csv`
- 全体ログ Excel互換CSV（UTF-8 BOM付き）: `overview_excel.csv`
- 被験者別ログ: 1人の統合回答履歴、学習状態、学習セッション詳細を見る
- 被験者別ログCSV: 1人分のログCSV
- 被験者別ログ Excel互換CSV（UTF-8 BOM付き）: 1人分のログCSV

操作監査、AI呼び出し、再発イベントの詳細は管理画面には常設表示しないが、DB/API/CSVには研究ログとして保持する。ギブアップの有無と回数は管理画面の被験者一覧・詳細で確認できる。

ログCSVは1ファイルにまとめ、行ごとに `record_type` を持たせる。

```text
record_type, source_type, participant_id, display_code, phase, term_slug, event_time, question_shown_at, answered_at, response_time_sec, question_body, selected_option_body, question_body_snapshot, option_order_snapshot, summary, value_json
```

回答単位の行は `record_type=answer` とし、`source_type=test_attempt` または `source_type=learning_turn` で区別する。`learner_state`, `tutor_session`, `ai_call`, `recurrence`, `evaluation_summary` は補助行として同じCSVに入る。学習ターン回答は `answer` 行として統合するため、重複する `record_type=tutor_turn` 行は出さない。

現行の `evaluation_summary` 行の `value_json` には、利用可能なスコア推移、誤概念推移、未達項目数推移、学習負担ログ、条件統制チェックを入れる。CSV列自体は互換性のため増やさず、詳細は `value_json` で保持する。

## 欠損値の扱い

- 未回答は空欄で出力する
- 途中離脱参加者は `completed = false`
- 指標の分母が0の場合はnull
- AI失敗による未診断はAPIエラーと `ai_call_logs.status=failed` で追跡する。手動レビュー状態へ自動移行するとは限らない
- 管理者による診断結果の手動修正UIと、その修正内容の `audit_events` への書き込みは将来対応である。ギブアップ・参加者削除の監査記録は現行実装で保存する

## 再計算

評価指標はDB上の`participants`、`attempts`、`learner_states`、`term_assignments`、`tutor_sessions`、`tutor_turns`、`recurrence_events`から再計算可能にする。管理画面の評価サマリー・群集計・被験者ログ・ログCSVを参照した時点で、3用語の事前テストが採点済みなら、保存済みsummaryがない場合、元ログより古い場合、または参加者の完了状態と不一致の場合に自動更新する。再計算履歴はDBと全体ログCSVに残すが、管理画面の一覧は参加者ごとの最新summaryだけを表示する。管理画面の再計算ボタンは、同じ処理を明示的に強制実行するために残す。

`overview_excel.csv` と被験者別 `*_logs_excel.csv` は、Excelで開きやすいUTF-8 BOM付きCSVであり、複数シートを持つ`.xlsx`ブックではない。分析時は `record_type` と `source_type` で行を分け、詳細なJSONは `value_json` から取得する。
