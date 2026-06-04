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
[L0 Check]
  ↓
[Transfer Test]
  ↓
[Post Survey]
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

各用語について以下を出す。

1. 選択式問題

必須仕様:

- 「わからない」選択肢を必ず入れる
- 誤答選択肢には内部的にM1〜M3ラベルを割り当てる
- M4は主に転移テストで検出する
- 選択肢順はランダム化できる
- 表示順ランダム化時も内部ラベルは保持する
- 事前テストでは理由記述欄と自信度入力欄を表示しない
- テスト中はフィードバック、ヒント、チャットを出さない

## Phase 2: AI Diagnosis

処理順:

1. 選択肢ラベルで初期判定する
2. 正答、誤答、未知に分類する
3. 誤概念タイプをM1〜M4に分類する
4. 初期足場掛けレベルを決定する
5. 学習者状態モデルを作成する

診断状態:

| 状態 | 意味 |
|---|---|
| unknown | わからない、空欄、知識不足 |
| misconception | 誤概念あり |
| unstable_correct | 選択式だけでは理解が安定していると断定しにくい正答 |
| stable_correct | 正答 |
| transfer_ready | L0または転移問題に進める |
| ambiguous | 選択肢情報だけでは判定困難 |

## Phase 3: Learning Target Selection

1回の実験で扱う学習対象は最大4用語を推奨する。対象は事前テスト後に自動選定し、管理画面で確認できるようにする。

優先順位:

1. M1またはM2の誤概念
2. M3の誤概念
3. unknown
4. unstable_correct
5. stable_correctだが転移準備が必要なもの

同順位の場合は、回答時間が短すぎるものを優先する。それでも同順位なら固定seedでランダム選択する。

## Phase 4: Learning Session 1

1用語あたりの固定構造:

```text
1. 前回回答の提示
2. AI診断の自然言語提示
3. 誤概念タイプ別ミニ教材
4. 足場掛けレベル別の問い返し
5. 学習者回答
6. AIフィードバック
7. 類題またはミニ確認問題
8. 自己説明
9. 状態更新
```

重要ルール:

- 被験者に「あなたはM1です」と直接表示しない
- 代わりに自然言語で誤解の可能性を説明する
- 1用語あたり最大3ターン
- 答えだけを聞く質問には答えない
- 学習者の全入力を保存する
- 学習セッションでは自信度入力欄を表示しない
- 統制群では一般解説と一般的な確認問題に限定する

## Phase 5: Immediate Retest

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

## Phase 6: State Update

| 前回 | 今回 | 次の処理 |
|---|---|---|
| 誤答 | 正答 | 足場掛けレベルを1段階下げる |
| 誤答 | 誤答 | 足場掛けレベルを維持する |
| 誤答 | 同じMで誤答 | 足場掛け維持 + 教授方略変更 |
| 正答 | 正答 | 足場掛けレベルを1段階下げる |
| 正答 | 誤答 | 足場掛けレベルを1段階上げる |
| L0 | 正答 | L0維持、支援なし理解として記録 |
| L0 | 誤答 | L1またはL2へ戻す |

再発は、同一参加者、同一用語、前回の主要誤概念タイプと今回の主要誤概念タイプが一致する場合に true とする。`unknown` は誤概念再発に含めないが、知識不足継続として別集計する。

## Phase 7: Learning Session 2

Phase 7で更新された状態に基づき、2回目の学習セッションを行う。再発がある場合は同じ説明を繰り返さず、教授方略を変更する。

再発時の例:

- M1再発: 定義説明の繰り返しではなく、誤カテゴリーと正カテゴリーの比較に切り替える
- M2再発: 比較表だけでなく、境界判断問題を出す
- M3再発: キーワードに頼らず判断基準を説明させる
- M4再発: 学習文脈と転移文脈の共通構造を抽出させる

## Phase 8: L0 Check

足場掛けなしで自力解答できるかを確認する。

- ヒントなし
- チャット不可
- 例示不可
- 即時正誤フィードバック不可
- 自由記述または理由記述必須
- L0正答なら `l0_success = true`

L0チェックの目的は「支援を外した状態の自力解答」を測ることであり、学習を続ける場ではない。

## Phase 9: Transfer Test

学習時とは異なる文脈で概念を使えるか測る。

- 全問L0
- ヒントなし
- チャット不可
- 別文脈の問題
- 理由記述必須
- M4 文脈転移失敗型をここで検出する

転移テストはテスト慣れによる成績向上を排除し、概念理解の深さを見るために必須である。

## Phase 10: Post Survey

主観評価を保存する。

- 分かりやすさ
- 使いやすさ
- AIの説明の納得感
- ヒント量の適切さ
- 自由記述

## Phase 11: Export & Analysis

出力:

- participants.csv
- participant_surveys.csv
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
