# 現行API

## 設問1のみ出題（2026-11-03）

管理認証付きGET/PUT `/api/admin/first-question-only` で厳密booleanのenabledを取得・保存する。初期値OFF、新規登録時に参加者へ固定する。用語ページ回答APIは1問または2問を受理し、答え合わせも同じ設問数で返す。3問/6問の6仮説集計は分離し、混在時はstrataを返す。詳細は[48](48_first_question_only.md)。

## 教材用語解説モード（仕様版40）

新規参加者は登録時に`integrated_material`へ固定する。管理画面の切替UIと管理API `GET/PUT /api/admin/learning-material-glossary-mode`は提供しない。既存Participantの保存値は変更せず、参加者一覧・個別ログ・participants CSVで履歴を参照できる。RuntimeSettingの旧モード列はDB互換性のため残すが、登録・管理APIでは参照しない。

教材生成応答は`show_material_glossary`を返す。`false`は教材内解説モードであることを示し、Frontendは教材用GlossarySidebarのみ隠す。既存の`glossary` snapshotは返却・保存を継続し、回答後解説の注釈APIは変更しない。教材内解説モードの教材生成入力には両群共通の任意項目`glossary_reference`を含める。辞書は共通回答履歴ではなく、診断情報とも独立する。

## 仕様版28のペア答え合わせAPI（現行版29で維持）

GET/PUT /api/admin/question-review-display は管理認証下で、{ enabled: true/false, applies_to: "new_standard_participants_only" }を扱う。enabledは厳密なbooleanとする。既定値はtrueとし、参加者登録時に通常版だけへ固定する。

既存のpretest/retest/final-test取得APIは、設定ON・仕様版28・通常版において、同じ用語の設問1・2がともに保存済みで未確認の場合だけpending_question_reviewを返す。結果にはphase、term_slug、term_label、各設問番号、選択済み選択肢のlabel/body、is_correctだけを含め、正答キー・未選択肢・解説・診断情報を含めない。単一設問だけの回答では返さない。

POST /api/participants/{id}/question-review-acknowledgements はphaseとterm_slugを受け取り、確認時刻を設問2のAttemptへ保存する。確認済みの再送は冪等とし、不完全なペアや現在表示中ではないペアは拒否する。採点APIは未確認ペアがある状態での進行を拒否する。詳細と受入条件は[40](40_question_pair_answer_review.md)。

## テスト結果表示設定（issue-204・issue-233）

管理画面の表示名は「テスト結果の表示」。互換性のためGET/PUT `/api/admin/pretest-result-display`のURL・厳密なbooleanの`enabled`・`applies_to=new_participants_only`は維持する。RuntimeSettingの設定値を新規参加者の`show_pretest_results`と`show_retest_results`へ登録時snapshotする。既存行には補完せず、NULLは表示ありと解釈する。既存参加者の事前結果設定は不変で、既存参加者の`show_retest_results=NULL`も表示ありとなる。

設定はPRETEST、RETEST 1/2、内部`final_test`の全体結果確認に適用する。採点APIは`review_required`と遷移先`next_url`を返し、表示ONなら結果確認画面、OFFなら学習・次テスト・アンケートへ進む。採点結果と正誤判定は維持する。学習対象APIは表示OFF時に現在のテスト結果配列を空にし、現在位置API・直接URL・再開でも同じ遷移を適用する。古い冪等応答に`review_required`がない場合、FrontendはRETEST/final_testでは従来どおり結果確認へ進む。

診断応答にはlearning_target_slugsも含め、結果画面を通らない経路でも学習進捗用の一覧を保存できるようにする。非表示でlearning_targets状態なのに学習対象が空の場合は503（learning_navigation_unavailable）とし、同じ画面のURLを返したり、GETで進行状態を修復したりしない。

## 教材・解説・テストの用語注釈（仕様版26）

教材・回答後解説に加え、GET /api/experiment/{id}/pretest、/retest、/final-testの各questions項目へ`glossary: {version, entries: [{id, term, definition}]}`を返す。テストは用語見出し・問題文・全選択肢から抽出し、選択・正誤・診断を使わない。未回答GETはDBへ保存せず、回答時に同じ不変辞書からAttempt.glossary_snapshotへ保存する。回答済みの再取得・再送は保存値を使い、欠落は後付けしない。該当語なしは空配列、snapshot欠落時はnull。指紋・出典・正答・分類情報は公開しない。新規ルート・管理設定は追加せず、nullable JSON列を1つ追加する。AI入力・共通履歴には含めない。[保存仕様](24_learning_glossary.md)。

## 2026-10-21 同意・分離対応表

- POST /api/registrations（互換URL /api/participants）: assignment_code、consent_checked、student_numberを受け取る。学籍番号は必須・trim後1〜64文字・改行/制御文字不可。同意なしは400、不正な型は識別情報を返さない422。研究DBには学籍番号もそのハッシュも保存しない。Idempotency-Keyの再送は登録結果だけを返し、削除済み対応表を再作成しない。
- GET /api/admin/identity-mappings: アプリ内の対応表を返す。
- GET /api/admin/identity-mappings.csv: BOM付きUTF-8 CSVを返す。数式開始文字は無害化し、ファイル名には識別情報を含めない。
- DELETE /api/admin/identity-mappings/{participant_id}、DELETE /api/admin/identity-mappings: 対応表の個別/全件削除。研究データは残す。
- DELETE /api/admin/participants/{participant_id}: 現行プロトコルの研究DB内の関連データとアプリ内の対応表を削除する。旧データの409を維持する。ダウンロード済みファイル・USB・バックアップ・Codex側の保持データは削除対象外。

登録・全管理APIの応答はCache-Control: no-store。POST /api/admin/auth/loginはpasswordを受け、backendで照合する（既定abc、ADMIN_PASSWORDで変更）。POST /api/admin/auth/logoutはセッションを失効させる。ログイン時の入力エラーでは受信パスワードを返さない。管理API全体・POST /api/seed・管理用の評価再計算は有効なHttpOnly/SameSite=Strict Cookieがなければ401。管理書込みはOriginがある場合に設定済みfrontend・既存のhttp://127.0.0.1:3000・API自身のいずれにも一致しなければ403。HTTPSではSecureを付ける。セッションは単一backendプロセス内に30分保持し、再起動でも失効する。ChatGPT/Codexログインとは別の認証であり、研究DB・実験版・回答状態は変更しない。

削除済み登録キーの再送判定は、削除監査のregistration_keys配列をDB側で完全一致検索する。SQLiteはjson_each、PostgreSQLはjson_array_elements_textとEXISTSを使用し、監査JSONの全件取得・Pythonでの線形探索を行わない。参加者削除では、研究DBの削除と対応表削除待ち状態を同時にcommitし、その後に対応表を削除して監査状態を完了へ更新する。対応表削除に失敗しても研究DBの削除は巻き戻さず、監査のpendingを起動時または同じDELETE APIの再試行時に回復する。研究DBのcommitに失敗した場合は対応表に触れない。別DB間の分散トランザクションを保証するのではなく、研究DB内の削除outboxで片側だけの処理を再試行可能にする。

## 計画書対応の範囲

現行APIは[承認済み実装判断](20_experiment_plan_alignment.md)に沿う。現行コードでは仕様版40 / `experiment-plan-2026-11-07-learning-material-target-800-v1`で進行可否を判定する。仕様版39以下は閲覧専用とする。教材本文の目標文字数変更による公開API構造の変更はない。旧仕様の教材文字数契約は[42](42_learning_glossary_material_length.md)、教材モードは[41](41_learning_glossary_material_mode.md)、RAG注釈は[49](49_rag_glossary.md)を参照する。

事前アンケートはGET/POST `/api/participants/{id}/presurvey`を使い、`presurvey-baseline-v2`の厳密なpayloadを受け付ける。`prior_term_knowledge`の6項目は`unknown`、`heard_of`、`knows_meaning`、`can_explain`のいずれかを必須とし、AI利用頻度・自己評価も1〜10整数で必須とする。`phase=presurvey`のParticipantSurveyとして冪等に保存する。登録後の`current_step=presurvey`中はテスト出題・採点を拒否し、保存後にpretestへ進める。仕様版36の`presurvey-baseline-v1`回答はBoolean形式のまま履歴保全し、新形式へ変換しない。

事後SurveyPayloadはservices/research_protocol.pyで定義する。新規送信`posttest-10point-v3`はgeneral_ratings（system_usability/system_clarityの1〜10整数）、material_ratings（clarity/readability/japanese_clarity/difficulty_appropriateness/learning_usefulness/amount_appropriatenessの1〜10整数）、任意free_commentを受け付ける。material_ratingsは未表示者のみnull、表示者は6項目必須。余分なキー・旧フォームを新規送信として拒否する。free_commentは省略・null・空文字を許可し、文字列の前後空白を除去する。posttest v1/v2の保存済み回答は変換せず保持する。仮説5はphase=posttestだけを集計し、presurvey値を混ぜない。

GET /api/participants/{id}/surveyはアンケート版・表示判定・教材評価の必須/対象外を返す。POST /api/tutor-turns/{id}/material-viewは初回表示時刻を冪等に記録し、未利用の先行生成は拒否する。管理集計のhypothesesおよび/export/hypothesis_metrics.csv、/export/hypothesis_group_summary.csvは6仮説の専用指標である。

## 利用可能な現行契約

正本は `backend/app/main.py`。回答可能フェーズはpretest/retest/final_testだけ。廃止した追加確認の専用URL/APIは404。

| 用途 | API |
| --- | --- |
| 新規開始 | POST `/api/participants` |
| 再開判定 | GET `/api/participants/{id}/current-step` |
| 出題 | GET `/api/experiment/{id}/pretest`, `/retest`, `/final-test` |
| 回答保存 | POST `/api/attempts` |
| 通常版の用語ページ回答保存（issue-208） | POST `/api/attempts/term-page` |
| 事前固定採点 | POST `/api/participants/{id}/diagnose-pretest` |
| 結果・学習対象 | GET `/api/participants/{id}/learning-targets` |
| 学習開始 | POST `/api/tutor-sessions` |
| 教材・固定問題 | POST `/api/tutor-sessions/{id}/turns` |
| 回答・解説 | POST `/api/tutor-turns/{id}/respond` |
| テスト採点 | POST `/api/participants/{id}/score-retest`, `/score-final-test` |
| 中断 | POST `/api/participants/{id}/give-up-learning`, `/give-up` |
| 事前アンケート | GET/POST `/api/participants/{id}/presurvey` |
| 事後アンケート対象判定・送信 | GET/POST `/api/participants/{id}/survey` |
| 教材表示記録 | POST `/api/tutor-turns/{id}/material-view` |
| 6仮説の群別集計 | GET `/api/admin/evaluation-summary` のhypotheses |
| 6仮説CSV / Excel | GET `/api/admin/export/hypothesis_metrics.csv`, `/hypothesis_group_summary.csv`, `/hypothesis_metrics.xlsx`, `/hypothesis_group_summary.xlsx` |
| AI設定状態 | GET `/api/admin/ai/status` |
| 推論レベル設定 | POST `/api/admin/ai/reasoning-effort` (`reasoning_effort`: `low`, `medium`, `high`) |
| AIモデル設定 | POST `/api/admin/ai/model` (`model`: `gpt-6.1-sol` または `gpt-6-luna`) |
| 選択肢配置設定の取得 | GET `/api/admin/option-order` |
| 選択肢配置設定の更新 | PUT `/api/admin/option-order` (`mode`: `debug_fixed` または `randomized`) |
| 管理者ログ | GET `/api/admin/participants/{id}/logs`, `/logs.csv`, `/logs_excel.csv`, `/logs.xlsx`; 全体ログは `/api/admin/logs/overview.csv`, `/overview_excel.csv`, `/overview.xlsx` |
| 評価再計算 | POST `/api/participants/{id}/evaluation-summary/recalculate` |

`GET /api/participants/{id}/current-step` は既存の `step`、`next_url`、`can_resume` を維持し、新規参加者向けに `progress` を追加する。進捗は現在の保存済み状態と採点済みテスト回数から読み取り専用で算出し、DB列追加や評価再計算は行わない。

```json
{
  "step": "learning_targets",
  "next_url": "/learning-targets",
  "can_resume": true,
  "progress": {
    "stage_id": "post_pretest_1",
    "label": "再テスト1までの学習・再テスト1",
    "percent": 25
  }
}
```

割合は、事前テスト・採点中0％、事前後1回目までの学習/再テスト1が25％、事前後2回目までの学習/再テスト2が50％、アンケート75％、アンケート保存後の終了画面100％とする。初回満点で学習を省略する場合も、内部 `final_test` を再テスト1として数える。満点による早期終了、未達上限、ギブアップのいずれもアンケートは75％、終了は100％であり、100％は手続き完了を示して成績とは区別する。

`progress` は `{stage_id, label, percent}` または `null`。旧試用・未対応状態では `progress: null` とする。未知・整合しない状態も推測値を返さずnullとし、取得は回答・採点・状態を変更しない。

回答は `selected_option_ids` と時刻情報（response_time_sec、question_shown_at、answered_at）。テストはparticipant_id/question_id/phaseも指定する。廃止入力項目は422。

事前・再テスト・内部final_testの取得APIは`test_page_mode`を返す。新規参加者は`per_term`で同一用語の設問1・2を一括保存する。`POST /api/attempts/term-page`はparticipant_id、phase、term_slug、test_round、page_id、各設問のquestion_idと選択肢1件、共通表示/回答時刻、正のelapsed_time_secを受け、`Idempotency-Key`を必須とする。現在の2問であること、同じ用語・回次であることを検証し、同一トランザクションで確定する。既存回答は変更せず、異なる回答との競合は409。応答に正答・正誤・分類情報を含めない。従来の`POST /api/attempts`は旧記録の互換読出しに残す。

用語ページ時間は`Attempt.test_page_timing_json`（nullable JSON）へpage_id、`measurement_version=term_page_v1`、elapsed_time_secを記録し、新形式の設問別`response_time_sec`はNULLとする。2問には同じpage_id・時間を保存し、合計時間ではpage_idを一度だけ数える。従来記録は設問ごとのresponse_time_secで計算する。統合ログCSVの列は増やさず、JSON値・summary・表示単位フィールドで区別する。詳細は[設問分割仕様](39_split_assessment.md#テスト画面と時間計測issue-208)。

NULL・版1〜25・未対応版・旧protocol_idは、本文検証・冪等再送・先行生成より前に409 legacy_experiment_read_only。current-stepは保存状態を変えずstep=legacy_read_only/can_resume=falseを返す。新規版26＋現行protocol_idのみcan_resume=true。

参加者の出題APIに正答や分類メタデータを公開しない。回答後の結果確認では問題・選択内容・正誤を返す。Idempotency-Keyの再送、回答済みロックは維持する。旧試用の管理者閲覧・CSVは許可し、再計算は拒否する。

`POST /api/participants/{id}/score-retest`とscore-final-test、GET learning-targets、管理者一覧/ログはpost_pretest_tests_completedとpost_pretest_test_limitを返す。現行版の上限は2で、旧版は両値null。retest_cycles_completedは学習後retestだけの既存カウンターを維持し、共通回数は採点済みfinal_testの有無を加えて導出する。未回答を含むバッチも1回、全問未回答は400、冪等再送は加算しない。満点または事前後2回目未達でsurveyへ進む。retest_cycle_limit_reachedは上限時かつ未達の場合trueで、未達対象を保持する。問題取得・回答では現在の全体回次に合うvariantのみ認め、前後回次の問題IDは409、必要なvariant欠落は503とする。

選択肢配置はRuntimeSettingの単一行で管理する。未設定時は `debug_fixed`。管理APIのPUTで設定を保存し、GETは現在値と `applies_to=new_participants_only` を返す。新規参加者には開始時のモードを保存し、既存参加者のnull値は `debug_fixed` として扱う。`randomized` は「わからない」を最後のJに固定し、残る9択をA〜Iへ固定・均衡配置する。同一問題は群や参加者をまたいで同じラベル・順序となる。採点は表示ラベルではなく選択肢IDと内部メタデータで行う。画面向け選択肢に追加する `exclusive` は「わからない」の単独選択を扱うための情報で、正誤やM1/M3分類は含まない。

ランダム配置の学習問題で送る `option_id` は、表示済みのTutorTurnスナップショットに保存するランダムIDであり、元の選択肢ラベルや判定役割を符号化しない。回答時はそのスナップショットを内部選択肢へ照合する。設問再取得・送信再試行では保存済みTutorTurnを返すため、同じ表示に対するIDは維持される。問題の表示ラベルと順序自体は問題バンクから決定論的に生成する。

## 廃止された問題版フィルター

AIモデル・推論レベル設定はDBへ保存しないbackendプロセス内の一時設定であり、両群・進行中参加者にも次のAI呼び出しから適用する。状態/更新応答は有効値と選択肢を返す。モデル選択はcodex_app_serverでのみ適用でき、Mockでは409で拒否する。実際に使ったモデル・推論レベルと標準条件への一致はAI監査JSONに残る。環境変数の明示値は既定値より優先し、backend再起動後に管理上書きは消える。

`/api/admin/question-set`は廃止し、GET/PUTとも404を返す。集計・ログ一覧・仮説CSV/Excelに`question_set_mode`を含む旧フィルターを指定した要求は422で拒否する。管理画面と新規Participantは通常版固定であり、版別の応答項目・集計切替は提供しない。旧モード列と専用問題資産は保守用削除処理の対象とし、通常版の保存snapshotと履歴バンクは維持する。
