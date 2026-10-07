# 07. Data Model

Docker ComposeではPostgreSQL 16、ローカル直接起動ではSQLiteを使用する。SQLAlchemyの同期engineで接続し、起動時は `Base.metadata.create_all` と互換用の不足列追加を行う。Alembicによるマイグレーションは現行起動経路では使用しない。モデル上のIDは36文字の文字列（SQLAlchemyの `String(36)`）として保存し、構造化列はSQLAlchemyのJSON型である。

## Enum Values

以下はコード上で使用する文字列列の論理値・互換値を整理したものであり、DBのenum制約ではない。現行のAttempt APIで受け付けるフェーズは`pretest`、`retest`、`l0_check`、`final_test`である。

### group_condition

- `control`
- `proposed`

参加者向けの作成APIは群名を直接受け付けない。管理者が伝える`assignment_code`のA/Bをbackendでそれぞれ`proposed`/`control`へ変換し、参加者行へ保存する。

### assignment_method

- `admin_code`（現行の`POST /api/participants`でA/Bコードから割り当てた値）
- `manual`（既存行・スキーマの互換値。現行の参加者作成画面では使用しない）
- `random`（過去ログ互換値。現行の参加者作成APIでは使用しない）

### phase

- `pretest`
- `diagnosis`  # AI自由回答・互換用の論理値。固定pretestの診断は`diagnose-pretest`で行う
- `learning`  # 学習ターンの論理値。学習確認問題は`questions`行ではなく`tutor_turns.practice_question_json`に保存する
- `retest`
- `l0_check`  # 互換・補助フェーズ。現行MVPの主導線は final_test
- `final_test`
- `transfer`  # 互換・補助フェーズ。現行主導線の開始・採点APIはない
- `delayed_retest`（将来対応。現行APIの主導線では未使用）

### test_round (`attempts`)

参加者ごとのテスト周回を記録する表示・分析用キー。`phase` は問題種別と既存API互換の内部値として残す。

- `test`（初回テスト。内部 `pretest`）
- `retest_1`（最初の学習後確認。通常は内部 `retest`。初回テストに学習対象がない場合は互換的に `final_test` を表示）
- `retest_2` 以降（追加学習後の再テスト周回）

### question_type

- `multi_select`
- `retest_multi_select`
- `final_multi_select`
- `learning_multi_select`
- `control_learning_multi_select`
- `l0_free_response`
- `transfer`

### misconception_type

- `M1`
- `M2`
- `M3`
- `M4`
- `unknown`
- `ambiguous`
- `null`

### diagnosed_status

- `unknown`
- `misconception`
- `unstable_correct`
- `stable_correct`
- `transfer_ready`
- `mastered`
- `needs_review`
- `ambiguous`

### scaffolding_level

- `L3`
- `L2`
- `L1`  # 過去データの互換値として残り得る。現行MVPの進行制御では使わない
- `null`  # 列定義上nullableな場合の値

`transfer_ready`、`mastered`、`needs_review`は過去または互換ログで保持し得るが、現行固定問題の主導線では直接生成しない。`ambiguous`は互換AI契約の値であり、固定採点では使わない。

## Tables

### participants

- id TEXT(36) PRIMARY KEY
- display_code TEXT UNIQUE NOT NULL
- group_condition TEXT NOT NULL
- assignment_method TEXT NOT NULL DEFAULT `manual`
- consent_checked BOOLEAN NOT NULL DEFAULT false
- current_step TEXT NOT NULL DEFAULT `start`
- learning_content_version INTEGER NULL  # 学習確認問題版。NULLは既存参加者用v1、参加者作成時はv2
- started_at TIMESTAMP NULL
- completed_at TIMESTAMP NULL
- completion_reason TEXT NULL  # `completed` または `give_up`
- created_at TIMESTAMP NOT NULL
- updated_at TIMESTAMP NOT NULL

`display_code` は `P001` のような画面表示用ID。個人名やメールアドレスは保存しない。

`assignment_method`のDBデフォルト`manual`は既存データおよび直接モデル作成との互換用に残る。現行の参加者作成APIはA/Bの`assignment_code`を必須とし、正常作成時は`admin_code`を書き込む。APIの参加者向けレスポンスには`group_condition`を含めないが、管理API・ログ・評価集計では内部群として利用する。

`current_step` は`pretest`、`learning_targets`、`retest`、`final_test`、`survey`、`l0_check`、`finish`を使用する。`retest`は学習ギブアップ直後に再テストへ進むための状態である。

`completion_reason` は実験終了時の理由を保存する。通常終了は`completed`、実験ギブアップは`give_up`であり、学習セッションだけをギブアップした場合は未終了のためNULLのままとする。学習ギブアップ回数や操作時刻は`audit_events`の`give_up_learning`で記録する。

`learning_content_version`は参加者単位で学習確認問題セットを固定する。既存DBへの列追加はnullableで行い、既存行のNULLはv1として扱う。新規参加者は作成時にv2を保存する。各`TutorTurn.diagnosis_json`にも実際に提示した版を記録し、回答時は参加者列ではなく提示ターンの版を優先して採点する。pretest、retest、final_testの問題セットには適用しない。

`current_stage_for_display` は `learner_states.current_status` と `primary_misconception` を優先して決める。不正解・unknownはそれぞれ「概念変化」・「豊富化」とし、`scaffolding_level`は正答状態などのフォールバックにだけ使う。これにより、L2/L3の保存値だけから学習段階を逆算して誤表示しない。

### participant_surveys

実験後アンケート用のモデル。`/survey` には仮フォームを表示し、送信時に`phase=posttest`として保存してから参加者を`finish`へ進める。

- id TEXT(36) PRIMARY KEY
- participant_id TEXT(36) REFERENCES participants(id)
- phase TEXT NOT NULL
- ai_experience_level INT NULL
- programming_experience_level INT NULL
- llm_usage_level INT NULL
- self_rated_ai_knowledge INT NULL
- term_confidences JSON NULL
- usability_rating INT NULL
- helpfulness_rating INT NULL
- perceived_hint_amount INT NULL
- free_comment TEXT NULL
- created_at TIMESTAMP NOT NULL

### terms

- id TEXT(36) PRIMARY KEY
- slug TEXT UNIQUE NOT NULL
- label TEXT NOT NULL
- description TEXT
- display_order INT NOT NULL
- is_active BOOLEAN NOT NULL DEFAULT true
- created_at TIMESTAMP NOT NULL

### term_assignments

現行MVPでは、診断後に学習対象として残す用語と優先度を参加者ごとに保存する。`group_condition` は参加者の条件と同じ値になる。参加者内比較で用語ごとに条件を変える用途は将来拡張である。

- id TEXT(36) PRIMARY KEY
- participant_id TEXT(36) REFERENCES participants(id)
- term_id TEXT(36) REFERENCES terms(id)
- group_condition TEXT NOT NULL
- is_learning_target BOOLEAN NOT NULL DEFAULT false
- selection_reason TEXT NULL
- priority_score FLOAT NULL
- created_at TIMESTAMP NOT NULL

### questions

- id TEXT(36) PRIMARY KEY
- term_id TEXT(36) REFERENCES terms(id)
- phase TEXT NOT NULL
- question_type TEXT NOT NULL
- body TEXT NOT NULL
- expected_answer TEXT NULL
- expected_keywords JSON NULL
- difficulty INT DEFAULT 1
- construct_key TEXT NOT NULL
- variant_key TEXT NOT NULL
- is_active BOOLEAN DEFAULT true
- created_at TIMESTAMP NOT NULL

`construct_key` は同じ構成概念を測る問題を束ねるキー。事前テストと再テストは同じ `construct_key` だが、`variant_key` と `body` は異なる。

学習確認問題はseed時に`questions`へ投入しない。`generate_tutor_turn`が参加者の`learning_content_version`に対応するYAMLの学習段階・用語別定義から固定の問題・選択肢を組み立て、AI生成教材とともに`tutor_turns.practice_question_json`へ保存する。既存参加者のNULL版はv1として扱い、新規参加者は作成時にv2へ固定する。回答採点では、参加者列よりも提示済みターンに記録した版を優先する。

### question_options

- id TEXT(36) PRIMARY KEY
- question_id TEXT(36) REFERENCES questions(id)
- option_label TEXT NOT NULL
- body TEXT NOT NULL
- is_correct BOOLEAN NOT NULL
- misconception_type TEXT NULL
- rationale TEXT NULL
- default_order INT
- created_at TIMESTAMP NOT NULL

misconception_type values:

- M1
- M2
- M3
- M4
- unknown
- ambiguous
- null

### question_display_orders

複数選択以外の問題で行う選択肢ランダム化の再現性を保存する。固定複数選択のA〜J順はランダム化しない。

- id TEXT(36) PRIMARY KEY
- participant_id TEXT(36) REFERENCES participants(id)
- question_id TEXT(36) REFERENCES questions(id)
- option_order JSON NOT NULL
- random_seed TEXT NOT NULL
- created_at TIMESTAMP NOT NULL

### attempts

- id TEXT(36) PRIMARY KEY
- participant_id TEXT(36) REFERENCES participants(id)
- term_id TEXT(36) REFERENCES terms(id)
- question_id TEXT(36) REFERENCES questions(id)
- phase TEXT NOT NULL
- test_round TEXT NULL  # test, retest_1, retest_2, ...
- attempt_index INT NOT NULL DEFAULT 1
- selected_option_id TEXT(36) NULL REFERENCES question_options(id)  # 旧互換列
- selected_option_ids JSON NULL  # 現行の複数選択正本
- free_text_answer TEXT NULL
- reason_text TEXT NULL  # pretestでは常にNULL
- confidence INT NULL  # legacy nullable; pretestとlearningでは収集しない
- response_time_sec FLOAT NULL
- question_shown_at TIMESTAMP NULL
- answered_at TIMESTAMP NULL
- question_body_snapshot TEXT NULL
- option_order_snapshot JSON NULL
- is_correct BOOLEAN NULL
- score FLOAT NULL
- diagnosed_status TEXT NULL
- misconception_type TEXT NULL
- secondary_misconception_type TEXT NULL
- misconception_confidence FLOAT NULL
- natural_language_diagnosis TEXT NULL
- recurrence_flag BOOLEAN NOT NULL DEFAULT false
- l0_success BOOLEAN NULL
- transfer_success BOOLEAN NULL
- requires_manual_review BOOLEAN NOT NULL DEFAULT false
- idempotency_key TEXT NULL
- created_at TIMESTAMP NOT NULL
- updated_at TIMESTAMP NOT NULL

`question_shown_at` と `answered_at` はクライアントが送るISO時刻を保存する。`created_at` はサーバーが回答を保存した時刻であり、回答所要時間の分析には `response_time_sec` を優先する。`question_body_snapshot` と `option_order_snapshot` は、seedや表示順が後で変わっても当時の出題内容を復元するために保存する。

### idempotency_records

参加者向けPOSTの再送を同一操作として扱うための記録である。`(scope, idempotency_key)` に一意制約を持ち、処理中の重複実行を防ぐ。

- id TEXT(36) PRIMARY KEY
- scope TEXT(255) NOT NULL
- idempotency_key TEXT(128) NOT NULL
- participant_id TEXT(36) NULL
- request_hash TEXT(64) NOT NULL
- status TEXT NOT NULL  # in_progress, completed, failed
- response_status INT NULL
- response_json JSON NULL
- owner_token TEXT(36) NULL
- lease_expires_at TIMESTAMP NULL
- completed_at TIMESTAMP NULL
- created_at TIMESTAMP NOT NULL
- updated_at TIMESTAMP NOT NULL

同一`scope`・同一キー・同一リクエストハッシュの完了済み処理は`response_json`を再返却する。同一キーでリクエストハッシュが異なる場合は`409 idempotency_key_conflict`、処理中の場合は`409 idempotency_in_progress`とする。参加者削除時は当該`participant_id`のレコードも削除する。

### learner_states

- id TEXT(36) PRIMARY KEY
- participant_id TEXT(36) REFERENCES participants(id)
- term_id TEXT(36) REFERENCES terms(id)
- current_status TEXT NOT NULL
- primary_misconception TEXT NULL
- secondary_misconception TEXT NULL
- scaffolding_level TEXT NOT NULL
- teaching_strategy TEXT NULL
- previous_teaching_strategy TEXT NULL
- stable_correct_count INT DEFAULT 0
- recurrence_count INT DEFAULT 0
- l0_success_count INT DEFAULT 0
- transfer_success_count INT DEFAULT 0
- last_attempt_id TEXT(36) NULL REFERENCES attempts(id)
- last_tutor_turn_id TEXT(36) NULL REFERENCES tutor_turns(id)
- state_summary TEXT NULL
- updated_reason TEXT NULL
- created_at TIMESTAMP NOT NULL
- updated_at TIMESTAMP NOT NULL

Unique:

- participant_id + term_id

### tutor_sessions

- id TEXT(36) PRIMARY KEY
- participant_id TEXT(36) REFERENCES participants(id)
- term_id TEXT(36) REFERENCES terms(id)
- session_index INT NOT NULL
- group_condition TEXT NOT NULL
- started_at TIMESTAMP NOT NULL
- ended_at TIMESTAMP NULL
- prefetch_state TEXT NOT NULL DEFAULT 'none'  # pending, generating, ready, consumed, failed, discarded
- prefetch_source_session_id TEXT(36) NULL
- prefetch_requested_at TIMESTAMP NULL
- prefetch_generating_at TIMESTAMP NULL
- prefetch_ready_at TIMESTAMP NULL
- prefetch_consumed_at TIMESTAMP NULL
- prefetch_failed_at TIMESTAMP NULL
- prefetch_discarded_at TIMESTAMP NULL
- prefetch_error_code TEXT(80) NULL
- created_at TIMESTAMP NOT NULL

`prefetch_state=none`は通常の対話生成、`ready`は後続用語の未回答v1教材が待機中、`consumed`はその教材を参加者へ再利用済みを表す。`failed`はAI失敗後に通常生成へ切り替え可能な状態、`discarded`は先行生成結果を利用しなかった状態である。既存DBへは列を追加し、過去行を`none`へ補正する。未使用の`pending`、`generating`、`ready`、`failed`、`discarded`は新周回やギブアップ時に再利用せず終了する。ただし、`failed`または`discarded`から同期フォールバックで通常のinteractive turnが保存されたセッションは実学習中とみなし、未使用prefetchのクリーンアップで強制終了しない。

### tutor_turns

- id TEXT(36) PRIMARY KEY
- tutor_session_id TEXT(36) REFERENCES tutor_sessions(id)
- turn_index INT NOT NULL
- scaffolding_level TEXT NULL
- teaching_strategy TEXT NOT NULL
- previous_teaching_strategy TEXT NULL
- strategy_changed BOOLEAN NOT NULL DEFAULT false
- tutor_message TEXT NOT NULL
- learner_prompt TEXT NULL
- practice_question_json JSON NULL
- learner_response TEXT NULL
- learner_confidence INT NULL  # legacy nullable; learningでは収集しない
- ai_feedback TEXT NULL
- diagnosis_json JSON NULL
- grading_json JSON NULL
- next_scaffolding_level TEXT NULL
- forbidden_help_given BOOLEAN NOT NULL DEFAULT false
- question_shown_at TIMESTAMP NULL
- answered_at TIMESTAMP NULL
- response_time_sec FLOAT NULL
- created_at TIMESTAMP NOT NULL
- updated_at TIMESTAMP NOT NULL

学習ターンの `question_shown_at`、`answered_at`、`response_time_sec` は、学習セッション内問題の表示から回答までの時間分析に使う。問題本文と選択肢は `practice_question_json` に保存する。

`diagnosis_json`には`generation_origin`（`interactive`、`interactive_fallback`、`prefetch`）と先行生成の状態、source session、v1方針、再利用・破棄時刻を内部監査情報として保存する。教材系列については`instruction_route`（`proposed_adaptive`または`control_fixed`）、`fixed_sequence_key`、用語・session/turn・variant、実際の構造化AI入力の投影を`instruction_audit`へ保存する。先行生成された未回答turnは`learner_response`と`grading_json`を持たず、回答履歴ビューから除外する。実際に再利用されたturnは`consumed`へ遷移してから回答履歴・実績負担の対象になる。

## 調査用統合回答履歴

`answer_history` は物理テーブルではなく、管理画面・ログAPI・CSVで作る調査用ビューである。`attempts` と `tutor_turns` は統合せず、回答単位で比較できる行だけを次の形に正規化する。

| source_type | 元データ | 用途 |
|---|---|---|
| `test_attempt` | `attempts` | 事前テスト、再テスト、最終テストなどのテスト回答 |
| `learning_turn` | `tutor_turns` | 学習セッション内の問題回答 |

共通フィールドは、`participant_id`, `phase`, `term_slug`, `question_body`, `learner_response`, `is_correct`, `is_sufficient`, `misconception_type`, `teaching_strategy`, `question_shown_at`, `answered_at`, `response_time_sec`, `created_at` とする。並び順は `answered_at` があればそれを使い、なければ `created_at` を使う。

### recurrence_events

- id TEXT(36) PRIMARY KEY
- participant_id TEXT(36) REFERENCES participants(id)
- term_id TEXT(36) REFERENCES terms(id)
- previous_attempt_id TEXT(36) REFERENCES attempts(id)
- current_attempt_id TEXT(36) REFERENCES attempts(id)
- previous_misconception_type TEXT NOT NULL
- current_misconception_type TEXT NOT NULL
- is_same_type BOOLEAN NOT NULL
- phase TEXT NOT NULL
- created_at TIMESTAMP NOT NULL

`unknown` の継続は recurrence_events に入れない。別途attemptsで集計する。

### ai_call_logs

- id TEXT(36) PRIMARY KEY
- provider TEXT NOT NULL
- fallback_provider TEXT NULL
- purpose TEXT NOT NULL
- request_payload JSON NOT NULL
- response_payload JSON NULL
- raw_text TEXT NULL
- codex_thread_id TEXT NULL
- codex_turn_id TEXT NULL
- status TEXT NOT NULL
- error_code TEXT NULL
- error_message TEXT NULL
- latency_ms INT NULL
- created_at TIMESTAMP NOT NULL

Codex app-serverの成功応答では、`raw_text`にapp-serverが返したJSON文字列を解析・内部ラベル除去・契約補正する前の状態で保存する。`response_payload`には、補正後にbackendが利用した応答オブジェクトを保存する。JSON解析に失敗した場合も取得できた生テキストを`raw_text`へ保存する。Mock backendでは実AIの生出力がないためNULLとする。

Codex app-serverの実送信監査は、既存`request_payload`の内容を保ったまま`effective_request`以下へJSONで追加する。実際の`thread/start`設定、`turn/start`の全文入力とoutput schema、モデル・推論レベル、Schema SHA-256、prompt/taxonomy版、RAG検索条件とchunk本文SHA-256、生成試行番号、送信段階を含む。認証情報は含めない。Mock backendの入力はCodexへの送信として記録しない。教材生成時は`response_payload.output_metrics`に本文文字数、700文字の目標値、600〜800文字の許容範囲、範囲内判定、段落数、箇条書き数を保存し、`TutorTurn.diagnosis_json.material_length_validation`に最終検証結果を保存する。これらは既存JSON列への追加であり、DBスキーマ変更ではない。

先行生成のAIログには`request_payload.generation_audit`（source session、対象session、内部生成キー、variant policy）と、確定時の`response_payload.prefetch_audit`（`ready`、`failed`、`discarded`）を追加する。教材生成ログには同じJSON内へ`instruction_route`、`fixed_sequence_key`、`actual_ai_input`を保存する。controlの`actual_ai_input`には個人の診断・履歴・足場掛けを追加せず、proposedだけが既存の適応情報を受け取る点は通常生成と同じである。固定列・CSV列は追加せず、既存JSON監査を正本とする。

purpose values:

- diagnose_answer
- generate_tutoring_turn
- grade_response
- generate_feedback
- generate_correct_answer_summary
- explain_selected_distractor
- summarize_learner_state

status values:

- success
- failed
- `retried`, `fallback_used`, `pending_manual_review` は互換上保持できるが、現行の通常AI呼び出しは自動再試行・Mockフォールバック・手動保留を行わず、主に `success` または `failed` を記録する。

### evaluation_summaries

現行実装の評価サマリーは参加者単位の最新集計として保存する。再計算のたびに履歴行を作成し、管理画面では参加者ごとの最新行だけを参照する。管理画面の評価サマリー、群集計、被験者ログ、ログCSVの参照時には、3用語の事前テストが採点済みで、保存済みsummaryがない場合、元ログより古い場合、または完了状態と不一致の場合に自動再計算する。既存カラム名との互換性のため `l0_correct_rate` を残すが、通常は `final_test` の選択式正答率、なければ互換 `l0_check` の正答率を入れる。両方がなく、再テスト満点で最終テストを省略した場合は再テスト満点を代用する。

旧データで`finish`なのに`completion_reason`がNULLの場合は、起動時に`give_up_experiment`の監査ログを照合する。監査ログがあれば`give_up`、なければ`completed`へ補正し、全履歴サマリーの`completed`も同じ参加者状態へ同期する。

- id TEXT(36) PRIMARY KEY
- participant_id TEXT(36) REFERENCES participants(id)
- group_condition TEXT NOT NULL
- pretest_score FLOAT NULL
- retest_score FLOAT NULL
- l0_correct_rate FLOAT NULL
- transfer_correct_rate FLOAT NULL
- same_misconception_recurrence_rate FLOAT NULL
- m1_recurrence_rate FLOAT NULL
- m2_recurrence_rate FLOAT NULL
- m3_recurrence_rate FLOAT NULL
- m4_failure_rate FLOAT NULL
- unknown_persistence_rate FLOAT NULL
- learning_target_count INT NOT NULL DEFAULT 0
- completed BOOLEAN NOT NULL DEFAULT false
- created_at TIMESTAMP NOT NULL

以下のJSON列は現行の `EvaluationSummary` モデルと再計算処理で使用する。保存済みsummaryだけに依存せず、`participants`、`attempts`、`learner_states`、`term_assignments`、`tutor_sessions`、`tutor_turns`、`recurrence_events`から再計算できる。内部の評価コードは研究ログとして保存し、管理画面の表示名は利用者向けに変換する。

- score_timeline_json JSON NULL
- misconception_timeline_json JSON NULL
- learning_burden_json JSON NULL
- condition_check_json JSON NULL

`score_timeline_json` は `test`, `retest_1`, `retest_2`, ... の得点率、事前比差分ポイント、直前比差分ポイント、未達項目数を保持する。最終確認を省略した場合は `final_test_skipped_after_retest_mastery` と `final_score_source` も保持する。`misconception_timeline_json` は用語別に `test -> retest_n` の誤概念タイプ推移と `resolved`, `same_type_recurred`, `changed_type`, `unknown_persisted`, `regressed`, `unclassified` の変化分類を保持する。`regressed` は画面上では「誤概念」と表示する。既存の `pretest_score`, `retest_score`, `l0_correct_rate` は互換用に残す。

### export_jobs

- id TEXT(36) PRIMARY KEY
- export_name TEXT NOT NULL
- file_path TEXT NOT NULL
- status TEXT NOT NULL
- row_count INT NULL
- created_at TIMESTAMP NOT NULL

### audit_events

- id TEXT(36) PRIMARY KEY
- actor TEXT NOT NULL
- action TEXT NOT NULL
- entity_type TEXT NOT NULL
- entity_id TEXT(36) NULL
- before_json JSON NULL
- after_json JSON NULL
- created_at TIMESTAMP NOT NULL

`AuditEvent` モデルは、学習・実験ギブアップと参加者削除の操作記録に現行MVPで使う。管理者による診断結果の手動修正UIと、その修正内容の監査記録は未実装である。CSV出力は `ExportJob` とログAPIで管理する。

## Logical Search Keys and Constraints

以下は、API・集計で使う論理的な検索キーと、現行モデルで明示された一意制約を分けて示す。現行コードは論理検索キーのすべてを物理的な`Index`として宣言しているわけではないため、DBの物理インデックス一覧とは区別する。

現行モデルで明示された一意制約:

- participants.display_code
- terms.slug
- term_assignments.participant_id + term_id
- question_display_orders.participant_id + question_id
- learner_states.participant_id + term_id

主な論理検索キー:

- questions.term_id + phase
- questions.construct_key
- attempts.participant_id + phase
- attempts.participant_id + term_id
- tutor_turns.tutor_session_id + turn_index
- recurrence_events.participant_id + term_id
- ai_call_logs.purpose + status
- idempotency_records.scope + idempotency_key

## 削除方針（現行MVPと将来運用）

現行MVPには、管理画面の確認ダイアログから `DELETE /api/admin/participants/{participant_id}` を実行して、参加者1名分の実験データを削除する機能がある。削除前に`delete_participant`の`AuditEvent`を作成し、その監査記録は参加者削除後も残す。参加者に所有されるsurvey、assignment、display order、recurrence event、tutor session/turn、learner state、evaluation summary、attempt、対象参加者のAI call logを削除するが、seedの`terms`・`questions`・`question_options`は削除しない。

全参加者一括削除、全実験データ削除、export file削除は現行APIにない。将来導入する場合は、物理削除の範囲、確認手順、監査記録、CSV・バックアップとの整合を別途定義する。

現行APIの削除対象:

- 参加者1名分の関連実験データ
- 対象参加者のAI call log

削除してはいけないもの:

- seed questions
- terms
- question options

将来検討する削除対象:

- 全実験データ
- export file
