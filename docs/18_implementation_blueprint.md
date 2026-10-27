# 現行プロトコルの実装境界

用語注釈はbackendの共通辞書処理へ分離し、教材生成・回答後解説の確定時に保存する。LLM・採点・診断の責務へ追加せず、frontendは保存された公開項目だけを表示する。新規登録は版25、旧版24以下は閲覧専用。[24](24_learning_glossary.md)。

現行仕様版25として、新規にexperiment-plan-2026-10-27-round2-revision-v1を保存する。旧プロトコルを並行稼働させず、版24以下・NULL・旧識別子の記録は閲覧専用にする。学習後のretest採点回数を新規参加者ごとに0から記録し、final_test込みの事前後テスト最大2回で未達終了する。学習後回数の保存列は維持し、上限用の回数は導出する。確定判断は[20](20_experiment_plan_alignment.md)。

## 実装の責務

- core/experiment_spec：仕様版とprotocol_idの両方で進行可否を判定。
- services/experiment：固定採点、群別入力、教材・回答後解説、再学習、履歴保護。
- services/research_protocol：新アンケートの厳密型・必須/対象外判定、冪等な教材表示記録。
- services/hypothesis_metrics：6仮説の根拠・参加者値・群別記述集計・専用CSV。既存評価列と分離。
- ai：自由な章立て、本文証拠、群別allowlist、v7契約とv3taxonomy。AIBackendを経由しMockへ自動フォールバックしない。

## 追加するnullable列

participants.protocol_id/retest_cycles_completed、participant_surveys.survey_version/responses_json、tutor_turns.material_viewed_at、evaluation_summaries.hypothesis_metrics_json。SQLite/PostgreSQLの不足列追加で移行し、既存行の回数・版・protocol_idを補完しない。

## 切替

1. 実行中リクエスト・workerを停止してから更新・再起動する。
2. DBを保全し、新版の問題を別construct_keyでseedする。旧問題・選択肢は非activeにするだけで本文を上書きしない。旧記録の再開/再送/削除/再計算が拒否されることを確認する。
3. 新規IDを作り、protocol_id、AIモデル/effort、RAG、アンケート版を確認する。
4. 試験データは隔離DBで扱い、研究収集DBへ混ぜない。
5. デバッグ正答配置・管理アクセス等の未解決事項を確認する。

旧列・生AIログ・固定統合CSVヘッダは維持する。教材内transfer_checkは独立した追加テストにしない。
