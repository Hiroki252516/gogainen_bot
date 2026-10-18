# 現行API

## 計画書対応の範囲

以下は利用可能な現行APIであり今回変更しない。計画書を目標仕様にしても新アンケート・6仮説の集計が利用可能になったとはしない。[未対応と要確認](20_experiment_plan_alignment.md) を参照する。

特にPOST /api/participants/{id}/surveyのSurveyPayload（backend/app/main.py:192-201）は経験・自己評価・操作評価等を1〜5で受け付ける現行型。計画の有無回答・1〜10段階・教材6項目に対応する新しい入力型/項目名・保存契約は未実装。既存エンドポイントがあることを新項目の受付保証としない。

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
| 管理者ログ | GET `/api/admin/participants/{id}/logs`, `/logs.csv`, `/logs_excel.csv` |
| 評価再計算 | POST `/api/participants/{id}/evaluation-summary/recalculate` |

回答は `selected_option_ids` と時刻情報（response_time_sec、question_shown_at、answered_at）。テストはparticipant_id/question_id/phaseも指定する。廃止入力項目は422。

NULL・仕様版1/2・未対応版の書込みは本文検証・冪等レスポンス再送・先行生成より前に409 `legacy_experiment_read_only`。current-stepは保存状態を変えず `step=legacy_read_only`, `can_resume=false` を返す。新規仕様版3は `can_resume=true`。公開APIの構造は変えない。

参加者の出題APIに正答や分類メタデータを公開しない。回答後の結果確認では問題・選択内容・正誤を返す。Idempotency-Keyの再送、回答済みロックは維持する。旧試用の管理者閲覧・CSVは許可し、再計算は拒否する。
