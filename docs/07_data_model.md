# 現行データと履歴互換

## 収集内容と版付き保存

計画書では参加者・群・用語・フェーズ/回次、問題と選択内容、全体正誤とunknown区分、誤答タイプ・再発、時刻/時間、段階・方略、完了/中断、AI実行状態、アンケートを収集する。正誤のboolとunknown分類は別の記録であり、保存型を文書だけで三値へ変更しない。

現行アンケートは経験4有無、一般4/教材6の1〜10段階、必須自由記述。ParticipantSurvey.survey_versionとresponses_jsonへ版付きで保存し、旧5段階列は新規入力に使わない。定義は[12](12_evaluation_metrics.md)。

## 現行の保存契約

モデルの正本は `backend/app/models/__init__.py`。実験仕様版3を維持する。参加者の `option_order_mode` nullable列は既存DBへ軽量移行で追加し、既存行はNULLのままdebug_fixedとして扱う。RuntimeSettingの単一行テーブルを追加する。その他の版付き列に尺度変換や旧行のprotocol_id補完は行わない。
2026-10-21追加: participantsにnullableのconsent_document_version / consented_atを追加する。新規登録だけconsent-2026-10-21-draft-v1と同意時刻を保存し、既存行はNULLのままにする。実験仕様版・protocol_id・既存CSVヘッダは変更しない。

学籍番号はSQLAlchemyの研究DBへ追加しない。IDENTITY_MAPPING_PATHが指す別SQLiteへ、学籍番号・参加者ID・表示コード・作成日時・再送処理用キーを保存する。研究用エクスポート・AI入力・AIログ・冪等性のrequest_hash/response_jsonには学籍番号を含めない。ブラウザには再送キーだけを保存し、登録本文を永続保存しない。対応表SQLiteはsecure_deleteを有効にし、対応表の削除は研究データに影響しない。別DB間には分散トランザクションがないため、登録は対応表を先行保存してから研究DBを確定し、通常の失敗では補償削除する。強制終了で残った未確定対応行は一覧/CSVに出さず、同じ登録キーの再試行で置換するか全件削除で消去する。

参加者の撤回削除では、研究DB内の関連データ削除と`AuditEvent.after_json.identity_mapping_cleanup=pending`を同じトランザクションで確定してから、別SQLiteの対応表を削除する。対応表削除後に監査記録を`complete`へ更新する。途中停止・対応表DB障害時はpending記録を起動時に再試行し、同じ削除APIの再送でも完了できる。研究DBの確定に失敗した場合は対応表を削除しない。これは分散トランザクションではなく、研究DBに保存する再試行可能な削除outboxで障害窓を回復する方式である。

モデルの正本は `backend/app/models/__init__.py`。実験仕様版3を維持し、participants.protocol_id、participant_surveys.survey_version/responses_json、tutor_turns.material_viewed_at、evaluation_summaries.hypothesis_metrics_jsonをnullableで追加する。新規テーブル・尺度変換・旧行のprotocol_id補完はない。

新規参加者だけ仕様版3とexperiment-plan-2026-10-18-v1を保存する。既存版3を含む異なるprotocol_idの記録は変更しない。旧試用は進行・採点・完了更新・削除・評価再計算を禁止する。起動時補修も仕様版とprotocol_idの両方へ限定する。

現行の主な保存対象:

- Participant: 群、同意、進捗、開始・完了時刻、終了理由、実験仕様版、開始時に確定した選択肢配置モード。
- RuntimeSetting: ID=1の単一行に、今後作成する参加者へ適用する選択肢配置モードを保存する。未設定時の既定値は `debug_fixed`。
- Attempt: 問題ID、複数選択ID、フェーズ・周回、正誤・M1/M3/unknown、問題/選択肢snapshot、時刻。選択肢snapshotには参加者に表示したラベル・本文・順序を保存する。
- LearnerState: 現在状態、主分類、方略、正答記録数、再発数、最終回答ID。
- TutorSession / TutorTurn: 教材・固定問題snapshot、回答・解説、採点JSON、生成契約・版・検証・先行生成監査。学習確認問題snapshotにも表示時の選択肢ラベル・本文・順序を保存する。
- AICallLog: 実送信prompt・Schema・モデル・推論設定、RAG指紋、試行・検証結果、生応答。
- EvaluationSummary: 現行スコア、同種再発、時系列・学習負担・条件確認JSON。

interaction_historyは既存Attempt/TutorTurnの採点済みsnapshotから読み出し、別テーブルへ複製しない。同じ参加者・用語の全周回を時系列で統合し、共通allowlistで診断・教授メタデータを除く。内部IDは並び順と参照照合にだけ使い、モデルへ送らない。

既存JSONへinteraction-history-v1の件数/SHA-256、shared-diagnosis-route-v1、仕様版3を保存する。AICallLog.request_payload.input_projectionはサーバー側の入力投影であり、実送信はeffective_requestとtransmissionを確認する。Mockの投影を実app-server送信とみなさない。

章立て監査は既存のAICallLog.response_payload.generation_validation.material_structureとTutorTurn.diagnosis_json.material_structure_validationに保存する。見出し・順序・節数・本文文字数・必須証拠配置（節番号）・検証結果を含み、DB列追加はしない。重複見出しは節番号で区別する。旧教材と旧監査JSONは再解析・書換えせず保持する。

本文証拠はTutorTurn.diagnosis_jsonとAICallLog.response_payloadへ保存し、参加者に表示しない。unknownはmandatory_elements.definition、teaching_contract.mechanism_explanation/transfer_checkを検査する。旧6項目の過去JSONは書き換えない。

旧列は物理削除しない。ORM名を `legacy_*` にして履歴読出しへ隔離する。新規レコードの旧NOT NULL列には `not_applicable`、0、falseなどの中立値を設定するだけで、教授・採点には参照しない。過去値は保持する。

現在のPython/API名 `attainment_correct_rate` は物理列 `l0_correct_rate` にマッピングする。新規計算はAttempt.is_correctだけを使う。旧保存値は `legacy_fields` 内にも表示できるが再計算しない。

生AIログと問題snapshotは過去内容もそのまま閲覧・CSV出力可能。統合ログCSVの固定ヘッダは変更しない。詳細な旧テーブル仕様は [履歴資料](history/2026-10-06/07_data_model.md)。

旧回答の問題文・選択肢本文は保存時snapshotを優先する。旧自由回答採点のexpected_keywords列もlegacy_*マッピングとして保持し、新しいseedから更新しない。
