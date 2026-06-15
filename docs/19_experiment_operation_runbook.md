# 19. Experiment Operation Runbook

この文書は、実験実施時に研究者がどう操作するかを示す。実装時のUI・APIはこの運用に合わせる。

## Before Experiment

1. Docker Desktopを起動する
2. ホストで `codex app-server --listen ws://127.0.0.1:4500` を起動する
3. `codex` または管理画面のログイン導線でChatGPT/Codexログインを確認する
4. `docker compose up --build` を実行する
5. seed questionsはbackend起動時に自動投入される
6. `/admin` でAI backendが `codex_app_server` かつログイン済みであることを確認する
7. テスト・切り分け以外では `AI_BACKEND=mock` を使わない

## Participant Setup

1. `/start` を開く
2. 同意チェックを入れる
3. group conditionをランダムまたは手動指定する
4. 表示された `display_code` を研究者が控える
5. 被験者に個人情報を入力させない

## During Experiment

被験者の流れ:

1. 事前テスト
3. 診断待ち
4. 学習対象確認
5. 学習セッション
6. 即時再テスト
7. 必要なら2回目以降の学習
8. 未達0件になったら最終テスト
9. アンケート遷移画面
10. 終了

現行MVPの事前テスト・最終テスト対象は、転移学習とLLMの学習段階の2用語である。`/survey` は暫定画面で、アンケート本体は次の実装で接続する。

研究者が見るもの:

- `/admin` の進捗
- AI診断失敗
- manual review
- app-server接続状態

## If AI Fails

### CodexAppServerBackend

1. `/admin/ai/status` を確認
2. app-serverが起動しているか確認
3. ChatGPTログイン状態を確認
4. token設定を確認
5. 失敗したAI call logを確認
6. 実験データを採る前に復旧する。Mockへ切り替えたデータは本実験データに混ぜない

### MockAIBackend

Mockは自動テスト・障害切り分け用であり、本実験運用では使わない。Mockで動作確認したログは本分析から除外する。

## Manual Review

以下の場合は管理者確認対象。

- AI診断信頼度が低い
- 選択肢と理由が矛盾する
- AI出力schema validationに失敗した
- forbidden_help_given = true

手動修正時:

- 修正理由を入力する
- audit_eventsへ保存する
- 修正後にevaluation summaryを再計算する

## After Experiment

1. `/admin` で参加者がcompletedになっているか確認
2. evaluation summaryを再計算する
3. CSVを出力する
4. exportsフォルダを研究分析用に保管する
5. 必要なら被験者データを削除する

## Delayed Retest Optional Operation

遅延再テストを行う場合:

1. 実験終了後、別日に同じ被験者コードで再開する
2. `delayed_retest` phaseの問題を出す
3. Q1/Q2/Q4の別バージョンを使う
4. 学習セッションやヒントは出さない
5. delayed_retest_scoreとdelayed recurrenceを別集計する

MVPでは必須ではない。

## Data Export Checklist

必須CSV:

- participants.csv
- attempts.csv
- learner_states.csv
- tutor_turns.csv
- recurrence_events.csv
- ai_call_logs.csv
- evaluation_summary.csv

確認:

- participant_idが全CSVで結合可能
- display_codeが含まれる
- group_conditionが含まれる
- term_slugが含まれる
- phaseが含まれる
- misconception_typeが含まれる
- recurrence_flagが含まれる
- l0_successが含まれる

現行のCSV出力は管理画面のボタンから、participants、attempts、learner_states、tutor_turns、recurrence_events、ai_call_logs、evaluation_summaryを取得できる。

## Research Notes During Operation

研究者は以下を別途メモしてよい。

- 被験者が操作に詰まった箇所
- app-server失敗の有無
- 問題文の誤解
- 学習時間が極端に短いケース
- 回答が不自然に短いケース

ただし、個人情報はメモしない。
