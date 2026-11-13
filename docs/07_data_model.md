# 現行データと履歴互換

## 仕様版54の現行条件

`Participant.protocol_id`は160文字まで保存する。PostgreSQLで既存列が短い場合は起動時に160文字へ拡張し、既存のprotocol ID値は変更しない。

現行Participantは仕様版54 / `experiment-plan-2026-11-12-four-topic-instruction-tuning-perfect-test-early-exit-posttest-material-amount-clarity-removal-v1`を使用する。新規Participantの`test_content_mode`は`four_topic_fundamentals`に固定し、問題バンク`split-actions-four-topic-v3`、事前版`presurvey-four-topic-baseline-v4`、事後版`posttest-5point-v4`を使う。4用語版の回答キーは`instruction_tuning`。アンケートは既存`ParticipantSurvey`の`phase`、`survey_version`、`responses_json`へ保存し、DB列は追加しない。旧版と保存値は変換せず保持する。教材評価は整数1〜5または`not_applicable`、未閲覧者は教材評価全体をJSON nullとする。現行指標H4は事後phaseの教材評価6項目を個別集計する。仕様版53以下は参加者操作を読み取り専用とし記録を変更しない。例外として仕様版52の対応する2 protocolは既存サマリーを上書きせずH1〜H4評価サマリーだけを追加できる。仕様版51以下と未対応protocolは再計算対象外。[事前アンケート](49_presurvey_baseline.md)、[4用語版](51_four_topic_foundation_mode.md)、[事後アンケート](52_posttest_five_point_evaluation.md)、[指標](12_evaluation_metrics.md)。

## 仕様版48の条件（履歴）

仕様版48 / `experiment-plan-2026-11-10-presurvey-exposure-understanding-split-v1`では、既存のphase別`ParticipantSurvey`へアンケート版とJSON回答を保存する。標準2モードの版は`presurvey-baseline-v3`、4用語版は`presurvey-four-topic-baseline-v2`。経験回答が`experienced`のときだけ理解度を必須とし、それ以外は理解度をnullにする。事前満点時の遷移は仕様版47で導入した経路を引き継ぎ、既存Attempt、`Participant.current_step`、結果表示snapshotを使用する。Participant/Attemptに列を追加せず、既存回答も書き換えない。仕様版47以下の記録は閲覧専用で保全する。

## 仕様版46の4用語版進行（履歴）

仕様版46では未設定時の問題モードを4用語版とし、4用語版のみ満点でも事前テスト後と再テスト1後に学習へ進んだ。誤答対象がない満点回は4用語すべてを学習対象にし、再テスト2の採点後はsurveyへ進んだ。

## 仕様版44・45の問題モードsnapshot（履歴）

（仕様版44・45採用時の履歴）`Participant.test_content_mode` / `RuntimeSetting.test_content_mode`を再利用し、新しい列は追加しない。RuntimeSettingの保存値を新規Participantへ登録時snapshotし、未設定時は`four_topic_fundamentals`とした。2026-11-12以降の新規登録ではRuntimeSettingを参照せず、4用語版に固定する。既存ParticipantのNULLやモードは補完せず、管理設定変更も遡及させない。仕様版44で導入した問題は独立したconstruct key・問題IDとAttempt snapshotから復元する。ログ・参加者CSV/Excel・仮説指標には既存の`test_content_mode`を含め、4用語版の分母は4問・4用語とする。[詳細](51_four_topic_foundation_mode.md)。

## 仕様版43の問題モードsnapshot（導入時・履歴）

`Participant.test_content_mode`と`RuntimeSetting.test_content_mode`をnullable VARCHAR(32)で保持する。RuntimeSettingは登録前の既定選択を保存し、新規Participantへ登録時の値をsnapshotする。許容値は`application`と`basic_understanding`、未設定時は`application`。起動時列追加は再実行可能で、既存ParticipantのNULLは補完しない。42以下のNULLは従来`split-actions-v5`として結果を復元する。参加者一覧・個別ログ・管理ログAPIと参加者／回答CSVにはモードを含める。仕様版43の仮説集計はモード別で、モード間の合算をしない。詳細は[50](50_basic_understanding_question_mode.md)。

## 仕様版42のテスト設定snapshot（履歴）

新規参加者は`show_pretest_results=false`、`show_retest_results=false`、`show_question_reviews=true`、`first_question_only=true`をParticipantへ登録時に保存する。登録処理はRuntimeSettingの旧設定値を読まず、対応する管理設定GET/PUT APIも提供しない。`RuntimeSetting.show_pretest_results`、`show_question_reviews`、`first_question_only`およびParticipantの各snapshot列はDB互換性と履歴監査のため残し、既存行を書き換えない。参加者一覧と個別ログ画面ではこれらの履歴値を表示しないが、管理ログAPIと参加者CSVには保存値を維持する。集計は仕様版42の3問条件に固定し、画面上の条件セレクターは設けない。仕様版41以下は閲覧専用。

## 教材用語解説モードの保存（仕様版29）

`RuntimeSetting.learning_material_glossary_mode`と`Participant.learning_material_glossary_mode`はnullable VARCHAR(32)として保持する。仕様版39以降、新規登録ではRuntimeSetting列を参照せず`integrated_material`をParticipantへ固定保存する。RuntimeSetting列は旧設定値の履歴保全用に残し、管理APIからは変更できない。既存ParticipantのモードとNULLは書き換えない。仕様版41以下は閲覧専用で再開できない。participants CSVと管理ログAPIにはParticipantの保存値を含めるが、参加者一覧・個別ログ画面には表示しない。旧NULLは「未記録（旧仕様）」として扱う。

## 仕様版28の答え合わせ保存

RuntimeSetting.show_question_reviewsとParticipant.show_question_reviewsはnullableで保存する。Attempt.question_review_acknowledged_atもnullableで、仕様版43の新規参加者は出題する設問1のAttemptに答え合わせ確認時刻を保存する。新規参加者はtrueへ固定する。旧行は補完しない。participant logs APIとparticipants CSVにshow_question_reviewsを含め、管理画面の一覧・個別ログ表示からは除く。確認時刻は既存のvalue_json形式で記録する。統合ログCSVは仕様版43で`test_content_mode`列を追加し、従来列を維持する。実装契約は[40](40_question_pair_answer_review.md)。

## テスト結果表示snapshot（issue-233）

`Participant.show_pretest_results`と`Participant.show_retest_results`はnullable Boolean。仕様版43の新規参加者は両方falseへ固定する。旧RuntimeSetting設定APIは廃止するが、RuntimeSettingの各列は履歴保全のため残し、新規登録では参照しない。既存参加者の値は補完・更新しない。旧snapshotのNULLは従来どおり表示ありとして扱う。participant logs API・participants CSVに両方の設定値を出すが、参加者一覧・個別ログ画面には表示しない。

## 用語注釈snapshot（仕様版26）

テスト用にAttempt.glossary_snapshotへnullable JSON列を追加し、旧行はNULLで保持する。教材・解説は従来どおりTutorTurn.diagnosis_json.material_glossaryとgrading_json.feedback_glossaryにversion、dictionary_sha256、entries（id/term/definition、表示順）を保存する。教材・解説は先行生成を含め新規生成時に作り、再取得・再送で再計算しない。テストは出題GETで不変辞書から導出し、回答時に保存する。未回答画面取得はDBへ書き込まない。回答済みの再取得・再送は保存値を使う。管理ログとCSVのvalue_jsonに同じsnapshotを出す。旧記録の補完・再解析は行わず、表示に供した内容の記録を読了証明とはしない。[24](24_learning_glossary.md)。

## 収集内容と版付き保存

計画書では参加者・群・用語・フェーズ/回次、問題と選択内容、全体正誤とunknown区分、誤答タイプ・再発、時刻/時間、段階・方略、完了/中断、AI実行状態、アンケートを収集する。正誤のboolとunknown分類は別の記録であり、保存型を文書だけで三値へ変更しない。

仕様版48でアンケートを事前・事後phaseに分け、仕様版49で事後版を5段階化し、仕様版50・51で事前質問文と4用語版用語、仕様版52・53で事後アンケートと早期終了条件を別protocolとして更新した。仕様版54で満点後早期終了と事後アンケートv4を統合した。現行事前phaseは用語ごとの見聞き経験・条件付き理解度、直近30日のAI利用日数、3行動の使いこなし自己評価で、問題モードごとに事前版を固定する。既存ParticipantSurvey.phase、survey_version、responses_jsonへ保存し、新DB列は追加しない。旧回答や旧posttest版は新規入力に使わず、既存JSONを変換しない。現行H4は事後phaseの教材評価を対象とし、事前回答は含めない。詳細は[12](12_evaluation_metrics.md)、[49](49_presurvey_baseline.md)、[52](52_posttest_five_point_evaluation.md)。

## 現行の保存契約

モデルの正本は`backend/app/models/__init__.py`。現行コードは仕様版54 / `experiment-plan-2026-11-12-four-topic-instruction-tuning-perfect-test-early-exit-posttest-material-amount-clarity-removal-v1`を使用する。新規Participantの`test_content_mode`は`four_topic_fundamentals`に固定し、`split-actions-four-topic-v3`を使う。`application`=`split-actions-v5`、`basic_understanding`=`split-actions-basic-v1`は既存参加者の履歴復元用に保持し、新規登録モードとしては選択しない。保存済みprotocolに対応する問題・アンケート版を使い、既存のNULLは補完しない。アンケートのphase/version別保存とJSON snapshotを保持する。仕様版53以下は参加者操作をread-onlyとし、問題・回答・snapshotを変更しない。仕様版52の対応する2 protocolは既存サマリーを上書きせずH1〜H4評価サマリーだけを追加でき、仕様版51以下・未対応protocolは再計算しない。`question_options.rationale`は内部メタデータで表示APIに含めない。研究用コードは登録中に検証後破棄し、DB列を追加しない。外部対応表はアプリDBモデルに含めない。詳細は[問題モード](50_basic_understanding_question_mode.md)、[4用語版](51_four_topic_foundation_mode.md)、[事前アンケート](49_presurvey_baseline.md)、[事後アンケート](52_posttest_five_point_evaluation.md)。
2026-10-21追加: participantsにnullableのconsent_document_version / consented_atを追加する。新規登録だけconsent-2026-10-21-draft-v1と同意時刻を保存し、既存行はNULLのままにする。実験仕様版・protocol_id・既存CSVヘッダは変更しない。

2026-10-21時点の履歴: 学籍番号はSQLAlchemyの研究DBへ追加せず、IDENTITY_MAPPING_PATHが指す別SQLiteの`identity_mappings`へ保存した。当時は対応表APIも存在した。現在は管理画面/APIを廃止し、既存SQLiteファイルと行は登録・通常起動では参照・移行・変更・削除しない。明示的な参加者削除時に限り、既存ファイル内の対象participant_idの旧行をcleanupする。

2026-11-11までの旧登録方式では、研究用コードを分離SQLiteの`research_code_mappings`へ保存し、管理UI/APIから参照していた。この段落は履歴であり、現在の登録仕様ではない。現行登録は研究用コードを半角数字1〜64桁として検証するだけで、参加者作成後は値を保持しない。研究DB、冪等性request_hash/response_json、ログ、CSV/XLSX、AI入力、ブラウザ永続領域には保存しない。研究用コードと学籍番号はアプリで照合しない。対応表は研究者がアプリ外で作成・保管する。旧IDENTITY_MAPPING_PATHのSQLiteファイル・テーブル・既存行は登録・通常起動・管理APIから参照、移行、変更、削除しない。アプリ内管理API/UIは廃止済み。明示的に参加者を削除する場合のみ、既存SQLiteがあるとき当該participant_idに一致する旧行のcleanupを再試行可能な削除outbox経由で行う。

参加者の明示的削除では、研究DB内の関連データ削除と`AuditEvent.after_json.identity_mapping_cleanup=pending`を同じトランザクションで確定してから、既存の別SQLiteが存在する場合に限り、旧学籍番号対応表・研究用コード対応表のうち当該participant_idの行だけを削除する。ファイルがない場合は新規作成しない。他の参加者の行と外部Excel対応表は変更しない。cleanup後に監査記録を`complete`へ更新する。途中停止時はpending記録を起動時または同じ削除APIの再送で再試行する。研究DBの確定に失敗した場合は旧ファイルに触れない。外部Excel対応表・USB・バックアップ上のデータは研究者が別途処理する。

モデルの正本は `backend/app/models/__init__.py`。participants.retest_cycles_completed、participants.protocol_id、participant_surveys.survey_version/responses_json、tutor_turns.material_viewed_at、evaluation_summaries.hypothesis_metrics_jsonをnullableで追加する。新規テーブル・尺度変換・旧行のprotocol_id補完はない。既存参加者のretest_cycles_completedは保存値のまま保持し、過去回数の推定や補完はしない。

現行コードでは新規Participantだけ仕様版54と統合protocolを保存し、教材内解説モード、テスト表示・答え合わせ条件、選択肢配置、`test_content_mode=four_topic_fundamentals`、`retest_cycles_completed=0`を固定する。RuntimeSettingの問題モードは登録時に参照しない。研究用コードは登録中に検証後破棄し、アプリには保存しない。事後アンケート版`posttest-5point-v4`を保存する。全問採点後に満点となったテストは既存の`current_step`・Attempt・結果表示snapshotを使って早期終了し、列追加や旧行補完は行わない。仕様版53以下の参加者操作は読み取り専用とするが、仕様版52の対応2 protocolに限り既存サマリーを上書きしないH1〜H4評価サマリー追加を許可する。仕様版51以下・未対応protocolは再計算しない。起動時補修は仕様版とprotocol_idの両方で対象を限定する。

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

生AIログと問題snapshotは過去内容もそのまま閲覧・CSV出力可能。統合ログCSVは仕様版43で`test_content_mode`列を追加し、それ以外の既存列と過去値を保持する。全体ログ・参加者ログと仮説集計にはCSVに対応した個別`.xlsx`出力もあり、各ブックは同じ列・行の1シート構成である。仕様版45の固定2回進行も既存の回数列で表し、DB構造を変更しない。詳細な旧テーブル仕様は [履歴資料](history/2026-10-06/07_data_model.md)。

旧回答の問題文・選択肢本文は保存時snapshotを優先する。旧自由回答採点のexpected_keywords列もlegacy_*マッピングとして保持し、新しいseedから更新しない。

## 問題版の保存

仕様版54の新規登録・出題・採点・確認問題復元は`test_content_mode=four_topic_fundamentals`に固定し、問題バンク`split-actions-four-topic-v3`を使う。`application`（`split-actions-v5`）と`basic_understanding`（`split-actions-basic-v1`）の資産は既存Participantの履歴復元用に保持し、新規登録モードとしては選択しない。仕様版51〜53のprotocolに応じv2/v3など当時のバンクを復元し、仕様版50以下は対応protocolに保存された版を使う。過去の問題は版付きconstruct_keyと回答snapshotから復元し、別バンクへフォールバックしない。旧`question_set_mode`の整理は別の履歴変更であり、通常版の問題資産や`test_content_mode`を削除しない。
