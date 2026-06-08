# 14. Testing and Acceptance Criteria

## 2026-06 Stage-Based Learning Acceptance

ステージ制学習の受け入れ条件:

- 用語理解段階で十分回答しても、構成用語が残っていれば `session_completed = false` のまま次の構成用語へ進む。
- 全構成用語が十分回答されると `concept_understanding` へ進む。
- 概念理解段階で不十分なら `term_understanding` の先頭へ戻る。
- 概念理解段階で十分なら `session_completed = true` になり、最終フィードバック画面を表示する。
- frontendには「ターン: x / 3」と「足場掛けレベル: Lx」を表示しない。


## Testing Strategy

研究システムなので、見た目よりも以下を重点的にテストする。

- 実験フローが崩れないこと
- 群条件が混ざらないこと
- ログが欠けないこと
- 評価指標が再計算可能であること
- 通常実行でCodex app-server経由のAI呼び出しが動くこと
- 自動テストではMockAIBackendを明示指定して決定論的に動くこと

## Unit Tests

### backend

- DiagnosisService
- ScaffoldingService
- Recurrence calculation
- Evaluation metric calculation
- CSV export
- Question randomization
- Learning target selection
- AIBackend mock
- Pydantic schema validation
- forbidden help detection

### frontend

- pretest form
- no confidence input in pretest and learning session
- learning session page
- confirmation page without chat
- admin dashboard rendering
- submit button double-click prevention

## Integration Tests

- create participant
- fetch pretest questions
- submit pretest attempts
- run diagnosis with MockAIBackend
- create learner states
- select learning targets
- run learning session
- submit retest
- compute recurrence
- run confirmation check
- generate evaluation summary
- export CSV

## AIBackend Acceptance

通常実行では `AI_BACKEND=codex_app_server` を使う。

- `account/read` でChatGPT/Codexログイン状態を確認できる
- `thread/start` と `turn/start` を使って構造化JSONを生成できる
- `outputSchema` で診断・教授・採点・フィードバックの戻り値を制約する
- `codex_app_server` モードではMockへ自動フォールバックしない
- app-server未接続・未ログイン・timeout・schema失敗は `ai_call_logs.status=failed` に残す

## MockAIBackend Acceptance

テスト・CI・障害切り分け用として実装する。`AI_BACKEND=mock` を明示した場合だけ使う。

Mock rules:

- correct optionなら stable_correct
- known M optionならそのMを返す
- unknown optionなら unknown
- reason_textに「同じ」「同一」「混同」があればM2寄せ
- reason_textに「言葉」「字」「単語」「名前」があればM3寄せ
- recurrence_flagはbackendで判定

## Acceptance Criteria

### A. 基本実験フロー

- 被験者を作成できる
- 事前テストを完了できる
- AI診断が実行される
- learner_states が作成される
- 学習対象用語が最大4件選ばれる
- 学習セッションが開始できる
- 再テストが実施できる
- 確認テストが実施できる
- 評価サマリーが生成される

### B. 提案群の動作

- 誤概念タイプに応じて教授方略が変わる
- L3〜L1が保存される
- 学習ターンで `is_sufficient = true` のときレベルが1段下がる
- 学習ターンで `is_sufficient = false` のときレベルが1段上がる
- `next_action = move_next` でも `is_sufficient = false` ならレベルは下がらない
- 同じMが再発したら recurrence_flag = true
- 同じMが再発したら teaching_strategy が変更される
- 学習セッションの通常画面にデバッグ用の誤概念タイプ判定、足場掛けレベル、回答判定、`teaching_strategy` が表示される
- 回答後のデバッグ欄は更新後の `next_scaffolding_level` を表示する
- ターン2以降の教材に前の問題とあなたの回答が表示される
- セッション完了時は問題・回答欄を表示せず、教材フィードバックと次へボタンだけを表示する
- 教材本文やAIフィードバック本文にはM1〜M4などの内部ラベルが混ざらない

### C. 統制群の動作

- 一般解説のみ
- 誤概念分類は保存されるが教授に使われない
- 足場掛けレベルは固定またはnull
- teaching_strategyは general_explanation
- 過去ログに基づく個別化をしない

### D. テストフェーズ制御

- pretestで正誤を表示しない
- retestでヒントを出さない
- confirmation checkでチャット欄がない
- 同じ問題文をpretest/retestで使い回さない

### E. データ出力

- participants.csv が出力できる
- attempts.csv が出力できる
- learner_states.csv が出力できる
- tutor_turns.csv が出力できる
- recurrence_events.csv が出力できる
- ai_call_logs.csv が出力できる
- evaluation_summary.csv が出力できる

### F. AIバックエンド

- `AI_BACKEND=codex_app_server` でCodex app-serverに接続できる
- app-server経由で診断、学習ターン、学習フィードバック、再テスト/確認テスト採点を実行できる
- `AI_BACKEND=mock` はテスト時に完全に動く
- app-server未接続時は分かりやすいエラーを出す
- ChatGPT未ログイン時はログイン案内を出す
- AI出力schema validationに失敗したらai_call_logsに残る

## End-to-End Test Scenario

### proposed participant

1. Participant P001をproposedで作成
2. TransformerまたはAttentionでM1誤答
3. 事前学習または事後学習でM2/M3誤答
4. Diagnosis後、優先度上位4件がlearning targetになる
5. 学習ターン生成時のLはbackendのLearnerStateを正とする
6. 学習後retestで同じ誤概念ならrecurrence_flag true
7. 次のturnでstrategy_changed true
8. confirmation checkで正答ならl0_success true
10. evaluation_summaryに指標が反映される

### control participant

1. Participant P002をcontrolで作成
2. 同様のpretest誤答を入力
3. Diagnosisは保存される
4. 学習画面では一般解説のみ
5. teaching_strategyはgeneral_explanation
6. scaffolding_levelの動的変更は行われない

## Definition of Done

- `docker compose up --build` で起動
- `http://localhost:3000` が開く
- `http://localhost:8000/api/health` がok
- backend tests pass
- frontend tests pass
- E2E happy path pass
- CSV exports open in spreadsheet software
- READMEにCodex app-server起動、ChatGPT/Codexログイン確認、Mockテスト用途が書かれている