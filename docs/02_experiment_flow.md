# 02. Experiment Flow

## 全体フロー

```text
[Start]
  ↓
[Participant Registration]
  ↓
[Pre Survey]
  ↓
[Pre Test]
  ↓
[AI Diagnosis]
  ↓
[Learner State Initialization]
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
[Export & Analysis]
```

## Phase 0: Participant Registration

- 被験者IDを自動発行
- 実験条件をランダム割当または手動指定
- `group_condition = control | proposed` を保存

## Phase 1: Pre Survey

背景知識を把握する。

- AI・機械学習の学習経験
- プログラミング経験
- ChatGPT等の利用経験
- AI用語への自信度

## Phase 2: Pre Test

学習前の理解状態と誤概念を測る。

各用語について以下を出す。

1. 選択式問題
2. 選択理由の自由記述
3. 自信度 1〜5

必須仕様:

- 「わからない」選択肢を必ず入れる
- 誤答選択肢には内部的にM1〜M3ラベルを割り当てる
- M4は主に転移テストで検出する
- 選択肢順はランダム化できるようにする
- 表示順ランダム化時も内部ラベルは保持する

## Phase 3: AI Diagnosis

処理順:

1. 選択肢ベースで初期判定
2. 理由記述をAIが評価
3. 正答・誤答・未知・不安定正答に分類
4. 誤概念タイプをM1〜M4に分類
5. 初期足場掛けレベルを決定
6. 学習者状態モデルを作成

診断状態:

| 状態 | 意味 |
|---|---|
| unknown | わからない、空欄、知識不足 |
| misconception | 誤概念あり |
| unstable_correct | 正答だが理由が不十分 |
| stable_correct | 正答かつ理由も妥当 |
| transfer_ready | L0または転移問題に進める |

## Phase 4: Learning Session 1

事前テストで以下に該当した用語を優先する。

1. 誤答かつ自信度高
2. M1またはM2
3. M3
4. unknown
5. 正答だが理由不十分

1回の実験で扱う学習対象は最大4用語を推奨する。

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
9. 自信度入力
10. 状態更新
```

重要ルール:

- 被験者に「あなたはM1です」と直接表示しない
- 代わりに自然言語で誤解の可能性を説明する
- 1用語あたり最大3ターン
- 答えだけを聞く質問には答えない
- 学習者の全入力を保存する

## Phase 5: Immediate Retest

学習直後に誤概念が減ったかを測る。

- 事前テストと同型の定義問題・識別問題
- 文面は変える
- 同じ問題文を完全には使い回さない

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
| L0 | 正答 | 支援なし理解として記録 |
| L0 | 誤答 | L1またはL2へ戻す |

## Phase 7: Learning Session 2

Phase 6で更新された状態に基づき、2回目の学習セッションを行う。再発がある場合は同じ説明を繰り返さず、教授方略を変更する。

## Phase 8: L0 Check

足場掛けなしで自力解答できるかを確認する。

- ヒントなし
- チャット不可
- 例示不可
- 自由記述または理由記述必須
- L0正答なら `l0_success = true`

## Phase 9: Transfer Test

学習時とは異なる文脈で概念を使えるか測る。

- 全問 L0
- ヒントなし
- チャット不可
- 別文脈の問題
- 理由記述必須
- M4 文脈転移失敗型をここで検出する

## Phase 10: Export & Analysis

出力:

- participants.csv
- attempts.csv
- tutor_logs.csv
- learner_states.csv
- evaluation_summary.csv
