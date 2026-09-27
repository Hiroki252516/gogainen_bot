# 19. Experiment Operation Runbook

この文書は、現行MVPで実験実施時に研究者がどう操作するかを示す。未実装の研究拡張は各節で「将来対応」と明記する。

## Before Experiment

1. Docker Desktopを起動する
2. ルート`.env`を設定し、`scripts/start-codex-app-server.sh`または`.ps1`でCodex app-serverを起動する
3. `codex` または管理画面のログイン導線でChatGPT/Codexログインを確認する
4. `docker compose up --build` を実行する
5. `learning_content.yml` を検証してseed questionsがbackend起動時に自動投入される
6. `/admin` でAI backendが `codex_app_server` かつログイン済みであることを確認する（AI status APIは `/api/admin/ai/status`）
7. テスト・切り分け以外では `AI_BACKEND=mock` を使わない

Dockerの再ビルド・再起動では、ブラウザの`localStorage`に保存された参加者IDは消えない。そのため、未完了の実験がある場合は現在位置から再開する。新しい実験を始める場合は、終了画面の「新しい実験を開始」を押してブラウザの参加者情報を消去する。管理画面から参加者を削除した場合も、同じブラウザの参加者情報は自動的に消去される。

## Participant Setup

1. `/start` を開く
2. 研究計画に従って管理者がAまたはBを割り当て、対応する参加コードを被験者へ伝える（Aは内部`proposed`、Bは内部`control`）
3. 被験者が参加コードを入力して「同意書を確認する」を押す
4. `/consent`で仮同意書を確認し、同意チェックを入れる
5. 「同意してテストを開始」を押す。backendが参加コードを検証して参加者を作成する
6. 表示された `display_code` を研究者が控える
7. 被験者に個人情報や群名を入力させない

## During Experiment

被験者の流れ:

1. 同意後にテスト
2. 診断待ち
3. 学習対象確認
4. 学習セッション（1用語につき3回まで不正解を記録し、3回目の不正解後は次のテスト出題順の学習対象へ進む）
5. 再テストAPIで現在の再テストを実施
6. 3用語を各1問ずつ採点して全問正解なら追加の確認を省略し、アンケート画面へ進む
7. 1問でも不正解または未回答なら、返された学習対象順に追加学習を再開（backendの自動ループはない）
8. 追加学習後に再テストへ戻る
9. 再テスト満点でない限り、`learning_targets`へ戻った対象を再学習し、クライアントまたは研究者が次の再テスト周回を開始する（自動遷移はない）
10. 初回テストで学習対象がない場合も、内部 `final_test` を「再テスト1」として表示する
11. 仮アンケートを送信する
12. 終了

初回学習教材を返した後は、backendが現在より後の未達用語のv1教材を裏で先行生成する。研究者や参加者が待機状態を操作する必要はなく、次の用語に到達した時点で完成済みなら同じturnを再利用する。先行生成中に到達した場合やAIが失敗した場合は、その用語だけ通常の同期生成へ切り替わる。教材生成が失敗しても参加者へ先行生成エラーを表示しない。

参加者が途中で中断する場合:

- 学習セッション中の「学習をギブアップして再テストへ」は、その学習セッションだけを終了し、未回答のまま再テストへ進める。
- 再テスト中または`final_test`（画面上は「再テスト1」）中の「実験をギブアップして終了」は、`survey`へ進み、アンケート送信後に`finish`を確定する。ギブアップ時に`completion_reason=give_up`と`completed_at`を記録し、アンケート送信後も保持する。以後の問題取得・回答・採点は409となる。
- 再テスト結果確認中または学習対象確認中の同操作は、従来どおり`finish`を確定して実験を終了する。以後の問題取得・回答・採点は409となる。
- 管理画面の参加者ログで`give_up_learning`または`give_up_experiment`の`AuditEvent`を確認し、中断操作と時刻を記録する。
- ギブアップ時は、後続用語に対して作成済みの未使用先行生成が`discarded`になり、`ended_at`が保存されていることを必要に応じて被験者ログで確認する。
- 参加者一覧の終了理由とギブアップ回数を確認し、必要に応じて参加者ログCSVまたは全体ログCSVにも記録された操作を確認する。
- 通信が切れた場合は画面を閉じず、同じ操作を再送する。backendがすでに保存済みなら同じ`Idempotency-Key`で保存済み結果が返り、回答やAI処理は重複しない。
- ブラウザの戻る操作で回答済み問題に戻った場合は、「回答済み・変更不可」を確認して「次の問題へ」で進む。選択肢を変更して再送しない。APIに到達した場合も`409`となり、元の回答が維持される。
- ブラウザの戻るボタンやマウスのサイドボタンで同意書、診断、再テスト結果、完了済み学習画面へ戻った場合は、画面が現在の正規フェーズへ自動的に戻るまで操作しない。これは現在位置を確認するGETであり、回答や実験状態を変更しない。409が表示されても実験終了ではないため、画面を閉じずに現在の正規画面で続行する。
- 回答済み問題へ戻った場合は、保存済みの選択肢が選択済みで表示され、入力は変更できない。「次の問題へ」で続行する。

現行MVPのテスト・再テスト対象は、LLMに知識を与える方法、マルチエージェント、記憶プロセスの3用語である。`attempts.test_round` に `test`、`retest_1`、`retest_2` 以降を保存する。`/survey` は仮フォームで、送信時に`participant_surveys`へ保存する。

問題はYAMLで管理される。テスト・再テスト1は各用語1問、再テスト2以降はv1〜v4（以後v4再利用）、学習確認はv1〜v5（以後v5再利用）である。LangGraphはRAG検索結果に含めない。

研究者が見るもの:

- `/admin` の進捗
- AI診断失敗
- AI call logの失敗・未接続状態。手動診断修正UIと修正内容のAuditEvent書き込みは将来対応
- app-server接続状態
- 教材生成を監査する場合は、被験者別ログの`ai_call_logs.request_payload.effective_request`で実送信prompt、Schema、モデル・推論レベル、prompt/taxonomy版、RAG chunk情報、送信状態を確認する。教材本文は700文字前後（600〜800文字）が共通範囲であり、文字数・段落数・箇条書き数、生成各試行の検証結果、最終試行回数も確認できる
- 先行生成を監査する場合は、`tutor_sessions.prefetch_state`の遷移、`tutor_turns.diagnosis_json.generation_origin/prefetch`、`AICallLog.request_payload.generation_audit`と`response_payload.prefetch_audit`を用語順に照合する。`ready`のまま未回答のturnは回答履歴・学習負担へ含めない。
- `failed`または`discarded`のセッションでも、参加者到達後に同期フォールバックのinteractive turnが保存されていれば実学習として継続中である。新周回・実験終了の未使用prefetch整理では、そのセッションを未使用教材として終了させない。
- controlの教材生成promptには用語・共通構成要素・共通RAGだけが含まれ、固定問題・選択肢・正答、参加者ID・群名、個人の回答・診断・学習段階・履歴は含まれない。正答要約・誤答解説では現在の問題・選択・表示済み教材・共通RAGのみを使う
- Codex監査prompt全文には学習者の回答・履歴が含まれる場合があるため、研究者限定で取り扱い、外部共有や参加者画面への表示を行わない

### 学習回答後の先行生成の確認

- 不正解かつ残り挑戦回数がある回答では、解説表示中に次教材生成が進む。画面には内部並行処理を表示しない。
- 被験者が「次の確認へ」を押したとき、先行生成済みなら待ち時間なく次教材へ進み、生成中なら`次の確認を準備中...`の進捗表示で待つ。
- 先行生成失敗は回答失敗ではない。次ターン取得が通常の同期生成へフォールバックしたことを、参加者ログの`generate_tutoring_turn`と`AICallLog`で確認する。
- 解説生成失敗は回答・学習状態を確定しないため、AI call logの失敗を確認してから同じ回答を再送する。Mockへ切り替えたログを本実験データへ混ぜない。
- 学習ギブアップまたはプロセス再起動後は先行生成が残らない場合がある。その場合は次ターン取得時の通常生成が正しい復旧経路であり、終了済みセッションへ新教材が保存されていないことを確認する。

## If AI Fails

### CodexAppServerBackend

1. `/admin` のAI statusを確認する（backend APIは `/api/admin/ai/status`）
2. app-serverが起動しているか確認
3. ChatGPTログイン状態を確認
4. token設定を確認
5. 失敗したAI call logを確認
6. 実験データを採る前に復旧する。Mockへ切り替えたデータは本実験データに混ぜない

### MockAIBackend

Mockは自動テスト・障害切り分け用であり、本実験運用では使わない。Mockで動作確認したログは本分析から除外する。

## Manual Review（将来対応）

以下の場合は管理者確認対象。

- AI診断信頼度が低い
- 選択肢と理由が矛盾する
- AI出力をJSONとして解析できなかった、またはapp-serverの契約エラーが出た
- forbidden_help_given = true

手動修正UIを将来追加する場合:

- 修正理由を入力する
- audit_eventsへ保存する
- 修正後にevaluation summaryを再計算する

## After Experiment

1. `/admin` で参加者の「完了」「中断」と終了理由を確認
2. 採点済みの事前テストがある参加者のevaluation summaryは画面表示時に自動計算される。必要な場合だけ再計算ボタンで強制更新する
   - 旧データの`finish`参加者は、ギブアップ監査ログに基づいて終了理由とサマリーの完了状態が起動時に補正される
   - 被験者別の学習段階は、誤概念・unknownの診断状態を優先して表示する
3. 管理画面で全体ログと被験者別ログを確認する
4. 被験者別ログの `回答履歴（テスト＋学習）` で、テスト回答と学習ターン回答の時刻・回答時間が連続して見えることを確認する
5. `evaluation_summaries` の `pretest_score`, `retest_score`, `l0_correct_rate`, 同種誤答再発率を確認する。用語別variant_keyも必要に応じて確認する
6. 必要に応じて全体ログCSVまたは被験者別ログCSVを出力する
7. exportsフォルダを研究分析用に保管する
8. 必要なら、管理画面の確認ダイアログから `DELETE /api/admin/participants/{participant_id}` で被験者データを削除する。削除前に`delete_participant`のAuditEventが残るが、seedデータとexport fileは削除されないため、DBバックアップと保存方針も確認する

`l0_correct_rate` は互換名であり、通常は `final_test` の正答率、なければ互換 `l0_check` の正答率として読む。両方がなく、再テスト満点で最終テストを省略した場合は再テスト満点を代用し、`final_score_source=retest_mastery` として判別する。得点率・誤概念・負担・条件統制の推移は現行 `evaluation_summaries` のJSONとCSVの `value_json` に保存される。自動周回のない参加者では存在するattemptsだけが集計対象になる。

## Delayed Retest Optional Operation（将来対応）

遅延再テストを行う場合:

1. 実験終了後、別日に同じ被験者コードで再開する
2. `delayed_retest` phaseの問題を出す
3. Q1/Q2/Q4の別バージョンを使う
4. 学習セッションやヒントは出さない
5. delayed_retest_scoreとdelayed recurrenceを別集計する

現行MVPには `delayed_retest` を開始するAPI/UIがない。別日再テストを導入する場合の運用案として残す。

## Data Export Checklist

主に使うCSV:

- overview.csv
- 被験者別ログCSV

確認:

- participant_idが全CSVで結合可能
- display_codeが含まれる
- group_conditionが含まれる
- term_slugが含まれる
- phaseが含まれる
- 回答行は `record_type=answer`、`source_type=test_attempt` または `source_type=learning_turn`
- `value_json` に詳細ログが含まれる
- Idempotency記録は参加者削除時に関連分を削除し、研究用CSVの回答行には混ぜない

既存のテーブル別CSV APIは互換用に残してよいが、管理画面の主導線では全体ログCSVと被験者別ログCSVを使う。

## Research Notes During Operation

研究者は以下を別途メモしてよい。

- 被験者が操作に詰まった箇所
- app-server失敗の有無
- 問題文の誤解
- 学習時間が極端に短いケース
- 回答が不自然に短いケース

ただし、個人情報はメモしない。
