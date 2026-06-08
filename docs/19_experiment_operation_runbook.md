# 19. Experiment Operation Runbook

この文書は、実験実施時に研究者がどう操作するかを示す。実装時のUI・APIはこの運用に合わせる。

## Before Experiment

1. Docker Desktopを起動する
2. ホストで `codex app-server --listen ws://127.0.0.1:4500` を起動する
3. Codex/ChatGPTログイン状態を確認する
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
2. 診断待ち
3. 学習対象確認
4. 学習セッション
   - proposed: 前提用語理解、概念理解
   - control: 通常AI説明、自己説明確認
5. 即時再テスト
6. 事後アンケート
7. 終了

事前アンケート、L0確認、転移テストは現行運用では実施しない。

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
- AI出力schema validationに失敗した
- forbidden_help_given = true
- 前提用語計画が教材範囲から外れている
- 概念理解fail理由が明らかに不適切

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

## Data Export Checklist

必須CSV:

- participants.csv
- attempts.csv
- learner_states.csv
- learning_sessions.csv
- prerequisite_terms.csv
- term_understanding_attempts.csv
- concept_understanding_attempts.csv
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
- proposedの前提用語pass/failが含まれる

## Research Notes During Operation

研究者は以下を別途メモしてよい。

- 被験者が操作に詰まった箇所
- app-server失敗の有無
- 問題文の誤解
- 学習時間が極端に短いケース
- 回答が不自然に短いケース

ただし、個人情報はメモしない。
