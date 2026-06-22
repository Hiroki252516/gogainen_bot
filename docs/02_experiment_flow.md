# 02. Experiment Flow

## 2026-06 Iterative Test-Learning Flow Update

現行フローは、固定の事前テスト・学習・再テストではなく、反復型の `テスト → 未達項目だけ学習 → 再テスト` を正とする。正解した用語は次周回のテスト・学習対象から除外し、不正解・`unknown`・誤概念選択肢の用語だけを残す。残り対象が0件になったら、現行seedの2用語すべてを対象にした `final_test` へ進み、その後アンケート遷移画面 `/survey` へ進む。

学習セッション内は引き続き `term_understanding → concept_understanding → final_feedback` のステージ制を使う。`unknown` とM1〜M3の誤概念に対して、L3用語理解からL2概念理解へ進める。M4は今回の教材方略から外す。

## 2026-06 Timing Log and Same-Item Retest Update

分析で「どれくらいの時間で解けているか」を見るため、テスト問題と学習セッション内問題は、問題表示時刻、回答時刻、回答時間秒を保存する。`created_at` はサーバー受信・保存時刻として残し、表示から回答までの所要時間分析には `question_shown_at`、`answered_at`、`response_time_sec` を使う。

再テストは未達用語だけではなく、事前テスト対象の全用語を毎回出題する。採点後の学習対象更新では、正答した用語を次周回の学習対象から外し、誤答・`unknown` の用語だけを残す。

今回の卒研運用では、比較しやすさを優先し、L2概念理解問題、再テスト、最終テストで完全に同じ問題文と選択肢セットを使う。これは旧方針の「フェーズごとに問題文を分ける」より優先する運用変更である。


## 全体フロー

```text
[Start]
  ↓
[Participant Registration]
  ↓
[Pre Test]
  ↓
[AI Diagnosis]
  ↓
[Learner State Initialization]
  ↓
[Learning Target Selection]
  ↓
[Learning Session 1]
  ↓
[Immediate Retest]
  ↓
[State Update]
  ↓
[Learning Session 2]
  ↓
[Confirmation Check]
  ↓
[Finish]
  ↓
[Export & Analysis]
```

遅延再テストは卒研運用で可能なら追加する。MVPでは必須にしないが、データモデルとAPIは `delayed_retest` phase を追加できるようにしておく。

## Phase 0: Participant Registration

- 被験者IDを自動発行する
- 実験条件をランダム割当または手動指定する
- `group_condition = control | proposed` を保存する
- 同意チェックを保存する
- 途中再開用に現在ステップを保存する

保存項目:

- participant_id
- display_code
- group_condition
- assignment_method
- consent_checked
- current_step
- created_at

## Phase 1: Pre Test

学習前の理解状態と誤概念を測る。

2用語について選択式問題を出す。対象は、Transformer、LLMの学習段階の順とする。事前テストでは記述欄と自信度入力欄を出さない。

必須仕様:

- 「わからない」選択肢を必ず入れる
- 誤答選択肢には内部的にM1〜M3ラベルを割り当てる
- 選択肢順はランダム化できる
- 表示順ランダム化時も内部ラベルは保持する
- テスト中はフィードバック、ヒント、チャットを出さない

## Phase 3: AI Diagnosis

処理順:

1. 選択肢ラベルで初期判定する
2. 正答、誤答、未知、不安定正答に分類する
3. 誤概念タイプをM1〜M4に分類する
4. 初期学習ステージと互換ログ用の初期scaffolding_levelを決定する
5. 学習者状態モデルを作成する

診断状態:

| 状態 | 意味 |
|---|---|
| unknown | わからない、空欄、知識不足 |
| misconception | 誤概念あり |
| unstable_correct | 正答だが理由が不十分 |
| stable_correct | 正答かつ理由も妥当 |
| transfer_ready | 最終テストに進める |
| ambiguous | 選択肢と理由が矛盾し判定困難 |

## Phase 4: Learning Target Selection

1回の実験で扱う候補は、事前テストで扱った2概念すべてとする。診断後、正解済み用語は学習対象から除外し、未達用語だけを `TermAssignment.is_learning_target = true` として残す。学習対象一覧には、その時点で残っている確認項目だけを表示する。

優先順位:

1. M1またはM2の誤答
2. M3の誤答
3. unknown
4. unstable_correct
5. stable_correctだが最終テストが必要なもの

同順位の場合は、回答時間が短すぎるものを優先する。それでも同順位なら固定seedでランダム選択する。

## Phase 5: Learning Session 1

1用語あたりの固定構造:

```text
1. `term_understanding` で、対象概念に必要な構成用語を1つずつ扱う
2. 教材エリアでは、現在の構成用語または対象概念について、定義、役割、よくある誤解との差、判断基準を最初から十分に提示する
3. 問題エリアでは、教材内容を学習者が自分の言葉で再説明する記述問題を出す
4. 学習者回答・自己説明を保存する
5. AIフィードバックをログとして保存し、継続時は次ステージ教材冒頭へ前の問題・あなたの回答・短い振り返りとして統合する
6. `is_sufficient` に基づき、次の構成用語、`concept_understanding`、または `final_feedback` へ進める
7. セッション完了時は問題を出さず、教材フィードバックだけを表示してから次へ進む
```

重要ルール:

- 被験者に「あなたはM1です」と直接表示しない
- 代わりに自然言語で誤解の可能性を説明する
- 答えだけを聞く質問には答えない
- 学習者の全入力を保存する
- ターン継続時は回答確認後に単独フィードバック枠を表示しない
- ターン2以降の教材には前の問題とあなたの回答を表示する
- セッション完了時は問題・回答欄を消し、教材フィードバックと次へボタンだけを表示する
- 学習セッションではデバッグ用に誤概念タイプ判定、learning_stage、回答判定、teaching_strategyを表示する
- 統制群では一般解説と一般的な確認問題に限定する

## Phase 6: Immediate Retest

学習直後に誤概念が減ったかを測る。

- 事前テストと同じ構成概念の定義問題・識別問題
- 文面は変える
- 選択肢も可能な範囲で言い換える
- L2・再テスト・最終テストで同一問題文を使う
- 結果は即時表示しない

判定:

- 正答
- 誤答
- 誤概念タイプ
- 前回と同じMタイプか
- recurrence_flag

## Phase 7: State Update

| 場面 | 今回 | 次の処理 |
|---|---|---|
| 用語理解段階 | `is_sufficient = true` | 次の構成用語へ進む。全構成用語が十分なら概念理解段階へ進む |
| 用語理解段階 | `is_sufficient = false` | 同じ構成用語を再提示する |
| 概念理解段階 | `is_sufficient = true` | `final_feedback` へ進み、セッション完了 |
| 概念理解段階 | `is_sufficient = false` | 用語理解段階の先頭へ戻る |
| 再テスト | 誤答 | learner_stateをneeds_review相当に更新する |
| 再テスト | 同じMで誤答 | recurrence_flagを立て、教授方略を変更する |
| 再テスト | 正答 | learner_stateをstable_correct相当に更新する |
| 最終テスト | 正答 | `l0_success = true` を保存する |
| 最終テスト | 誤答 | needs_review相当に更新する |

学習ターンではAIの `next_action` を正誤判定やステージ遷移の根拠にしない。`next_action` は補助情報として扱い、次ステージ、構成用語インデックス、セッション完了はbackendの決定論的ルールで決める。`scaffolding_level` は既存ログ互換のため保存するが、被験者画面の進行表示や教材説明量の制御には使わない。

再発は、同一参加者、同一用語、前回の主要誤概念タイプと今回の主要誤概念タイプが一致する場合に true とする。`unknown` は誤概念再発に含めないが、知識不足継続として別集計する。

## Phase 8: Learning Session 2

Phase 7で更新された状態に基づき、2回目の学習セッションを行う。再発がある場合は同じ説明を繰り返さず、教授方略を変更する。

再発時の例:

- M1再発: 定義説明の繰り返しではなく、誤カテゴリーと正カテゴリーの比較に切り替える
- M2再発: 比較表だけでなく、境界判断問題を出す
- M3再発: キーワードに頼らず判断基準を説明させる

## Phase 9: Confirmation Check

足場掛けなしで自力解答できるかを確認する。

- ヒントなし
- チャット不可
- 例示不可
- 即時正誤フィードバック不可
- 自由記述または理由記述必須
- 最終テスト正答なら `l0_success = true`

最終テストの目的は「支援を外した状態の自力解答」を測ることであり、学習を続ける場ではない。

## Phase 10: Final Test

未達用語が0件になったら、途中で除外された正解済み用語も含め、現行seedの2用語すべてを対象にした `final_test` を実施する。最終テストは選択式で、理由記述は要求しない。採点後は `/survey` へ進む。

現行 `/survey` はアンケート遷移用の暫定画面であり、「アンケート画面は次の実装で接続します」と表示して `/finish` へ進める。

## Phase 12: Export & Analysis

現行の管理画面では、全体ログと被験者別ログを確認し、それぞれCSVとして出力できる。

出力:

- overview.csv
- 被験者別ログCSV

CSVは `record_type` で回答、学習状態、学習ターン、AI呼び出し、再発イベント、評価サマリーを区別する。既存のテーブル別CSV APIは互換用に残してよいが、管理画面の主導線からは外す。

## 中断・再開

- 各フェーズ完了時に `participant_progress` を更新する
- 同一フェーズ内の途中中断は、最後に保存された回答から再開する
- テストフェーズでブラウザを閉じた場合、未回答問題だけ再表示する
- 同じ問題への二重送信はidempotency keyで防ぐ
