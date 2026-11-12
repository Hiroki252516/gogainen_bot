# 研究計画と仕様・実装の対応

現行実装は仕様版51 / `experiment-plan-2026-11-12-perfect-test-early-exit-v1`。必要な全設問が採点済みで全問正解した場合、事前・再テスト・内部`final_test`の全モードで後続の学習・テストを行わずsurveyへ進む。再テスト1の満点後も4用語版の学習対象を設定しない。結果表示は参加者の事前・再テスト結果表示snapshotに従う。H1/H2/H6に対する事前満点経路の既存対象外扱いは維持し、新しい評価式や指標区分は追加しない。事前アンケート、事後アンケート、H5、現行辞書v4も変わらない。仕様版50以下は保存済み内容を保全し閲覧専用。[実験フロー](02_experiment_flow.md)、[事前アンケート](49_presurvey_baseline.md)、[事後アンケート](52_posttest_five_point_evaluation.md)、[指標](12_evaluation_metrics.md)、[辞書](24_learning_glossary.md)。

出典・採用判断は[20](20_experiment_plan_alignment.md)、式と欠測定義は[12](12_evaluation_metrics.md)を正本とする。

| 仮説・要件 | 実装・記録 | 管理・出力 |
| --- | --- | --- |
| H1：正答率の伸び | hypothesis_metrics.h1、採点済み完答ペア、初回再テスト | 群別平均・中央値・n、回次・経路別参考 |
| H2：満点までのセッション | material_viewed_at、初回満点の採点記録、h2 | 到達者と未達者の観測回数を分離 |
| H3：用語内の反復 | 回答済みTutorTurn.grading_json、h3.term_means/sessions | 用語内・参加者内平均、不正解0〜3 |
| H4：同種再選択 | 事前M1/M3と初回再テストの分類、h4分子/分母 | 参加者率平均と参考件数比 |
| H5：教材評価 | 表示ログ、`posttest-5point-v2`の中核4数値評定、h5 | 参加者内4項目平均。評価不能・欠測を区別し、難易度・教材量は分布を別掲 |
| H6：満点到達割合 | モード別の採点済み全問正解、h6 | 3用語モードは3問、4用語モードは4問。分子/分母は適用対象者のみ。事前満点早期終了は対象外として別計数し、完了人数とは別 |
| 共通履歴・群別入力 | services/interaction_history、ai/interaction_history | 実送信入力・指紋監査 |
| 教授と証拠 | tutoring_prompt、mandatory_elements、teaching_contract | v7契約、unknownの定義・仕組み・適用確認 |
| AI設定 | config、環境low、runtime_config | 不一致警告・実送信model/effort |
| アンケート | `presurvey-baseline-v4` / `presurvey-four-topic-baseline-v3` / `posttest-5point-v2`、phase別ParticipantSurvey | 事前はモード別6用語の見聞き経験、経験ありの場合の理解度、直近30日AI利用頻度、AI活用3評定。事後はシステム2＋教材6＋任意自由記述。旧回答は不変で保全 |
| テスト上限・回次 | 学習後回数＋採点済みfinal_testから全体回次を導出 | 事前後最大2回、事前込み最大3回。満点時はその場でsurvey、未達上限では未達を記録してsurvey |
| 行動選択型問題 | scenario-actions-v9、9固有問、版付きconstruct_key | 旧問題非active保全、分類根拠は21 |
| 問題モード・時間 | 仕様版51で`RuntimeSetting.test_content_mode`をParticipantへ登録時snapshotし、3つの独立bankから出題・採点・学習確認を復元。用語ページ単位の`test_page_timing_json`を保持 | 3問/4問をモード別に集計し、満点なら後続学習・テストを省略する。事前満点の既存対象外扱いを維持。回答時間の測定単位をログ・CSV/Excelに表示。個別`.xlsx`を提供。難易度同等性・研究承認は未確認 |
| 旧記録保護 | 仕様版26＋protocol_id、API/worker/補修ガード | 旧版25以下も閲覧専用・新集計から除外 |
| 割付・アクセス・正答配置 | 既存A/Bコード・デバッグ問題を維持 | 自動割付・認証・位置復旧は今回対象外 |

計算の正本はbackend/app/services/hypothesis_metrics.py。新指標はEvaluationSummary.hypothesis_metrics_jsonに分離し、統合CSVヘッダと旧値を維持する。専用CSVはhypothesis_metricsとhypothesis_group_summary。
