# 現行API

## 計画書対応の範囲

現行APIは[承認済み実装判断](20_experiment_plan_alignment.md)に沿う。実験仕様版3と新protocol_idの両方で進行可否を判定する。

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
| 選択肢配置設定の取得 | GET `/api/admin/option-order` |
| 選択肢配置設定の更新 | PUT `/api/admin/option-order` (`mode`: `debug_fixed` または `randomized`) |
| 管理者ログ | GET `/api/admin/participants/{id}/logs`, `/logs.csv`, `/logs_excel.csv` |
| 評価再計算 | POST `/api/participants/{id}/evaluation-summary/recalculate` |

回答は `selected_option_ids` と時刻情報（response_time_sec、question_shown_at、answered_at）。テストはparticipant_id/question_id/phaseも指定する。廃止入力項目は422。

NULL・版1/2・未対応版・旧protocol_idの版3は、本文検証・冪等再送・先行生成より前に409 legacy_experiment_read_only。current-stepは保存状態を変えずstep=legacy_read_only/can_resume=falseを返す。新規版3＋現行protocol_idのみcan_resume=true。

参加者の出題APIに正答や分類メタデータを公開しない。回答後の結果確認では問題・選択内容・正誤を返す。Idempotency-Keyの再送、回答済みロックは維持する。旧試用の管理者閲覧・CSVは許可し、再計算は拒否する。

選択肢配置はRuntimeSettingの単一行で管理する。未設定時は `debug_fixed`。管理APIのPUTで設定を保存し、GETは現在値と `applies_to=new_participants_only` を返す。新規参加者には開始時のモードを保存し、既存参加者のnull値は `debug_fixed` として扱う。`randomized` は問題バンクごとの固定・均衡配置で、同一問題は群や参加者をまたいで同じラベル・順序となる。採点は表示ラベルではなく選択肢IDと内部メタデータで行う。画面向け選択肢に追加する `exclusive` は「わからない」の単独選択を扱うための情報で、正誤やM1/M3分類は含まない。

ランダム配置の学習問題で送る `option_id` は、表示済みのTutorTurnスナップショットに保存するランダムIDであり、元の選択肢ラベルや判定役割を符号化しない。回答時はそのスナップショットを内部選択肢へ照合する。設問再取得・送信再試行では保存済みTutorTurnを返すため、同じ表示に対するIDは維持される。問題の表示ラベルと順序自体は問題バンクから決定論的に生成する。
