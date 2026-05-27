# 14. Testing and Acceptance Criteria

## Unit Tests

### backend

- diagnosis service
- scaffolding level update
- recurrence calculation
- metric calculation
- CSV export
- AIBackend mock

### frontend

- pretest form
- confidence input
- learning session page
- admin dashboard rendering

## Integration Tests

- create participant
- submit pretest
- run diagnosis with MockAIBackend
- create learner states
- run learning session
- submit retest
- compute recurrence
- run transfer test
- export CSV

## MockAIBackend

必ず実装する。Codex app-serverなしでもテストが通るようにする。

Mock rules:

- correct optionなら stable_correct
- known M optionならそのMを返す
- unknown optionなら unknown
- reason_textに「同じ」「同一」「混同」があればM2寄せ
- reason_textに「言葉」「字」「単語」があればM3寄せ

## Acceptance Criteria

### A. 基本実験フロー

- 被験者を作成できる
- 事前アンケートを保存できる
- 事前テストを完了できる
- AI診断が実行される
- learner_states が作成される
- 学習セッションが開始できる
- 再テストが実施できる
- 転移テストが実施できる
- 評価サマリーが生成される

### B. 提案群の動作

- 誤概念タイプに応じて教授方略が変わる
- L3〜L0が保存される
- 正答時にレベルが下がる
- 誤答時にレベルが維持または上がる
- 同じMが再発したら recurrence_flag = true
- 同じMが再発したら teaching_strategy が変更される

### C. 統制群の動作

- 一般解説のみ
- 誤概念分類は保存されるが教授に使われない
- 足場掛けレベルは固定またはnull
- teaching_strategyは general_explanation

### D. データ出力

- attempts.csv が出力できる
- tutor_turns.csv が出力できる
- evaluation_summary.csv が出力できる

### E. AIバックエンド

- `AI_BACKEND=mock` で完全に動く
- `AI_BACKEND=codex_app_server` でCodex app-serverに接続できる
- app-server未接続時は分かりやすいエラーを出す
- ChatGPT未ログイン時はログイン案内を出す
