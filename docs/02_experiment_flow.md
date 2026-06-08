# 02. Experiment Flow

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

5用語について選択式問題を出す。対象は、Transformer、Attention、LLMの学習段階、事前学習、事後学習の順とする。事前テストでは記述欄と自信度入力欄を出さない。

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
4. 初期足場掛けレベルを決定する
5. 学習者状態モデルを作成する

診断状態:

| 状態 | 意味 |
|---|---|
| unknown | わからない、空欄、知識不足 |
| misconception | 誤概念あり |
| unstable_correct | 正答だが理由が不十分 |
| stable_correct | 正答かつ理由も妥当 |
| transfer_ready | 確認テストに進める |
| ambiguous | 選択肢と理由が矛盾し判定困難 |

## Phase 4: Learning Target Selection

1回の実験で扱う学習対象は最大4用語を推奨する。対象は事前テスト後に自動選定し、管理画面で確認できるようにする。

優先順位:

1. M1またはM2の誤答
2. M3の誤答
3. unknown
4. unstable_correct
5. stable_correctだが確認テストが必要なもの

同順位の場合は、回答時間が短すぎるものを優先する。それでも同順位なら固定seedでランダム選択する。

## Phase 5: Learning Session 1

1用語あたりの固定構造:

```text
1. 教材エリアでAIミニ教材を提示する
2. 問題エリアで足場掛けレベル別の問い返しと類題を提示する
3. 学習者回答・自己説明を保存する
4. AIフィードバックをログとして保存し、継続時は次ターン教材冒頭へ前の問題・あなたの回答・短い振り返りとして統合する
5. `is_sufficient` に基づく状態更新を保存する
6. セッション完了時は問題を出さず、教材フィードバックだけを表示してから次へ進む
```

重要ルール:

- 被験者に「あなたはM1です」と直接表示しない
- 代わりに自然言語で誤解の可能性を説明する
- 1用語あたり最大3ターン
- 答えだけを聞く質問には答えない
- 学習者の全入力を保存する
- ターン継続時は回答確認後に単独フィードバック枠を表示しない
- ターン2以降の教材には前の問題とあなたの回答を表示する
- セッション完了時は問題・回答欄を消し、教材フィードバックと次へボタンだけを表示する
- 学習セッションではデバッグ用に誤概念タイプ判定、足場掛けレベル、回答判定を表示する
- 統制群では一般解説と一般的な確認問題に限定する

## Phase 6: Immediate Retest

学習直後に誤概念が減ったかを測る。

- 事前テストと同じ構成概念の定義問題・識別問題
- 文面は変える
- 選択肢も可能な範囲で言い換える
- 同じ問題文を完全には使い回さない
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
| 学習ターン | `is_sufficient = true` | 足場掛けレベルを1段階下げる |
| 学習ターン | `is_sufficient = false` | 足場掛けレベルを1段階上げる |
| 再テスト | 誤答 | 足場掛けレベルを維持する |
| 再テスト | 同じMで誤答 | 足場掛け維持 + 教授方略変更 |
| 再テスト | 正答 | 足場掛けレベルを1段階下げる |
| 確認テスト | 正答 | L1を維持し `l0_success = true` を保存する |
| 確認テスト | 誤答 | L2相当へ上げる |

学習ターンではAIの `next_action` を正誤判定や足場掛け更新の根拠にしない。`next_action` は画面遷移補助として扱い、最終レベルはbackendの決定論的ルールで決める。ターン生成時にAIが返す `scaffolding_level` は採用せず、`LearnerState.scaffolding_level` を保存・表示の正とする。

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
- 確認テスト正答なら `l0_success = true`

確認テストの目的は「支援を外した状態の自力解答」を測ることであり、学習を続ける場ではない。

## Phase 12: Export & Analysis

出力:

- participants.csv
- term_assignments.csv
- attempts.csv
- tutor_sessions.csv
- tutor_turns.csv
- learner_states.csv
- recurrence_events.csv
- ai_call_logs.csv
- evaluation_summary.csv

## 中断・再開

- 各フェーズ完了時に `participant_progress` を更新する
- 同一フェーズ内の途中中断は、最後に保存された回答から再開する
- テストフェーズでブラウザを閉じた場合、未回答問題だけ再表示する
- 同じ問題への二重送信はidempotency keyで防ぐ
