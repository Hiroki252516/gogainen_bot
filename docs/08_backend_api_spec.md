# Backend API Spec

## Question Payload

新規seedの対象は `llm_knowledge`、`multi_agent`、`memory_process` の3用語である。pretest、retest、final_test、l0_checkの固定問題はYAMLから読み込む。

```json
{
  "question_id": "uuid",
  "term_slug": "llm_knowledge",
  "term_label": "LLMに知識を与える方法",
  "question_type": "multi_select",
  "selection_mode": "multiple",
  "min_selections": 3,
  "max_selections": 3,
  "requires_reason": false,
  "test_round": "test",
  "test_round_label": "テスト",
  "options": []
}
```

固定複数選択では`selected_option_ids: string[]`を正本とし、既存互換の`selected_option_id`も残す。A〜Iから3件ちょうど、またはJのみ1件を必須とする。JとA〜Iの混在は不可とする。自由記述の互換フェーズでは`free_text_answer`を使用する。

## Participant Creation

`POST /api/participants` は同意済みの参加者を作成する。参加者が群名を選択・送信することはできず、管理者から伝えられたA/Bコードを送信する。

Request:

```json
{
  "assignment_code": "A",
  "consent_checked": true
}
```

`assignment_code`は前後の空白を除去して大文字化し、`A`を内部の`group_condition=proposed`、`B`を`group_condition=control`へ変換する。正常作成時の`assignment_method`は`admin_code`である。コードがない、またはA/B以外の場合は400を返す。同意がない場合も400を返す。旧来の`group_condition`や`assignment_method`を参加者作成入力として利用せず、既存DB行の値だけを互換目的で保持する。

Response:

```json
{
  "participant_id": "uuid",
  "display_code": "P001",
  "current_step": "pretest"
}
```

参加者向けレスポンスには内部の`group_condition`を含めない。群別の値は管理API、ログ、評価集計でのみ扱う。

参加者作成中にDB接続障害が発生した場合は、Idempotency-Keyの有無にかかわらず`503`と「データベースに接続できません。管理者に確認してください。」を返す。キー付きリクエストで保存処理に到達しなかった場合、DB復旧後に同じキー・同じ本文を再送でき、参加者を二重作成しない。

## Variant policy

- pretest: 用語ごとに `pretest_v1`
- retest: `retest_v1`〜`retest_v4`。5回目以降はv4を再利用
- learning: stage・用語ごとにv1〜v5。6回目以降はv5を再利用
- final_test: 用語ごとに `final_test_v1`

seed済みのテスト問題は`questions.variant_key`に保存し、学習確認問題は同等の`variant_key`を`tutor_turns.practice_question_json`に保存する。後者は学習確認問題の公開レスポンスに独立フィールドとして返さない。

初回教材のレスポンス後に作る先行生成は、現在より後の未達用語についてだけ実行し、先行生成分のvariantは常に各用語のv1とする。これは通常の学習variant policyを変更するものではなく、後続用語の最初の確認問題を先に作るための内部予約である。

再テストの採点対象が現行の3用語を各1問ずつ含み、すべて正解だった場合は、`score-retest`が`next_step=survey`、`next_url=/survey`を返して追加の確認を省略する。不正解または未回答がある場合は、`next_step=learning_targets`、不正解・未回答用語をテストの出題順に入れた`learning_target_slugs`、最初の用語への`next_url=/learning/{term_slug}`を返す。診断の`priority_score`は分析用に保存するが、参加者向けの学習対象の表示・遷移順には使わない。`final_test`も全問正解時だけ`survey`へ進み、不正解または未回答時は`learning_targets`へ戻り、最初の学習URLを返す。次の学習・再テスト周回はクライアントまたは研究者が再導線を開始し、backendが自動反復しない。対象一覧が空の異常時も`next_url=/learning-targets`に留める。各APIは`current_step`に応じてアクセスを制限し、満点で`survey`へ進んだ後は再テスト・学習操作を`409`で拒否する。不正解・未回答で`learning_targets`へ戻った場合は対象学習と次の再テストを利用でき、`final_test`は`current_step=final_test`の場合だけ利用できる。`final_test`の参加者向け表示名は「再テスト1」である。

`attempts.test_round` には初回 `pretest` を `test`、最初の学習後確認を `retest_1`、次周回を `retest_2` のように保存する。`attempts.phase` は `pretest`、`retest`、`l0_check`、`final_test` の内部値として互換維持する。

学習回答が十分と判定された場合は、その`TermAssignment.is_learning_target`を`false`に更新する。1用語で3回不正解になった場合は学習対象を未達のまま残して現在の用語セッションを終了し、次のテスト出題順の学習対象へ進める。残りの学習対象があれば`current_step=learning_targets`と次の用語への`next_url`、すべての対象を処理した場合は`current_step=retest`と`next_url=/retest`を、学習回答・学習状態・AIログと同じトランザクションで確定する。回答レスポンスには`attempts_used`、`remaining_attempts`、`session_ended_by_attempt_limit`を含める。`learning_targets`中にない用語の学習セッション開始は409で拒否し、旧互換として`current_step=final_test`からの直接呼び出しだけは既存APIの動作を維持する。

## Idempotency-Key

参加者向けの状態変更POSTでは、フロントエンドが`Idempotency-Key`ヘッダーを送る。API側ではヘッダーを任意とし、旧クライアントとの互換性を維持する。キーは1つの論理操作にだけ使い、通信失敗やレスポンス欠落時の再送では同じキーと同じ本文を使う。学習ターン生成では初回生成と各ターン後の次ターン生成に別キーを発行し、戻る操作後の再開でも前のターンの結果を誤って再利用しない。

対象は参加者作成、回答保存、事前テスト診断、学習セッション・ターン生成・学習回答、再テスト/L0/最終テスト採点、アンケート、学習ギブアップ、実験ギブアップである。GET、seed、管理者APIは対象外とする。

- 同一スコープ・同一キー・同一本文: 保存済みのレスポンスを返し、業務処理・AI呼び出し・監査イベントを再実行しない
- 同一スコープ・同一キー・別本文: `409`、`detail.error_code=idempotency_key_conflict`
- 同じ操作を処理中: `409`、`detail.error_code=idempotency_in_progress`
- 現在の問題に未採点の回答がすでにある: `409`、`detail.error_code=answer_already_submitted`。元の回答は変更せず、追加の`attempts`を作らない

`GET /api/experiment/{participant_id}/pretest|retest|l0-check|final-test`の各問題には`answer_status`（`unanswered`または`submitted`）を含める。`submitted`の問題には本人が送信した`submitted_answer`（選択した`option_id`、理由・自由記述）も含め、画面で選択済み状態を復元する。`submitted`の問題は回答変更不可として扱う。再テストで過去周回の回答が採点済みになった後の新しい周回は、新しい問題インスタンスとして回答できる。

`GET /api/participants/{participant_id}/current-step`は、ブラウザの戻る操作で古い画面が表示されたときの正規遷移確認にも使う。GET自体はデータを変更しない。参加者の現在フェーズと異なる画面からの状態変更POSTは、処理を行わず409を返し、既存の回答・学習状態・監査ログを変更しない。

現行の主なAPIルートは `/api/health`、`/api/seed`、`/api/participants`、`/api/participants/{participant_id}/current-step`、`/api/experiment/{participant_id}/pretest|retest|l0-check|final-test`、`/api/attempts`、`/api/participants/{participant_id}/diagnose-pretest`、`/api/participants/{participant_id}/learning-targets`、`/api/participants/{participant_id}/survey`、`/api/tutor-sessions`、`/api/tutor-sessions/{session_id}/turns`、`/api/tutor-turns/{turn_id}/respond`、`/api/participants/{participant_id}/score-retest`、`/api/participants/{participant_id}/score-l0-check`、`/api/participants/{participant_id}/score-final-test`、`/api/participants/{participant_id}/give-up-learning`、`/api/participants/{participant_id}/give-up`、`/api/participants/{participant_id}/evaluation-summary/recalculate`、`/api/admin/*` である。参加者作成は`consent_checked=true`を必須とし、同意画面から実行する。参加者向け状態変更POSTの再送は`Idempotency-Key`で保護し、キー競合の409は参加者の終了や実験中断を意味しない。`give-up-learning`は現在の学習セッションを回答なしで終了して`next_step=retest`、`next_url=/retest`を返す。`give-up`は、`current_step=retest`または`final_test`の場合は`next_step=survey`、`next_url=/survey`を返し、学習対象確認中などそれ以外の実験ギブアップ対象では`next_step=finish`、`next_url=/finish`を返す。いずれも`completed_at`と`completion_reason=give_up`を記録し、survey送信後は`current_step=finish`へ進むが、ギブアップ時の`completed_at`と`completion_reason`は保持する。retestまたはfinal_testのギブアップ後は問題取得、回答保存、採点、学習セッション操作を409で拒否し、surveyだけを受け付ける。両操作は`audit_events`へ`give_up_learning`または`give_up_experiment`として記録する。`survey`は`current_step=survey`の参加者だけが送信でき、`participant_surveys`へ仮フォームの回答を保存して`current_step=finish`へ進める。通常完了時は`completion_reason=completed`とし、retestまたはfinal_testギブアップ後は`completion_reason=give_up`を維持する。管理画面から `DELETE /api/admin/participants/{participant_id}` を呼ぶと、対象参加者が所有する関連実験データとIdempotencyレコードを削除し、削除操作の監査記録を残す。seedデータは削除しない。frontendの `/api/*` はNext.jsのrewriteでbackendへ転送する。

管理用の参加者情報には`completion_reason`、`give_up_learning_count`、`give_up_experiment_count`を含める。個別ログの`participant`にも同じ状態を返し、`audit_events`には操作種別・実行時刻・状態変更前後を含める。全体ログの`recent_audit_events`と参加者ログCSVにもギブアップ操作を含める。

参加者ログAPIの`ai_call_logs`は、AI入力の`request_payload`、backendが利用した`response_payload`、取得可能な場合の`raw_text`を返す。Codex app-serverでは`request_payload.effective_request`に実際の`thread/start`と`turn/start`設定、全文prompt、JSON Schema、モデル・推論レベル、prompt/taxonomy版、Schema SHA-256、RAG query・section・chunk ID・本文SHA-256、生成試行番号、送信段階を含む。認証情報は保存しない。Codex実送信がないMock呼び出しには`effective_request`を付けない。`raw_text`は補正前の生JSON文字列、`response_payload`はJSON解析後に内部ラベル除去や教材契約補正を行った結果であり、教材生成では本文長・段落数・箇条書き数も含む。全文promptには学習者の回答や履歴が含まれる場合があるため、ログAPI・CSVは研究者限定で扱う。CSVではpayloadを既存の`value_json`へ含め、固定列は変更しない。

`GET /api/participants/{participant_id}/learning-targets` は、`current_step`、既存の未達対象一覧、事前テスト後の互換用 `pretest_results`、直近のテスト結果 `test_results` を返す。`pretest_results` は3用語を表示順に含み、`term_slug`、`term_label`、`is_correct`、`result_label`、`result_summary`、`is_learning_target` を持つ。`test_results` は `test_round`、`test_round_label`、`results` を持ち、各結果に `term_slug`、`term_label`、`question_body`、`selected_options`（`label` と `body` のみ）、`is_correct`、`result_label`、`is_learning_target` を含める。`test_results` は保存済みの問題文・選択内容・正誤を参加者向けに投影したものであり、`correct_answer`、`expected_answer`、選択肢ごとの `is_correct`、M分類などの内部診断値は含めない。結果は保存済み `Attempt.is_correct` を正本とする。`targets` はテストの出題順で並び、学習開始先を決める未達用語の一覧として維持する。`priority_score`は分析用の保存値であり、参加者向けの並び順には使わない。`current_step=learning_targets` のとき、対象が空でも最終テストへの導線を返さない。

## Scoring

A/B/Cの3つだけを選択した場合だけ正解。不正解分類はM3を最優先し、次にM1、J単独または判定材料なしはunknownとする。採点・遷移はbackendが決定し、AI出力で上書きしない。

## Learning API

参加者向けの学習結果・表示では `learning_stage` として `enrichment`、`conceptual_change`、`final_feedback` を使う。新しい学習ターンの教材生成で受け付けるstageは `enrichment` と `conceptual_change` であり、`final_feedback` は確認問題に十分回答した後の結果表示状態で、新しい教材生成の入力にはしない。L3/L2は内部の`scaffolding_level`互換ログである。教材生成では両群に用語・共通構成要素・同一条件のRAG本文だけを共有し、固定確認問題・選択肢・正答はYAML/backendの責務としてAIへ渡さない。`control`には学習段階・診断・履歴を渡さず、`proposed`だけが診断target・taxonomy・足場掛け情報を追加で受け取る。参加者IDと群名はルーティング・ログ照合専用で、モデルpromptから除く。

学習ターン回答APIのレスポンスには `item_results` フィールドを残すが、現行の固定複数選択フローでは空配列になる。個別項目結果を返す自由回答フローは将来または互換用である。

### 学習教材の先行生成（内部動作）

`POST /api/tutor-sessions` と `POST /api/tutor-sessions/{id}/turns` の公開レスポンス形式は変更しない。初回turnの保存後、backendが後続の未達用語の`TutorSession`を待機状態で作り、同じ教材契約、必須教授要素検証、RAG条件、control/proposed入力分離を使ってv1教材を生成する。次の用語でturn生成APIを呼ぶと、`ready`の未回答turnを新規AI呼び出しなしで返す。

参加者が先にその用語へ進み、状態が`pending`または`generating`の場合は、待機結果を破棄して通常の同期生成を行う。先行AIの失敗は参加者向けエラーにせず、`AICallLog`と`failed`状態に残して通常生成へフォールバックする。ギブアップ、実験終了、再テスト後の新しい学習周回では未使用の先行生成を破棄する。参加者画面には先行生成状態、M分類、RAG、内部方略を表示しない。

先行生成の内部キーは`prefetch_tutor_turn:{session_id}`と`initial-v1`で重複生成を防ぐ。アプリ再起動で`pending`または`generating`が残っても、後続用語への到達時に同期生成へ切り替えるため、耐久キューへの依存や新しい公開APIはない。
