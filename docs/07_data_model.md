# 現行データと履歴互換

## 仕様版40のテスト設定snapshot

新規参加者は`show_pretest_results=false`、`show_retest_results=false`、`show_question_reviews=true`、`first_question_only=true`をParticipantへ登録時に保存する。登録処理はRuntimeSettingの旧設定値を読まず、対応する管理設定GET/PUT APIも提供しない。`RuntimeSetting.show_pretest_results`、`show_question_reviews`、`first_question_only`およびParticipantの各snapshot列はDB互換性と履歴監査のため残し、既存行を書き換えない。参加者一覧と個別ログ画面ではこれらの履歴値を表示しないが、管理ログAPIと参加者CSVには保存値を維持する。集計は仕様版40の3問条件に固定し、画面上の条件セレクターは設けない。仕様版39以下は閲覧専用。

## 教材用語解説モードの保存（仕様版29）

`RuntimeSetting.learning_material_glossary_mode`と`Participant.learning_material_glossary_mode`はnullable VARCHAR(32)として保持する。仕様版39以降、新規登録ではRuntimeSetting列を参照せず`integrated_material`をParticipantへ固定保存する。RuntimeSetting列は旧設定値の履歴保全用に残し、管理APIからは変更できない。既存ParticipantのモードとNULLは書き換えない。仕様版39以下は閲覧専用で再開できない。participants CSVと管理ログAPIにはParticipantの保存値を含め、参加者一覧・個別ログ画面には表示しない。旧NULLは「未記録（旧仕様）」として扱う。

## 仕様版28の答え合わせ保存

RuntimeSetting.show_question_reviewsとParticipant.show_question_reviewsはnullableで保存する。Attempt.question_review_acknowledged_atもnullableで、仕様版40の新規参加者は出題する設問1のAttemptに答え合わせ確認時刻を保存する。新規参加者はtrueへ固定する。旧行は補完しない。participant logs APIとparticipants CSVにshow_question_reviewsを含め、管理画面の一覧・個別ログ表示からは除く。統合ログCSVの固定ヘッダーは維持し、確認時刻は既存のvalue_json形式で記録する。実装契約は[40](40_question_pair_answer_review.md)。

## テスト結果表示snapshot（issue-233）

`Participant.show_pretest_results`と`Participant.show_retest_results`はnullable Boolean。仕様版40の新規参加者は両方falseへ固定する。旧RuntimeSetting設定APIは廃止するが、RuntimeSettingの各列は履歴保全のため残し、新規登録では参照しない。既存参加者の値は補完・更新しない。旧snapshotのNULLは従来どおり表示ありとして扱う。participant logs API・participants CSVに両方の設定値を出すが、参加者一覧・個別ログ画面には表示しない。

## 用語注釈snapshot（仕様版26）

テスト用にAttempt.glossary_snapshotへnullable JSON列を追加し、旧行はNULLで保持する。教材・解説は従来どおりTutorTurn.diagnosis_json.material_glossaryとgrading_json.feedback_glossaryにversion、dictionary_sha256、entries（id/term/definition、表示順）を保存する。教材・解説は先行生成を含め新規生成時に作り、再取得・再送で再計算しない。テストは出題GETで不変辞書から導出し、回答時に保存する。未回答画面取得はDBへ書き込まない。回答済みの再取得・再送は保存値を使う。管理ログとCSVのvalue_jsonに同じsnapshotを出す。旧記録の補完・再解析は行わず、表示に供した内容の記録を読了証明とはしない。[24](24_learning_glossary.md)。

## 収集内容と版付き保存

計画書では参加者・群・用語・フェーズ/回次、問題と選択内容、全体正誤とunknown区分、誤答タイプ・再発、時刻/時間、段階・方略、完了/中断、AI実行状態、アンケートを収集する。正誤のboolとunknown分類は別の記録であり、保存型を文書だけで三値へ変更しない。

仕様版37のアンケートは、事前phaseの4段階カテゴリによる用語事前知識6項目・AI利用2評定と、事後phaseのシステム評価2・教材評価6・任意自由記述に分ける。既存ParticipantSurvey.phase、survey_version、responses_jsonへ保存し、新DB列は追加しない。仕様版36のBoolean形式`presurvey-baseline-v1`回答や旧posttest v1/v2・旧5段階列は新規入力に使わず、既存JSONを変換しない。H5はposttest phaseだけを参照する。詳細は[12](12_evaluation_metrics.md)・[49](49_presurvey_baseline.md)。

## 現行の保存契約

モデルの正本は backend/app/models/__init__.py。現行コードは仕様版40 / `experiment-plan-2026-11-07-fixed-admin-settings-v1`を使用する。固定設定によるDB列・注釈JSON形式の変更はない。新規登録のモードは`integrated_material`、テスト設定4値は固定値をParticipantへ保存する。RuntimeSettingの旧設定列は保全目的で保持するが参照・更新しない。辞書v4と既存JSON snapshotは保持する。アンケートは既存のParticipantSurveyをphase/version別に使い、新DB列を追加しない。仕様版39以下・旧アンケート回答を不変で保持する。PRETEST改訂はversioned construct keyとYAMLバンクで分離し、旧問題と回答snapshotを保持する。仕様版36〜39の結果復元はsplit-actions-v5を使う。詳細は[教材モード](41_learning_glossary_material_mode.md)、[事前アンケート](49_presurvey_baseline.md)、[RAG注釈](49_rag_glossary.md)、[PRETEST履歴](44_pretest_content_revision.md)〜[追加選択肢](47_split_assessment_added_choices.md)。教材の文字数契約と言い換え条件は[42](42_learning_glossary_material_length.md)・[43](43_glossary_definition_paraphrase.md)を参照。参加者のoption_order_mode nullable列は既存DBへ軽量移行で追加し、既存行はNULLのままdebug_fixedとして扱う。その他の版付き列に尺度変換や旧行のprotocol_id補完は行わない。
2026-10-21追加: participantsにnullableのconsent_document_version / consented_atを追加する。新規登録だけconsent-2026-10-21-draft-v1と同意時刻を保存し、既存行はNULLのままにする。実験仕様版・protocol_id・既存CSVヘッダは変更しない。

学籍番号はSQLAlchemyの研究DBへ追加しない。IDENTITY_MAPPING_PATHが指す別SQLiteへ、学籍番号・参加者ID・表示コード・作成日時・再送処理用キーを保存する。研究用エクスポート・AI入力・AIログ・冪等性のrequest_hash/response_jsonには学籍番号を含めない。ブラウザには再送キーだけを保存し、登録本文を永続保存しない。対応表SQLiteはsecure_deleteを有効にし、対応表の削除は研究データに影響しない。別DB間には分散トランザクションがないため、登録は対応表を先行保存してから研究DBを確定し、通常の失敗では補償削除する。強制終了で残った未確定対応行は一覧/CSVに出さず、同じ登録キーの再試行で置換するか全件削除で消去する。

参加者の撤回削除では、研究DB内の関連データ削除と`AuditEvent.after_json.identity_mapping_cleanup=pending`を同じトランザクションで確定してから、別SQLiteの対応表を削除する。対応表削除後に監査記録を`complete`へ更新する。途中停止・対応表DB障害時はpending記録を起動時に再試行し、同じ削除APIの再送でも完了できる。研究DBの確定に失敗した場合は対応表を削除しない。これは分散トランザクションではなく、研究DBに保存する再試行可能な削除outboxで障害窓を回復する方式である。

モデルの正本は `backend/app/models/__init__.py`。participants.retest_cycles_completed、participants.protocol_id、participant_surveys.survey_version/responses_json、tutor_turns.material_viewed_at、evaluation_summaries.hypothesis_metrics_jsonをnullableで追加する。新規テーブル・尺度変換・旧行のprotocol_id補完はない。既存参加者のretest_cycles_completedは保存値のまま保持し、過去回数の推定や補完はしない。

現行コードでは新規参加者だけ仕様版40と`experiment-plan-2026-11-07-fixed-admin-settings-v1`を保存し、教材内解説モード、4つのテスト設定、retest_cycles_completed=0を固定する。仕様版39以下・異なるprotocol_idの記録は変更しない。旧試用は進行・採点・完了更新・削除・評価再計算を禁止する。起動時補修も仕様版とprotocol_idの両方へ限定する。

現行の主な保存対象:

- Participant: 群、同意、進捗、開始・完了時刻、終了理由、実験仕様版、開始時に確定した選択肢配置・教材用語解説モード、学習後retestの採点済み回数。
- RuntimeSetting: ID=1の単一行に、今後作成する参加者へ適用する選択肢配置を保存する。未設定時の配置既定値は `debug_fixed`。教材用語解説モード列は旧値保全のため残すが、現行コードは参照・更新しない。
- Attempt: 問題ID、複数選択ID、フェーズ・周回、正誤・M1/M3/unknown、問題/選択肢snapshot、時刻。選択肢snapshotには参加者に表示したラベル・本文・順序を保存する。
- LearnerState: 現在状態、主分類、方略、正答記録数、再発数、最終回答ID。
- TutorSession / TutorTurn: 教材・固定問題snapshot、回答・解説、採点JSON、生成契約・版・検証・先行生成監査。学習確認問題snapshotにも表示時の選択肢ラベル・本文・順序を保存する。
- AICallLog: 実送信prompt・Schema・モデル・推論設定、RAG指紋、試行・検証結果、生応答。
- EvaluationSummary: 現行スコア、同種再発、時系列・学習負担・条件確認JSON。

interaction_historyは既存Attempt/TutorTurnの採点済みsnapshotから読み出し、別テーブルへ複製しない。同じ参加者・用語の全周回を時系列で統合し、共通allowlistで診断・教授メタデータを除く。内部IDは並び順と参照照合にだけ使い、モデルへ送らない。

既存JSONへinteraction-history-v1の件数/SHA-256、shared-diagnosis-route-v1、仕様版26を保存する。AICallLog.request_payload.input_projectionはサーバー側の入力投影であり、実送信はeffective_requestとtransmissionを確認する。Mockの投影を実app-server送信とみなさない。

`retest_cycles_completed`は学習後のretest採点バッチ数で、final_testを含めない。上限用のpost_pretest_tests_completedはこの値に採点済みfinal_testの有無（0/1）を加えて導出し、DB列を増やさない。事前後の共通上限は2回、事前込み最大3回。冪等再送では加算せず、未達状態を習得済みへ変更しない。旧版の保存値を推定・補完しない。

旧v8はarchive/learning_content_scenario_actions_v8.ymlに保全する。新問題はconstruct_keyにscenario-actions-v9を付けてseedし、旧Question/QuestionOptionの本文と判定情報を上書きせず非activeにする。旧snapshotがない回答も旧IDの内容を参照する。seed再実行で新問題を重複作成しない。

章立て監査は既存のAICallLog.response_payload.generation_validation.material_structureとTutorTurn.diagnosis_json.material_structure_validationに保存する。見出し・順序・節数・本文文字数・必須証拠配置（節番号）・検証結果を含み、DB列追加はしない。重複見出しは節番号で区別する。旧教材と旧監査JSONは再解析・書換えせず保持する。

本文証拠はTutorTurn.diagnosis_jsonとAICallLog.response_payloadへ保存し、参加者に表示しない。unknownはmandatory_elements.definition、teaching_contract.mechanism_explanation/transfer_checkを検査する。旧6項目の過去JSONは書き換えない。

旧列は物理削除しない。ORM名を `legacy_*` にして履歴読出しへ隔離する。新規レコードの旧NOT NULL列には `not_applicable`、0、falseなどの中立値を設定するだけで、教授・採点には参照しない。過去値は保持する。

現在のPython/API名 `attainment_correct_rate` は物理列 `l0_correct_rate` にマッピングする。新規計算はAttempt.is_correctだけを使う。旧保存値は `legacy_fields` 内にも表示できるが再計算しない。

生AIログと問題snapshotは過去内容もそのまま閲覧・CSV出力可能。統合ログCSVの固定ヘッダは変更しない。詳細な旧テーブル仕様は [履歴資料](history/2026-10-06/07_data_model.md)。

旧回答の問題文・選択肢本文は保存時snapshotを優先する。旧自由回答採点のexpected_keywords列もlegacy_*マッピングとして保持し、新しいseedから更新しない。

## 問題版の保存

現行アプリは通常版だけを新規登録・出題に使用する。ParticipantとRuntimeSettingの旧question_set_mode列は専用の削除処理で物理削除する。通常版の履歴問題は版付きconstruct_keyと保存snapshotから復元し、版の異なる問題へフォールバックしない。
