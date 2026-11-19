# 研究計画と仕様・実装の対応

新規参加者は仕様版61 / `experiment-plan-2026-11-19-presurvey-guidance-example-v1`の`four_topic_fundamentals`に固定する。旧protocolを含む結果を扱う場合は`test_content_mode`ごとに分ける。必要な全設問が採点済みで全問正解したテスト後は、結果表示snapshotに応じて確認後または直接surveyへ進み、学習・後続テストを省略する。事後アンケートは`posttest-5point-v5`、現行指標版は`four-hypotheses-v1`（H1〜H4）。仕様版52の対応する2 protocolは参加者進行・回答・旧サマリーを変更せず、H1〜H4評価サマリーのみ追加できる。仕様版51以下・未対応protocolは再計算しない。事前アンケートv10と問題バンクv4を使う。理解度は中立値`neither`を含む5段階で、仕様版60以下の回答を変換しない。事前AI自己評価と事後評価から「評価できない」を外し、数値を上・文言を下に置く。教材難易度・量は末尾に間隔を置いて配置する。AI利用日数の質問文と自己評価3項目の設問文、最初の2項目の例を維持し、3項目目に「AIが答えた営業時間を、お店の公式サイトで確認する。」を表示する条件は維持する。難易度・測定上の同等性や研究上の承認は未確認。

出典・採用判断は[20](20_experiment_plan_alignment.md)、式と欠測定義は[12](12_evaluation_metrics.md)を正本とする。

| 仮説・要件 | 実装・記録 | 管理・出力 |
| --- | --- | --- |
| H1：正答率の伸び | `hypothesis_metrics.h1`、事前・初回再テストの採点済み完答ペア | 群別平均・中央値・n。後続回次は参考値 |
| H2：同じ誤答タイプの再選択 | `hypothesis_metrics.h2`、事前M1/M3項目と初回再テストの分類 | 完答ペアの参加者ごとの割合を主集計、項目加重率は参考値 |
| H3：再テスト満点率 | `hypothesis_metrics.h3`、採点済み全問正解と事前完了状況 | 事前完了かつ事前非満点を分母に含む。未受験・中断・未達は未到達 |
| H4：教材評価 | 教材表示ログ、現行`posttest-5point-v5`の6項目 | 項目別集計。4項目の数値平均・中央値・差、難易度・分量は分布のみ。総合点なし |
| 共通履歴・群別入力 | services/interaction_history、ai/interaction_history | 実送信入力・指紋監査 |
| 教授と証拠 | tutoring_prompt、mandatory_elements、teaching_contract | v7契約、unknownの定義・仕組み・適用確認 |
| AI設定 | config、環境low、runtime_config | 不一致警告・実送信model/effort |
| アンケート | `presurvey-baseline-v5` / `presurvey-four-topic-baseline-v10` / `posttest-5point-v5`、phase別ParticipantSurvey | 事前は6用語の経験・条件付き理解度、AI利用頻度、AI活用3評定。v8の中間理解度値は`neither`。事前自己評価と事後評価は1〜5のみ。旧版の回答値は保存時の版で保持 |
| テスト上限・回次 | 学習後回数＋採点済みfinal_testから全体回次を導出 | 事前後最大2回、事前込み最大3回。未達を維持してsurvey |
| 行動選択型問題 | scenario-actions-v9、9固有問、版付きconstruct_key | 旧問題非active保全、分類根拠は21 |
| 問題モード・時間 | `RuntimeSetting.test_content_mode`をParticipantへ登録時snapshotし、3つの独立bankから出題・採点・学習確認を復元。用語ページ単位の`test_page_timing_json`を保持 | 3問/4問をモード別に集計し、全問正解後は後続学習・テストを省略する。回答時間の単位をログ・CSV/Excelに表示し、対応する個別`.xlsx`を提供。難易度同等性・研究承認は未確認 |
| 旧記録保護 | 仕様版26＋protocol_id、API/worker/補修ガード | 仕様版60以下は参加者操作read-only。仕様版52の対応2 protocolだけH1〜H4評価サマリーを追加。仕様版51以下・未対応protocolは再計算対象外 |
| 割付・アクセス・正答配置 | 既存A/Bコード・デバッグ問題を維持 | 自動割付・認証・位置復旧は今回対象外 |

計算の正本はbackend/app/services/hypothesis_metrics.py。新指標はEvaluationSummary.hypothesis_metrics_jsonに分離し、統合CSVヘッダと旧値を維持する。専用CSVはhypothesis_metricsとhypothesis_group_summary。
