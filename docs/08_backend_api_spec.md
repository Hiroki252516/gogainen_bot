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
| 管理者ログ | GET `/api/admin/participants/{id}/logs`, `/logs.csv`, `/logs_excel.csv` |
| 評価再計算 | POST `/api/participants/{id}/evaluation-summary/recalculate` |

回答は `selected_option_ids` と時刻情報（response_time_sec、question_shown_at、answered_at）。テストはparticipant_id/question_id/phaseも指定する。廃止入力項目は422。

NULL・版1/2・未対応版・旧protocol_idの版3は、本文検証・冪等再送・先行生成より前に409 legacy_experiment_read_only。current-stepは保存状態を変えずstep=legacy_read_only/can_resume=falseを返す。新規版3＋現行protocol_idのみcan_resume=true。

参加者の出題APIに正答や分類メタデータを公開しない。回答後の結果確認では問題・選択内容・正誤を返す。Idempotency-Keyの再送、回答済みロックは維持する。旧試用の管理者閲覧・CSVは許可し、再計算は拒否する。
