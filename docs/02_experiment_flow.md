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
  ├─ control: General RAG Small Questions → Concept Phase 1 → Concept Phase 2
  └─ proposed: Prerequisite Terms → Concept Phase 1 → Concept Phase 2
  ↓
[Immediate Retest]
  ↓
[Post Survey]
  ↓
[Finish]
  ↓
[Export & Analysis]
```

`revised_experiment_flow_3phase_learning_session_v2.md` を新しい設計方針の根拠として扱う。ただし今回の実装対象は学習セッション内部の3段階化に限定する。

v2原文との差分として、事前アンケートは復活させない。転移テストも参加者フローへ戻さない。再テストは現行通り学習対象概念のみを出す。学習対象数は `stable_correct` 以外を全件対象にし、最大5概念まで扱う。

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
- `pretest_v2` をactive版として使い、旧版は回答履歴との参照整合性を保ったまま非active化する
- 誤答は関連する別概念・工程として自然に読める内容にし、知識がない参加者が文章表現だけで除外できないようにする
- 正答と誤答の文体、長さ、専門性を可能な限り揃える
- 「単に」「〜だけ」「名前に〜とあるため」など、誤答であることを示唆する表現を避ける
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

1. 対象概念だけに基づく一般小問を3件生成する
2. 小問ごとに教材と確認質問を提示し、pass/failを保存する
3. failしても同じ小問へ戻らず、次の小問へ進む
4. 概念フェーズ1で教材あり説明確認を1回行う
5. 概念フェーズ2で教材なし・軽い条件付き説明確認を1回行う
6. pass/failにかかわらず次の学習対象へ進む

禁止:

- 誤概念タイプの利用
- 過去ログを使った個別化
- 回答結果に応じた前提用語・教材への戻り処理
- L3/L2/L1の動的更新

## Phase 4B: Proposed Learning Session

提案群は3段階学習セッション型AIチューターとして実施する。

### 4B-1. 前提用語計画生成

対象概念ごとにAIが前提用語を3件生成する。各前提用語には以下を保存する。

- 前提用語名
- 学習者向け教材
- 確認質問
- 期待回答
- 生成理由
- 表示順

AI payloadには、対象概念、事前テスト診断、選択誤答、学習対象理由、RAG教材を含める。

### 4B-2. 用語理解

前提用語を1つずつ提示し、記述式確認を行う。

- 最大2回まで回答できる
- 1回目failなら、より簡単な再説明と具体例を提示する
- 2回目failなら、その対象概念は `blocked` として記録し、概念理解へ進めない
- pass条件は、中核要素を含み重大な誤りがないこと

### 4B-3. 概念フェーズ1: 教材あり

すべての前提用語をpassした場合のみ、対象概念理解へ進む。

- AIが前提用語を使った対象概念教材を提示する
- 学習者は前提用語を使って対象概念を説明する
- 最大3回まで回答できる
- fail時、AIは不足用語と直前関連用語を返す
- fail時は該当用語レビューまたはフェーズ1再提示へ戻る
- 3回failなら `failed_phase1` として記録し、次対象概念へ進む
- pass時は概念フェーズ2へ進む

### 4B-4. 概念フェーズ2: 教材なし・軽い条件あり

概念フェーズ2は、学習セッション内で教材本文を外した状態に近い確認である。主評価ではなく、重要な補助指標として扱う。

- 教材本文、模範説明、直接的ヒントは表示しない
- 問題文、軽い条件、使用語の一部、解答形式は表示してよい
- フェーズ1と同じ問いをそのまま出さない
- 最大3回まで回答できる
- pass時は `completed`
- fail 1〜2回目は概念フェーズ1へ戻る
- 3回failなら `failed_phase2` として記録し、次対象概念へ進む

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
