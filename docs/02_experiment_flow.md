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
[Learning Target Selection]
  ↓
[Learning Session]
  ├─ control: General RAG Tutor + Self Explanation
  └─ proposed: Prerequisite Terms → Concept Understanding
  ↓
[Immediate Retest]
  ↓
[Post Survey]
  ↓
[Finish]
  ↓
[Export & Analysis]
```

`revised_experiment_flow_term_concept_stages_FINAL.md` を新しい設計方針の根拠として扱う。ただし今回の実装では、利用者の指定により二群比較を維持し、事前アンケートは実施しない。

L0確認、転移テスト、Learning Session 2、学習中のL3/L2/L1動的更新は現行参加者フローでは使わない。旧データ列や旧ページは互換用に残してよいが、導線とactive出題から外す。

## Phase 0: Participant Registration

- 被験者IDを自動発行する
- 実験条件をランダム割当または手動指定する
- `group_condition = control | proposed` を保存する
- 同意チェックを保存する
- `current_step = pretest` から開始する

事前アンケートは行わない。

## Phase 1: Pre Test

学習前の理解状態と初期誤概念を測る。5概念について選択式問題だけを出す。

必須仕様:

- 「わからない」選択肢を必ず入れる
- 誤答選択肢には内部的にM1〜M3ラベルを割り当てる
- 選択肢順は参加者ごとにランダム化し、表示順を保存する
- 理由記述欄と自信度入力欄を表示しない
- フィードバック、ヒント、チャットを出さない

## Phase 2: AI Diagnosis

処理順:

1. 選択肢ラベルで初期判定する
2. 正答、誤答、unknownに分類する
3. 誤答選択肢のM1〜M3またはunknownを保存する
4. `learner_states` と `term_assignments` を作成する

診断は分析ログとして保存する。被験者画面にはMラベルを出さない。

## Phase 3: Learning Target Selection

現行5問版では固定上限で切らず、`stable_correct` 以外を全件学習対象にする。

学習対象:

- `misconception`
- `unknown`
- `unstable_correct`

学習対象外:

- `stable_correct`

5問すべて誤答または「わからない」の場合は、最大5対象概念を学習する。

## Phase 4A: Control Learning Session

統制群は通常AIチューターとして実施する。

構造:

1. RAG教材を根拠に対象概念の一般説明を提示する
2. 学習者に対象概念を自分の言葉で説明させる
3. AIが一般的なフィードバックを返す
4. 次の学習対象へ進む

禁止:

- 誤概念タイプの利用
- 過去ログを使った個別化
- 前提用語ゲート
- L3/L2/L1の動的更新

## Phase 4B: Proposed Learning Session

提案群は前提用語ゲート型AIチューターとして実施する。

### 4B-1. 前提用語計画生成

対象概念ごとにAIが前提用語を原則3件生成する。各前提用語には以下を保存する。

- 前提用語名
- 学習者向け教材
- 確認質問
- 期待回答
- 表示順

AI payloadには、対象概念、事前テスト診断、選択誤答、学習対象理由、RAG教材を含める。

### 4B-2. 用語理解

前提用語を1つずつ提示し、記述式確認を行う。

- 最大2回まで回答できる
- 1回目failなら、より簡単な再説明と具体例を提示する
- 2回目failなら、その対象概念は `blocked` として記録し、概念理解へ進めない
- pass条件は、中核要素を含み重大な誤りがないこと

### 4B-3. 概念理解

すべての前提用語をpassした場合のみ、対象概念理解へ進む。

- AIが前提用語を使った対象概念教材を提示する
- 学習者は前提用語を使って対象概念を説明する
- 最大4回まで回答できる
- fail時、AIは不足用語と直前関連用語を返す
- fail時は該当用語レビューへ戻る
- 4回failなら `failed` として記録し、次対象概念へ進む

## Phase 5: Immediate Retest

学習直後に、支援なしで同じ構成概念を理解できたかを測る。

- 学習対象用語だけを出す
- 事前テストと同じ文面は使わない
- 正式 `retest_v1` を使う
- 選択式のみで、理由記述欄と自信度入力欄は表示しない
- 結果は即時表示しない
- 完了後は `post_survey` へ進む

判定:

- 正答
- 誤答
- 誤概念タイプ
- 前回と同じMタイプか
- recurrence_flag

## Phase 6: Post Survey

主観評価を保存する。

- 分かりやすさ
- 使いやすさ
- AIの説明の納得感
- ヒント量の適切さ
- 自由記述

## Phase 7: Export & Analysis

出力:

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

## 中断・再開

- 各フェーズ完了時に `participants.current_step` を更新する
- 同一フェーズ内の途中中断は、最後に保存された回答から再開できるようにする
- テストフェーズでブラウザを閉じた場合、未回答問題だけ再表示する拡張を可能にする
- 同じ問題への二重送信はidempotency keyで防ぐ
