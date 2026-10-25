# 現行API

## 教材・解説の用語注釈（仕様版12）

POST /api/tutor-sessions/{id}/turnsとPOST /api/tutor-turns/{id}/respondのレスポンスへ`glossary: {version, entries: [{id, term, definition}]}`を追加する。語がなければentriesは空配列。保存snapshotだけを返し、辞書指紋・出典・診断・正答情報を公開しない。新規ルート・DB列・管理設定は追加しない。AI入力と共通履歴には含めない。[保存仕様](24_learning_glossary.md)。

## 2026-10-21 同意・分離対応表

- POST /api/registrations（互換URL /api/participants）: assignment_code、consent_checked、student_numberを受け取る。学籍番号は必須・trim後1〜64文字・改行/制御文字不可。同意なしは400、不正な型は識別情報を返さない422。研究DBには学籍番号もそのハッシュも保存しない。Idempotency-Keyの再送は登録結果だけを返し、削除済み対応表を再作成しない。
- GET /api/admin/identity-mappings: アプリ内の対応表を返す。
- GET /api/admin/identity-mappings.csv: BOM付きUTF-8 CSVを返す。数式開始文字は無害化し、ファイル名には識別情報を含めない。
- DELETE /api/admin/identity-mappings/{participant_id}、DELETE /api/admin/identity-mappings: 対応表の個別/全件削除。研究データは残す。
- DELETE /api/admin/participants/{participant_id}: 現行プロトコルの研究DB内の関連データとアプリ内の対応表を削除する。旧データの409を維持する。ダウンロード済みファイル・USB・バックアップ・Codex側の保持データは削除対象外。

登録・対応表の応答はCache-Control: no-store。対応表APIも現状は認証なしであり、確認ポップアップは認可の代わりにはならない。

削除済み登録キーの再送判定は、削除監査のregistration_keys配列をDB側で完全一致検索する。SQLiteはjson_each、PostgreSQLはjson_array_elements_textとEXISTSを使用し、監査JSONの全件取得・Pythonでの線形探索を行わない。参加者削除では、研究DBの削除と対応表削除待ち状態を同時にcommitし、その後に対応表を削除して監査状態を完了へ更新する。対応表削除に失敗しても研究DBの削除は巻き戻さず、監査のpendingを起動時または同じDELETE APIの再試行時に回復する。研究DBのcommitに失敗した場合は対応表に触れない。別DB間の分散トランザクションを保証するのではなく、研究DB内の削除outboxで片側だけの処理を再試行可能にする。

## 計画書対応の範囲

現行APIは[承認済み実装判断](20_experiment_plan_alignment.md)に沿う。実験仕様版12と新protocol_idの両方で進行可否を判定する。

SurveyPayloadはservices/research_protocol.pyで定義する。experiences（chat/coding_assistance/cli/apiの厳密boolean）、general_ratings（ai_usage_frequency/self_rated_ai_knowledge/system_usability/system_clarity）、material_ratings（clarity/readability/japanese_clarity/difficulty_appropriateness/learning_usefulness/amount_appropriateness）、必須free_commentを受け付ける。評定は厳密な整数1〜10。material_ratingsは未表示者のみnull、表示者は6項目必須。余分なキー・旧フォーム・空白のみのコメントを拒否する。

GET /api/participants/{id}/surveyはアンケート版・表示判定・教材評価の必須/対象外を返す。POST /api/tutor-turns/{id}/material-viewは初回表示時刻を冪等に記録し、未利用の先行生成は拒否する。管理集計のhypothesesおよび/export/hypothesis_metrics.csv、/export/hypothesis_group_summary.csvは6仮説の専用指標である。

## 利用可能な現行契約

正本は `backend/app/main.py`。回答可能フェーズはpretest/retest/final_testだけ。廃止した追加確認の専用URL/APIは404。

| 用途 | API |
| --- | --- |
| 新規開始 | POST `/api/participants` |
| 再開判定 | GET `/api/participants/{id}/current-step` |
| 出題 | GET `/api/experiment/{id}/pretest`, `/retest`, `/final-test` |
| 回答保存 | POST `/api/attempts` |
| 事前固定採点 | POST `/api/participants/{id}/diagnose-pretest` |
| 結果・学習対象 | GET `/api/participants/{id}/learning-targets` |
| 学習開始 | POST `/api/tutor-sessions` |
| 教材・固定問題 | POST `/api/tutor-sessions/{id}/turns` |
| 回答・解説 | POST `/api/tutor-turns/{id}/respond` |
| テスト採点 | POST `/api/participants/{id}/score-retest`, `/score-final-test` |
| 中断 | POST `/api/participants/{id}/give-up-learning`, `/give-up` |
| アンケート | POST `/api/participants/{id}/survey` |
| アンケート対象判定 | GET `/api/participants/{id}/survey` |
| 教材表示記録 | POST `/api/tutor-turns/{id}/material-view` |
| 6仮説の群別集計 | GET `/api/admin/evaluation-summary` のhypotheses |
| 6仮説CSV | GET `/api/admin/export/hypothesis_metrics.csv`, `/hypothesis_group_summary.csv` |
| AI設定状態 | GET `/api/admin/ai/status` |
| 推論レベル設定 | POST `/api/admin/ai/reasoning-effort` (`reasoning_effort`: `low`, `medium`, `high`) |
| AIモデル設定 | POST `/api/admin/ai/model` (`model`: `gpt-6.1-sol` または `gpt-6-luna`) |
| 選択肢配置設定の取得 | GET `/api/admin/option-order` |
| 選択肢配置設定の更新 | PUT `/api/admin/option-order` (`mode`: `debug_fixed` または `randomized`) |
| 管理者ログ | GET `/api/admin/participants/{id}/logs`, `/logs.csv`, `/logs_excel.csv` |
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

NULL・版1〜11・未対応版・旧protocol_idは、本文検証・冪等再送・先行生成より前に409 legacy_experiment_read_only。current-stepは保存状態を変えずstep=legacy_read_only/can_resume=falseを返す。新規版12＋現行protocol_idのみcan_resume=true。

参加者の出題APIに正答や分類メタデータを公開しない。回答後の結果確認では問題・選択内容・正誤を返す。Idempotency-Keyの再送、回答済みロックは維持する。旧試用の管理者閲覧・CSVは許可し、再計算は拒否する。

`POST /api/participants/{id}/score-retest`とscore-final-test、GET learning-targets、管理者一覧/ログはpost_pretest_tests_completedとpost_pretest_test_limitを返す。現行版の上限は2で、旧版は両値null。retest_cycles_completedは学習後retestだけの既存カウンターを維持し、共通回数は採点済みfinal_testの有無を加えて導出する。未回答を含むバッチも1回、全問未回答は400、冪等再送は加算しない。満点または事前後2回目未達でsurveyへ進む。retest_cycle_limit_reachedは上限時かつ未達の場合trueで、未達対象を保持する。問題取得・回答では現在の全体回次に合うvariantのみ認め、前後回次の問題IDは409、必要なvariant欠落は503とする。

選択肢配置はRuntimeSettingの単一行で管理する。未設定時は `debug_fixed`。管理APIのPUTで設定を保存し、GETは現在値と `applies_to=new_participants_only` を返す。新規参加者には開始時のモードを保存し、既存参加者のnull値は `debug_fixed` として扱う。`randomized` は「わからない」を最後のJに固定し、残る9択をA〜Iへ固定・均衡配置する。同一問題は群や参加者をまたいで同じラベル・順序となる。採点は表示ラベルではなく選択肢IDと内部メタデータで行う。画面向け選択肢に追加する `exclusive` は「わからない」の単独選択を扱うための情報で、正誤やM1/M3分類は含まない。

ランダム配置の学習問題で送る `option_id` は、表示済みのTutorTurnスナップショットに保存するランダムIDであり、元の選択肢ラベルや判定役割を符号化しない。回答時はそのスナップショットを内部選択肢へ照合する。設問再取得・送信再試行では保存済みTutorTurnを返すため、同じ表示に対するIDは維持される。問題の表示ラベルと順序自体は問題バンクから決定論的に生成する。

## 問題版と集計版

AIモデル・推論レベル設定はDBへ保存しないbackendプロセス内の一時設定であり、両群・進行中参加者にも次のAI呼び出しから適用する。状態/更新応答は有効値と選択肢を返す。モデル選択はcodex_app_serverでのみ適用でき、Mockでは409で拒否する。実際に使ったモデル・推論レベルと標準条件への一致はAI監査JSONに残る。環境変数の明示値は既定値より優先し、backend再起動後に管理上書きは消える。

GET/PUT /api/admin/question-setはmode=standard|easyを扱い、新規参加者だけに適用する。問題版と配置は別設定。evaluation-summary、logs/overview、仮説2種CSVのquery question_set_mode（既定standard）で集計版を選ぶ。生ログは全版保持。参加者向け問題APIへ正答・分類情報は追加しない。他版の問題IDは409、不足する自版問題は503。API一覧と保存契約は[22](22_question_set_modes.md)。
