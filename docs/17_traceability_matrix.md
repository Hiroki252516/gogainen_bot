# 研究計画と仕様・実装の対応

用語注釈はservices/learning_glossary、固定YAML、LearningGlossary表示コンポーネントで処理し、TutorTurnの既存JSONと統合CSVのvalue_jsonへsnapshotを保持する。AI契約版はv7を維持し、実験仕様版19・共通固定辞書v1として区別する。[24](24_learning_glossary.md)。

出典・採用判断は[20](20_experiment_plan_alignment.md)、式と欠測定義は[12](12_evaluation_metrics.md)を正本とする。

| 仮説・要件 | 実装・記録 | 管理・出力 |
| --- | --- | --- |
| H1：正答率の伸び | hypothesis_metrics.h1、採点済み完答ペア、初回再テスト | 群別平均・中央値・n、回次・経路別参考 |
| H2：満点までのセッション | material_viewed_at、初回満点の採点記録、h2 | 到達者と未達者の観測回数を分離 |
| H3：用語内の反復 | 回答済みTutorTurn.grading_json、h3.term_means/sessions | 用語内・参加者内平均、不正解0〜3 |
| H4：同種再選択 | 事前M1/M3と初回再テストの分類、h4分子/分母 | 参加者率平均と参考件数比 |
| H5：教材評価 | 表示ログ、新ParticipantSurvey.responses_json、h5 | 6項目別と6項目平均 |
| H6：満点到達割合 | 採点済み3問全正解、h6、現行登録者 | 到達人数/登録人数。completedとは別 |
| 共通履歴・群別入力 | services/interaction_history、ai/interaction_history | 実送信入力・指紋監査 |
| 教授と証拠 | tutoring_prompt、mandatory_elements、teaching_contract | v7契約、unknownの定義・仕組み・適用確認 |
| AI設定 | config、環境low、runtime_config | 不一致警告・実送信model/effort |
| アンケート | research_protocol.SurveyPayload、survey画面 | 経験4有無・一般4/教材6の1〜10・必須自由記述 |
| テスト上限・回次 | 学習後回数＋採点済みfinal_testから全体回次を導出 | 事前後最大2回、事前込み最大3回。未達を維持してsurvey |
| 行動選択型問題 | scenario-actions-v5、9固有問、版付きconstruct_key | 旧問題非active保全、分類根拠は21 |
| 旧記録保護 | 仕様版19＋protocol_id、API/worker/補修ガード | 旧版18以下も閲覧専用・新集計から除外 |
| 割付・アクセス・正答配置 | 既存A/Bコード・デバッグ問題を維持 | 自動割付・認証・位置復旧は今回対象外 |

計算の正本はbackend/app/services/hypothesis_metrics.py。新指標はEvaluationSummary.hypothesis_metrics_jsonに分離し、統合CSVヘッダと旧値を維持する。専用CSVはhypothesis_metricsとhypothesis_group_summary。

## 易しい版の対応

管理切替→main.py/question_setsサービス/admin画面、固定版→Participantとexperimentサービス、別バンク→content_loader/seed_questions、平易化→interaction_history/tutoring_prompt、版別集計→hypothesis_metricsとHypothesisMetrics、個別分類根拠→[23](23_easy_question_bank.md)。保存・受入条件は[22](22_question_set_modes.md)を参照する。
