# 研究計画と仕様・実装の対応

新規参加者は仕様版55 / `experiment-plan-2026-11-13-presurvey-ai-proficiency-examples-v1`を対象とし、全モードの結果を`test_content_mode`ごとに分ける。必要な全設問が採点済みで全問正解したテスト後は、結果表示snapshotに応じて確認後または直接surveyへ進み、学習・後続テストを省略する。事後アンケートは`posttest-5point-v4`、現行指標版は`four-hypotheses-v1`（H1〜H4）。仕様版52の対応する2 protocolは参加者進行・回答・旧サマリーを変更せず、H1〜H4評価サマリーのみ追加できる。仕様版51以下・未対応protocolは再計算しない。4用語版は事前アンケートv5と問題バンクv3を使う。AI利用自己評価3項目には具体例を表示するが、回答仕様は変更しない。難易度・測定上の同等性や研究上の承認は未確認。

出典・採用判断は[20](20_experiment_plan_alignment.md)、式と欠測定義は[12](12_evaluation_metrics.md)を正本とする。

| 仮説・要件 | 実装・記録 | 管理・出力 |
| --- | --- | --- |
| H1：正答率の伸び | `hypothesis_metrics.h1`、事前・初回再テストの採点済み完答ペア | 群別平均・中央値・n。後続回次は参考値 |
| H2：同じ誤答タイプの再選択 | `hypothesis_metrics.h2`、事前M1/M3項目と初回再テストの分類 | 完答ペアの参加者ごとの割合を主集計、項目加重率は参考値 |
| H3：再テスト満点率 | `hypothesis_metrics.h3`、採点済み全問正解と事前完了状況 | 事前完了かつ事前非満点を分母に含む。未受験・中断・未達は未到達 |
| H4：教材評価 | 教材表示ログ、現行`posttest-5point-v4`の6項目 | 項目別集計。4項目の数値平均・中央値・差、難易度・分量は分布のみ。総合点なし |
| 共通履歴・群別入力 | services/interaction_history、ai/interaction_history | 実送信入力・指紋監査 |
| 教授と証拠 | tutoring_prompt、mandatory_elements、teaching_contract | v7契約、unknownの定義・仕組み・適用確認 |
| AI設定 | config、環境low、runtime_config | 不一致警告・実送信model/effort |
| アンケート | `presurvey-baseline-v5` / `presurvey-four-topic-baseline-v5` / `posttest-5point-v4`、phase別ParticipantSurvey | 事前はモード別6用語の見聞き経験、経験ありの場合の理解度、直近30日AI利用頻度、AI活用3評定。事後はシステム1＋教材6＋任意自由記述。教材量設問を更新し、仕様版52のv3回答を保全 |
| テスト上限・回次 | 学習後回数＋採点済みfinal_testから全体回次を導出 | 事前後最大2回、事前込み最大3回。未達を維持してsurvey |
| 行動選択型問題 | scenario-actions-v9、9固有問、版付きconstruct_key | 旧問題非active保全、分類根拠は21 |
| 問題モード・時間 | `RuntimeSetting.test_content_mode`をParticipantへ登録時snapshotし、3つの独立bankから出題・採点・学習確認を復元。用語ページ単位の`test_page_timing_json`を保持 | 3問/4問をモード別に集計し、全問正解後は後続学習・テストを省略する。回答時間の単位をログ・CSV/Excelに表示し、対応する個別`.xlsx`を提供。難易度同等性・研究承認は未確認 |
| 旧記録保護 | 仕様版26＋protocol_id、API/worker/補修ガード | 仕様版54以下は参加者操作read-only。仕様版52の対応2 protocolだけH1〜H4評価サマリーを追加。仕様版51以下・未対応protocolは再計算対象外 |
| 割付・アクセス・正答配置 | 既存A/Bコード・デバッグ問題を維持 | 自動割付・認証・位置復旧は今回対象外 |

計算の正本はbackend/app/services/hypothesis_metrics.py。新指標はEvaluationSummary.hypothesis_metrics_jsonに分離し、統合CSVヘッダと旧値を維持する。専用CSVはhypothesis_metricsとhypothesis_group_summary。
