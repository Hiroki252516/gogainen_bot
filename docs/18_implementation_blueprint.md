# 現行プロトコルの実装境界

> この文書の版26に関する記述は当時の実装設計記録であり、現行状態ではない。現行仕様版51の問題モード、参加者snapshot、モード別集計は[50](50_basic_understanding_question_mode.md)・[51](51_four_topic_foundation_mode.md)を参照する。現行のコード・運用は[00](00_project_summary.md)、[02](02_experiment_flow.md)、[19](19_experiment_operation_runbook.md)、[41](41_learning_glossary_material_mode.md)、[42](42_learning_glossary_material_length.md)、[43](43_glossary_definition_paraphrase.md)、[44](44_pretest_content_revision.md)、[45](45_pretest_memory_distractors.md)を参照。

用語注釈はbackendの共通辞書処理へ分離し、教材生成・回答後解説の確定時と、テスト回答時に保存する。LLM・採点・診断の責務へ追加せず、frontendは保存された公開項目だけを表示する。新規登録は版26、旧版25以下は閲覧専用。[24](24_learning_glossary.md)。

現行仕様版26として、新規にexperiment-plan-2026-10-27-test-glossary-v2を保存する。旧プロトコルを並行稼働させず、版25以下・NULL・旧識別子の記録は閲覧専用にする。学習後のretest採点回数を新規参加者ごとに0から記録し、final_test込みの事前後テスト最大2回で未達終了する。学習後回数の保存列は維持し、上限用の回数は導出する。確定判断は[20](20_experiment_plan_alignment.md)。

## 実装の責務

- core/experiment_spec：仕様版とprotocol_idの両方で進行可否を判定。
- services/experiment：固定採点、群別入力、教材・回答後解説、再学習、履歴保護。
- services/research_protocol：新アンケートの厳密型・必須/対象外判定、冪等な教材表示記録。
- services/hypothesis_metrics：6仮説の根拠・参加者値・群別記述集計・専用CSV。既存評価列と分離。
- ai：自由な章立て、本文証拠、群別allowlist、v7契約とv3taxonomy。AIBackendを経由しMockへ自動フォールバックしない。

## 追加するnullable列

仕様版26ではテスト注釈用のattempts.glossary_snapshot（JSON/JSONB）を追加する。既存行はNULLで保持し、補完しない。

participants.protocol_id/retest_cycles_completed、participant_surveys.survey_version/responses_json、tutor_turns.material_viewed_at、evaluation_summaries.hypothesis_metrics_json。SQLite/PostgreSQLの不足列追加で移行し、既存行の回数・版・protocol_idを補完しない。

## 切替

1. 実行中リクエスト・workerを停止してから更新・再起動する。
2. DBを保全し、新版の問題を別construct_keyでseedする。旧問題・選択肢は非activeにするだけで本文を上書きしない。旧記録の再開/再送/削除/再計算が拒否されることを確認する。
3. 新規IDを作り、protocol_id、AIモデル/effort、RAG、アンケート版を確認する。
4. 試験データは隔離DBで扱い、研究収集DBへ混ぜない。
5. デバッグ正答配置・管理アクセス等の未解決事項を確認する。

旧列・生AIログ・固定統合CSVヘッダは維持する。教材内transfer_checkは独立した追加テストにしない。
