# 現行API

## 仕様版54の現行条件

新規参加者は仕様版54 / `experiment-plan-2026-11-12-four-topic-instruction-tuning-perfect-test-early-exit-posttest-material-amount-clarity-removal-v1`を使い、登録の`test_content_mode`は`four_topic_fundamentals`に固定する。仕様版53以下は保存済み問題・回答・snapshotを維持して閲覧専用とする。GET `/api/participants/{id}/presurvey`は4用語版`presurvey-four-topic-baseline-v4`と6件の`term_items`を返す。下位用語キーは`instruction_tuning`、表示名は「インストラクションチューニング」。理解度質問は「{用語}の基本的な意味や働きをどの程度理解していますか。」とし、見聞き経験質問文も現行版の文言を使う。POSTの保存構造と経験に応じた理解度検証は従来どおり。

POST `/api/registrations`（互換URL `/api/participants`）は`assignment_code`、`consent_checked`、`research_code`を受け取る。研究用コードは半角数字1〜64桁を厳密に検証するが、Participant作成・冪等性記録作成前に参照を終え、その後保持しない。request hashには研究用コードを含めず、レスポンスにも返さない。研究DB、別SQLite、アプリログ、CSV/XLSX、AI入力、ブラウザ永続領域には保存しない。研究用コードの一意性照合や対応表の管理APIはない。`student_number`は入力項目ではなく、余分なキーとして拒否する。研究者が研究用コード・学籍番号・参加者IDの対応表をアプリ外で管理する。

GET `/api/admin/test-content-mode`は新規参加者用の固定値`four_topic_fundamentals`を返す。PUTは同じ値だけを受け付け、他のモードは409で拒否する。登録時は4用語版をParticipantへsnapshotし、既存Participantのモードは変えない。管理画面に問題モード切替はない。識別対応表のGET/CSV/DELETE管理APIも現行では提供せず、旧routeは404となる。参加者削除APIに限り、明示的な削除の後処理として旧SQLiteに存在する当該参加者IDの行だけをcleanupする。必要な全設問を採点し全問正解した事前・再テスト1/2・内部`final_test`後は、結果表示snapshotに従ってsurveyへ遷移し、学習・後続テストを省略する。詳細は[データモデル](07_data_model.md)と[運用手順](19_experiment_operation_runbook.md)。

4用語版は現行問題バンク`split-actions-four-topic-v3`から出題する。仕様版51のissue336 protocolと仕様版52の4用語表記protocolはv3、仕様版51のissue338 protocolと仕様版52の早期終了・教材量protocolはv2を使う。仕様版50の各protocolと仕様版49以下は記録時のバンクを使用し、保存済み問題snapshotに従って復元する。問題内容の取得・採点・回答後確認のAPI契約、問題snapshot、役割構成は変わらない。詳細は[事前アンケート](49_presurvey_baseline.md)と[4用語版](51_four_topic_foundation_mode.md)。

現行事後アンケートGET `/api/participants/{id}/survey`は版`posttest-5point-v4`と教材閲覧状態を返し、POST同URLはシステム評価1項目、教材評価6項目、任意自由記述を受け付ける。システム評価は「必要な操作をスムーズに行えた」のみ。削除した`system_clarity`はv4の新規回答で余分なキーとして拒否する。教材量の設問は「教材の量はどの程度でしたか」。数値回答は厳密な整数1〜5、または各項目独立の`not_applicable`。教材閲覧者は6項目すべて回答し、未閲覧者は`material_ratings: null`を送る。仕様版51までのv3回答を含む旧版の保存済み回答は変換・上書きしない。

H5は4つの中核教材項目の有効な数値回答の参加者内平均とし、`not_applicable`は除外する。難易度・教材量はH5外の回答分布として集計する。ログ・アンケートCSV／Excelにはphase、survey_version、保存回答を保持する。詳細は[事後アンケート仕様](52_posttest_five_point_evaluation.md)と[評価指標](12_evaluation_metrics.md)。

## 仕様版48の条件（履歴）

仕様版48当時は管理認証付きGET/PUT `/api/admin/test-content-mode`で`application`、`basic_understanding`、`four_topic_fundamentals`を受け付けていた。RuntimeSettingの保存値を登録時にsnapshotし、未設定時は`four_topic_fundamentals`とした。参加者向け出題・採点API、4用語の3択またはunknown単独、Attemptと問題snapshot、モード別集計は維持された。protocolは`experiment-plan-2026-11-10-presurvey-exposure-understanding-split-v1`であり、この段落は仕様版48時点の履歴条件を示す。

事前採点APIと`score-retest`／`score-final-test`は、対象フェーズの必要な全設問が採点済みかつ全問正解の場合に`current_step=survey`を返す。`review_required`と`next_url`は各参加者の結果表示snapshotに従い、ONなら結果確認画面を経由してsurveyへ、OFFなら直接surveyへ遷移する。事前・再テスト1/2・内部`final_test`のいずれで満点となっても、学習対象は設定せず後続テストを開始できない。未達時は既存の`next_url`と学習対象を使う。現在位置API、結果表示、再読み込み、直接URLも保存済み状態を参照する。仕様版53以下は読み取り専用で、既存回答の再評価・書換えはしない。[画面フロー](09_frontend_ux_flow.md)、[指標](12_evaluation_metrics.md)。

## テスト問題モード（仕様版43導入時の履歴契約）

- `GET /api/admin/test-content-mode`: `{mode, label, applies_to: "new_participants_only"}`を返す。RuntimeSetting未保存時は`application`を返す。
- `PUT /api/admin/test-content-mode`: `{mode: "application" | "basic_understanding"}`のみ受け付け、DBへ保存する。未知キー・値は拒否する。
- 両endpointは既存の管理認証を適用する。設定は新規参加者の登録時だけ`Participant.test_content_mode`へ固定し、登録済み参加者へ遡及しない。
- 参加者向けの出題・採点API契約は変えず、保存済みParticipantのモードに対応するbank construct keyを選ぶ。問題本文や判定情報を追加公開しない。
- 管理ログ・参加者CSVにモードを含める。仮説集計と群サマリーはモードで分離する。

問題バンク・互換性は[50](50_basic_understanding_question_mode.md)。

## 仕様版42の固定設定（履歴）

新規登録はRuntimeSettingの旧表示設定を参照せず、結果表示false・設問ごとの答え合わせtrue・設問1のみ出題true・教材内解説モードをParticipantへ固定保存する。管理API `/api/admin/pretest-result-display`、`/api/admin/question-review-display`、`/api/admin/first-question-only`、`/api/admin/learning-material-glossary-mode` は提供しない。RuntimeSettingとParticipantの履歴値はparticipant log API・CSVに保持するが、管理画面の一覧・個別ログ表示からは除く。出題条件は現行の3問のみであり、集計の条件指定API/UIは設けない。仕様版41以下は閲覧専用。

## 設問1のみ出題APIの廃止（仕様版35で導入した履歴）

過去には管理認証付きGET/PUT `/api/admin/first-question-only` で条件を切り替えていた。仕様版40から当該APIを廃止した。現行仕様版54の新規参加者は4用語版を各1問（計4問）出題する。現行版・基礎理解版の各3問条件は過去参加者の記録復元用に保持する。旧参加者の記録復元には保存snapshotと版対応を使う。詳細は[48](48_first_question_only.md)・[50](50_basic_understanding_question_mode.md)・[51](51_four_topic_foundation_mode.md)。

## 教材用語解説モード（仕様版39導入・42現行）

新規参加者は登録時に`integrated_material`へ固定する。管理画面の切替UI・固定値表示と管理API `GET/PUT /api/admin/learning-material-glossary-mode`は提供しない。既存Participantの保存値は変更せず、participants CSVと管理ログAPIで履歴を参照できる。RuntimeSettingの旧モード列はDB互換性のため残すが、登録・管理APIでは参照しない。管理画面の参加者一覧・個別ログには表示しない。

教材生成応答は`show_material_glossary`を返す。`false`は教材内解説モードであることを示し、Frontendは教材用GlossarySidebarのみ隠す。既存の`glossary` snapshotは返却・保存を継続し、回答後解説の注釈APIは変更しない。教材内解説モードの教材生成入力には両群共通の任意項目`glossary_reference`を含める。辞書は共通回答履歴ではなく、診断情報とも独立する。

## 設問ごとの答え合わせAPI（現行仕様版54）

設定GET/PUT `/api/admin/question-review-display` は仕様版40で廃止した。現行仕様版54の新規参加者にも設問別確認を常に有効とし、問題モードに応じて回答済みの設問を確認する。これはテスト全体の結果画面とは別の確認である。事前テスト後の全体結果画面は`show_pretest_results` snapshotに従って表示し、事前満点者は確認後または非表示で事後アンケートへ進む。

回答保存後の各テスト取得APIは、現在ページの回答を保存した後に`pending_question_review`を返す。確認内容にはphase、term_slug、問題・設問番号、選択済み選択肢のlabel/body、設問全体のis_correctを含め、正答キー・未選択肢・解説・診断情報は含めない。4用語版では回答後確認に限り、選択済み選択肢へ個別の正誤を含める。未選択肢の正誤は公開しない。回答未保存の出題データには正誤を含めない。

POST /api/participants/{id}/question-review-acknowledgements はphaseとterm_slugを受け取り、確認時刻をその用語ページの最後の設問Attemptへ保存する。確認済みの再送は冪等とし、必要な回答がそろっていない用語や現在表示中ではない確認は拒否する。現行仕様版54は1用語ページ1問だが、旧記録の設問ペア契約も復元互換性のため維持する。詳細と受入条件は[40](40_question_pair_answer_review.md)。

## テスト結果表示（issue-204・issue-233の履歴と仕様版54の現行条件）

現行仕様版54の新規Participantは`show_pretest_results=false`、`show_retest_results=false`を登録時にsnapshotする。事前テスト後の全体結果確認は`show_pretest_results`に従う。事前満点者は表示ONなら確認後、OFFなら直接surveyへ進む。事前未達者は表示ONなら確認後に学習へ、OFFなら学習へ直接進む。再テスト結果確認は`show_retest_results`に従い、事前満点者は再テスト自体を行わない。旧設定GET/PUT APIは廃止し、RuntimeSetting列は履歴互換のため残すが参照・更新しない。既存Participantの値は補完・更新せず、NULLは従来どおり表示ありと解釈する。

採点・診断APIは`review_required`と遷移先`next_url`を返し、表示を省略する場合は学習・次テスト・アンケートへ直接進む。採点結果と正誤判定は保存する。学習対象APIは表示を省略する場合に全体結果配列を空にし、現在位置API・直接URL・再開でも同じ遷移を適用する。古い冪等応答に`review_required`がない場合は既存の従来表示へフォールバックする。設問別確認は全体結果表示とは独立して実施する。

診断応答にはlearning_target_slugsも含め、結果画面を通らない経路でも学習進捗用の一覧を保存できるようにする。非表示でlearning_targets状態なのに学習対象が空の場合は503（learning_navigation_unavailable）とし、同じ画面のURLを返したり、GETで進行状態を修復したりしない。

## 教材・解説・テストの用語注釈（仕様版26）

教材・回答後解説に加え、GET /api/experiment/{id}/pretest、/retest、/final-testの各questions項目へ`glossary: {version, entries: [{id, term, definition}]}`を返す。テストは用語見出し・問題文・全選択肢から抽出し、選択・正誤・診断を使わない。未回答GETはDBへ保存せず、回答時に同じ不変辞書からAttempt.glossary_snapshotへ保存する。回答済みの再取得・再送は保存値を使い、欠落は後付けしない。該当語なしは空配列、snapshot欠落時はnull。指紋・出典・正答・分類情報は公開しない。新規ルート・管理設定は追加せず、nullable JSON列を1つ追加する。AI入力・共通履歴には含めない。[保存仕様](24_learning_glossary.md)。

## 2026-11-11 研究用コード登録（履歴、fix/issue-317）

- POST /api/registrations（互換URL /api/participants）: `assignment_code`、`consent_checked`、`research_code`を受け取る。`research_code`は半角数字1〜64桁を厳密に検証し、先頭ゼロを保持する。旧`student_number`フィールドなど余分なキーは拒否し、登録入力の検証応答では受信値を返さない。
- 当時は研究用コードを`IDENTITY_MAPPING_PATH`の分離SQLiteにある`research_code_mappings`へ保存していた。現在は登録時に検証後破棄し、既存SQLiteファイル・行はそのまま保持する。
- Idempotency-Keyによる同じ登録要求の再送は保存済み登録結果を返し、管理者が削除済みの対応表を再作成しない。既存の登録冪等性レコードに研究用コードそのものは保存しない。
- 当時のGET/CSV/DELETE `/api/admin/research-code-mappings`各routeは廃止済みで、現行APIでは提供しない。
- 旧`/api/admin/identity-mappings`系も現行APIでは提供しない。旧行を登録処理で読み書きしない。
- DELETE `/api/admin/participants/{participant_id}`は、明示的なParticipant削除後に、既存旧SQLite内の当該ID行だけを再試行可能なcleanupで削除する。外部Excel表は研究者が別途管理する。

上記はfix/issue-317当時の実装記録であり、その後の2026-11-12更新で同意文書・登録方式と一致させた。更新は指導教員または研究倫理上の承認を意味しない。

## 2026-10-21 同意・学籍番号対応表（履歴）

- POST /api/registrations（互換URL /api/participants）: assignment_code、consent_checked、student_numberを受け取る。学籍番号は必須・trim後1〜64文字・改行/制御文字不可。同意なしは400、不正な型は識別情報を返さない422。研究DBには学籍番号もそのハッシュも保存しない。Idempotency-Keyの再送は登録結果だけを返し、削除済み対応表を再作成しない。
- GET /api/admin/identity-mappings: アプリ内の対応表を返す。
- GET /api/admin/identity-mappings.csv: BOM付きUTF-8 CSVを返す。数式開始文字は無害化し、ファイル名には識別情報を含めない。
- DELETE /api/admin/identity-mappings/{participant_id}、DELETE /api/admin/identity-mappings: 対応表の個別/全件削除。研究データは残す。
- DELETE /api/admin/participants/{participant_id}: 現行プロトコルの研究DB内の関連データとアプリ内の対応表を削除する。旧データの409を維持する。ダウンロード済みファイル・USB・バックアップ・Codex側の保持データは削除対象外。

登録・全管理APIの応答はCache-Control: no-store。POST /api/admin/auth/loginはpasswordを受け、backendで照合する（既定abc、ADMIN_PASSWORDで変更）。POST /api/admin/auth/logoutはセッションを失効させる。ログイン時の入力エラーでは受信パスワードを返さない。管理API全体・POST /api/seed・管理用の評価再計算は有効なHttpOnly/SameSite=Strict Cookieがなければ401。管理書込みはOriginがある場合に設定済みfrontend・既存のhttp://127.0.0.1:3000・API自身のいずれにも一致しなければ403。HTTPSではSecureを付ける。セッションは単一backendプロセス内に30分保持し、再起動でも失効する。ChatGPT/Codexログインとは別の認証であり、研究DB・実験版・回答状態は変更しない。

削除済み登録キーの再送判定は、削除監査のregistration_keys配列をDB側で完全一致検索する。SQLiteはjson_each、PostgreSQLはjson_array_elements_textとEXISTSを使用し、監査JSONの全件取得・Pythonでの線形探索を行わない。参加者削除では、研究DBの削除と対応表削除待ち状態を同時にcommitし、その後に対応表を削除して監査状態を完了へ更新する。対応表削除に失敗しても研究DBの削除は巻き戻さず、監査のpendingを起動時または同じDELETE APIの再試行時に回復する。研究DBのcommitに失敗した場合は対応表に触れない。別DB間の分散トランザクションを保証するのではなく、研究DB内の削除outboxで片側だけの処理を再試行可能にする。

## 計画書対応の範囲

現行APIは[実装判断](20_experiment_plan_alignment.md)に沿う。仕様版54で進行可否を判定し、仕様版53以下および未対応版は閲覧専用とする。管理認証付きGET/PUT `/api/admin/test-content-mode`は新規登録で4用語版に固定された値を返し、他モードの設定変更を拒否する。必要な全設問を採点し全問正解したテストの後は、結果表示snapshotに従って結果確認後または直接surveyへ進み、学習・後続テストを省略する。未達者は4用語版の経路を使う。詳細は[4用語版](51_four_topic_foundation_mode.md)、[事前](49_presurvey_baseline.md)・[事後](52_posttest_five_point_evaluation.md)アンケート、[評価指標](12_evaluation_metrics.md)を参照する。

GET `/api/participants/{id}/presurvey`は参加者の固定済み`test_content_mode`に応じて`survey_version`と6件の`term_items`（`key`・`label`）を返す。標準2モードは`presurvey-baseline-v4`、4用語版は`presurvey-four-topic-baseline-v4`で、4用語版の`instruction_tuning`は「インストラクションチューニング」と表示する。POST同URLは、6用語の`prior_term_exposure`（`experienced`／`not_experienced`／`cannot_recall`）と`prior_term_understanding`（`not_at_all`／`slightly`／`moderately`／`well`またはnull）、`general_ratings.ai_usage_frequency_30d`（5区分）および3項目の`ai_proficiency`（1〜5または`not_applicable`）を受け付ける。経験が`experienced`なら理解度を必須とし、それ以外は理解度nullを要求する。欠落・余分な用語キー、不正な選択値、条件分岐に反する値は422。固定版に対応したPydantic modelで検証し、phase=presurveyのParticipantSurveyとして冪等保存する。理解度質問文は全モードで「{用語}の基本的な意味や働きをどの程度理解していますか。」とし、見聞き経験質問の「実験の説明を受ける前に」は維持する。登録後の`current_step=presurvey`中はテスト出題・採点を拒否し、保存後にpretestへ進める。仕様版50以下の保存済み回答は記録時のschemaのまま復元し、変換しない。

事後SurveyPayloadは`backend/app/services/research_protocol.py`で定義する。現行の新規送信`posttest-5point-v4`は、`general_ratings`の`system_usability` 1項目と`material_ratings`（`clarity`、`readability`、`japanese_clarity`、`difficulty_appropriateness`、`learning_usefulness`、`amount_appropriateness`）の各項目に、厳密な整数1〜5または`not_applicable`を受け付ける。`system_clarity`を含む余分なキーは拒否する。自由記述は任意。`material_ratings`は未閲覧者のみnull、閲覧者は6項目すべて必須。旧`posttest-10point-v1/v2/v3`と`posttest-5point-v1/v2/v3`の保存済み回答は変換せず保持する。H5は現行版の中核4項目について数値回答の参加者内平均を算出し、評価不能を除外する。難易度・教材量は平均に含めず分布を別集計する。事後アンケートの詳細は[仕様書](52_posttest_five_point_evaluation.md)、H5は[指標](12_evaluation_metrics.md)を参照する。

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
| 推論レベル設定 | POST `/api/admin/ai/reasoning-effort` (`reasoning_effort`: `low`, `medium`, `high`, `xhigh`, `max`) |
| AIモデル設定 | POST `/api/admin/ai/model` (`model`: `gpt-6.1-sol`, `gpt-6-luna`, `gpt-6-astra`) |
| Codex Fast mode設定 | POST `/api/admin/ai/fast-mode` (`enabled`: boolean) |
| 選択肢配置設定の取得 | GET `/api/admin/option-order` |
| 選択肢配置設定の更新 | PUT `/api/admin/option-order` (`mode`: `debug_fixed` または `randomized`) |
| 管理者ログ | GET `/api/admin/participants/{id}/logs`, `/logs.csv`, `/logs_excel.csv`, `/logs.xlsx`; 全体ログは `/api/admin/logs/overview.csv`, `/overview_excel.csv`, `/overview.xlsx` |
| 評価再計算 | POST `/api/participants/{id}/evaluation-summary/recalculate` |

`GET /api/admin/ai/status`は`fast_mode`、`can_change_fast_mode`、`fast_mode_applies`を返す。Fast mode更新は厳密なJSON真偽値だけを受け付け、`AI_BACKEND=mock`では409を返す。設定はbackendプロセス内だけに保持する。

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

事前・再テスト・内部final_testの取得APIは`test_page_mode`を返す。現行仕様版54の新規参加者は`per_term`で、当該用語ページに表示された設問への回答をページ単位で保存する。通常の2モードは各用語の設問1、4用語版は各用語の1問を保存する。`POST /api/attempts/term-page`はparticipant_id、phase、term_slug、test_round、page_id、各回答のquestion_idと選択肢ID、共通表示/回答時刻、正のelapsed_time_secを受け、`Idempotency-Key`を必須とする。同一ページ・用語・回次の有効な問題と選択を検証し、未保存分を同一トランザクションで確定する。既存回答は変更せず、異なる回答との競合は409。応答に正答・正誤・分類情報を含めない。従来の`POST /api/attempts`は旧形式の回答保存と履歴互換に残す。

用語ページ時間は`Attempt.test_page_timing_json`（nullable JSON）へpage_id、`measurement_version=term_page_v1`、elapsed_time_secを記録し、新形式の設問別`response_time_sec`はNULLとする。集計ではpage_idごとに時間を一度だけ数える。従来記録は設問ごとのresponse_time_secで計算する。参加者ログとCSV/Excelの`test_page_mode`・`test_timing_unit`・ページ時間JSONで表示方式と測定単位を識別する。統合ログCSVの既存ヘッダは維持する。詳細は[設問分割仕様](39_split_assessment.md#テスト画面と時間計測issue-208)。

仕様版53以下・未対応版・旧protocol_idは、本文検証・冪等再送・先行生成より前に409 legacy_experiment_read_only。current-stepは保存状態を変えずstep=legacy_read_only/can_resume=falseを返す。現行の仕様版54とprotocol IDの組み合わせだけが進行可能であり、既存行の仕様版・protocol_idを補完しない。

参加者の出題APIに正答や分類メタデータを公開しない。回答後の結果確認では問題・選択内容・正誤を返す。Idempotency-Keyの再送、回答済みロックは維持する。旧試用の管理者閲覧・CSVは許可し、再計算は拒否する。

`POST /api/participants/{id}/score-retest`とscore-final-test、GET learning-targets、管理者一覧/ログはpost_pretest_tests_completedとpost_pretest_test_limitを返す。現行版の上限は2で、旧版は両値null。retest_cycles_completedは学習後retestだけの既存カウンターを維持し、共通回数は採点済みfinal_testの有無を加えて導出する。未回答を含むバッチも1回、全問未回答は400、冪等再送は加算しない。必要な全設問が採点済みで全問正解なら全モードでsurveyへ進み、後続の学習・テストを省略する。4用語版の再テスト1満点時も固定学習対象は設定しない。未達時は既存の学習経路を維持し、再テスト2の採点後は正誤にかかわらずsurveyへ進む。retest_cycle_limit_reachedは上限時かつ未達の場合trueで、未達対象を保持する。問題取得・回答では現在の全体回次に合うvariantのみ認め、前後回次の問題IDは409、必要なvariant欠落は503とする。

選択肢配置はRuntimeSettingの単一行で管理する。未設定時は `debug_fixed`。管理APIのPUTで設定を保存し、GETは現在値と `applies_to=new_participants_only` を返す。新規参加者には開始時のモードを保存し、既存参加者のnull値は `debug_fixed` として扱う。`randomized` は「わからない」を最後のJに固定し、残る9択をA〜Iへ固定・均衡配置する。同一問題は群や参加者をまたいで同じラベル・順序となる。採点は表示ラベルではなく選択肢IDと内部メタデータで行う。画面向け選択肢に追加する `exclusive` は「わからない」の単独選択を扱うための情報で、正誤やM1/M3分類は含まない。

ランダム配置の学習問題で送る `option_id` は、表示済みのTutorTurnスナップショットに保存するランダムIDであり、元の選択肢ラベルや判定役割を符号化しない。回答時はそのスナップショットを内部選択肢へ照合する。設問再取得・送信再試行では保存済みTutorTurnを返すため、同じ表示に対するIDは維持される。問題の表示ラベルと順序自体は問題バンクから決定論的に生成する。

## 廃止された問題版フィルター

AIモデル・推論レベル設定はDBへ保存しないbackendプロセス内の一時設定であり、両群・進行中参加者にも次のAI呼び出しから適用する。状態/更新応答は有効値と選択肢を返す。モデル選択はcodex_app_serverでのみ適用でき、Mockでは409で拒否する。実際に使ったモデル・推論レベルと標準条件への一致はAI監査JSONに残る。環境変数の明示値は既定値より優先し、backend再起動後に管理上書きは消える。

`/api/admin/question-set`は廃止し、GET/PUTとも404を返す。集計・ログ一覧・仮説CSV/Excelに旧`question_set_mode`を含むフィルターを指定した要求は422で拒否する。これは仕様版43の独立した`test_content_mode`設定を無効にするものではない。新規参加者は管理認証付き`/api/admin/test-content-mode`で選んだモードを登録時にsnapshotし、出題・採点・復元は対応するconstruct keyを使う。旧easy-mode列削除手順は新しい列・問題資産を削除せず、過去のsnapshotと履歴バンクは維持する。
