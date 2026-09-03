# 07. Data Model

Docker ComposeではPostgreSQL 16、ローカル直接起動ではSQLiteを使用する。SQLAlchemyの同期engineで接続し、起動時は `Base.metadata.create_all` と互換用の不足列追加を行う。Alembicによるマイグレーションは現行起動経路では使用しない。モデル上のIDは36文字の文字列（SQLAlchemyの `String(36)`）として保存し、構造化列はSQLAlchemyのJSON型である。

## Enum Values

### group_condition

- `control`
- `proposed`

### phase

- `pretest`
- `diagnosis`
- `learning`
- `retest`
- `l0_check`  # 互換・補助フェーズ。現行MVPの主導線は final_test
- `final_test`
- `transfer`
- `delayed_retest`（将来対応。現行APIの主導線では未使用）

### test_round (`attempts`)

参加者ごとのテスト周回を記録する表示・分析用キー。`phase` は問題種別と既存API互換の内部値として残す。

- `test`（初回テスト。内部 `pretest`）
- `retest_1`（最初の学習後確認。内部 `retest` または `final_test`）
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
- `L1`  # legacy nullable/互換値。現行MVPの進行制御では使わない
- `null`

## Tables

### participants

- id TEXT(36) PRIMARY KEY
- display_code TEXT UNIQUE NOT NULL
- group_condition TEXT NOT NULL
- assignment_method TEXT NOT NULL DEFAULT `manual`
- consent_checked BOOLEAN NOT NULL DEFAULT false
- current_step TEXT NOT NULL DEFAULT `start`
- started_at TIMESTAMP NULL
- completed_at TIMESTAMP NULL
- completion_reason TEXT NULL  # `completed` または `give_up`
- created_at TIMESTAMP NOT NULL
- updated_at TIMESTAMP NOT NULL

`display_code` は `P001` のような画面表示用ID。個人名やメールアドレスは保存しない。

`current_step` は`pretest`、`learning_targets`、`retest`、`final_test`、`survey`、`l0_check`、`finish`を使用する。`retest`は学習ギブアップ直後に再テストへ進むための状態である。

`completion_reason` は実験終了時の理由を保存する。通常終了は`completed`、実験ギブアップは`give_up`であり、学習セッションだけをギブアップした場合は未終了のためNULLのままとする。学習ギブアップ回数や操作時刻は`audit_events`の`give_up_learning`で記録する。

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

参加者内比較を将来使う場合に備える。MVPでは参加者の `group_condition` と同じ値を保存してよい。

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
- expected_answer TEXT
- expected_keywords JSON NULL
- difficulty INT DEFAULT 1
- construct_key TEXT NOT NULL
- variant_key TEXT NOT NULL
- is_active BOOLEAN DEFAULT true
- created_at TIMESTAMP NOT NULL

`construct_key` は同じ構成概念を測る問題を束ねるキー。事前テストと再テストは同じ `construct_key` だが、`variant_key` と `body` は異なる。

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

選択肢ランダム化の再現性を保存する。

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
- created_at TIMESTAMP NOT NULL

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

現行実装の評価サマリーは参加者単位の最新集計として保存する。再計算のたびに履歴行を作成し、管理画面では参加者ごとの最新行だけを参照する。管理画面の評価サマリー、群集計、被験者ログ、ログCSVの参照時には、3用語の事前テストが採点済みで、保存済みsummaryがない場合、元ログより古い場合、または完了状態と不一致の場合に自動再計算する。既存カラム名との互換性のため `l0_correct_rate` を残すが、現行MVPでは `final_test` の選択式正答率を入れ、最終テストを省略した場合は再テスト満点を代用する。

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

以下のJSON列は現行の `EvaluationSummary` モデルと再計算処理で使用する。保存済みsummaryだけに依存せず、`attempts`、`learner_states`、`recurrence_events`から再計算できる。内部の評価コードは研究ログとして保存し、管理画面の表示名は利用者向けに変換する。

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

`AuditEvent` モデルは存在するが、管理者による手動修正・データ削除の書き込みAPIは現行MVPにない。CSV出力は `ExportJob` とログAPIで管理する。手動修正・削除の監査記録は将来対応である。

## Logical Search Keys and Constraints

以下はAPI・集計で使う論理的な検索キーと、現行モデルで明示されている一意制約である。現行コードはこれらすべてを物理的な`Index`として宣言しているわけではないため、DBの物理インデックス一覧とは区別する。

- participants.display_code unique
- terms.slug unique
- questions.term_id + phase
- questions.construct_key
- attempts.participant_id + phase
- attempts.participant_id + term_id
- learner_states.participant_id + term_id unique
- tutor_turns.tutor_session_id + turn_index
- recurrence_events.participant_id + term_id
- ai_call_logs.purpose + status

## 削除方針（将来運用）

現行MVPには管理画面から参加者や全実験データを削除するAPIがない。データ削除を導入する場合は、物理削除の範囲、確認ダイアログ、`audit_events` 記録を別途実装する。

削除対象:

- 参加者1名分の全データ
- 全実験データ
- export file

削除してはいけないもの:

- seed questions
- terms
- migration history
