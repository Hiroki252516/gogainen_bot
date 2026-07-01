# 07. Data Model

PostgreSQL + SQLAlchemy + Alembicを使用する。すべてのテーブルに `created_at` を持たせ、更新されるテーブルには `updated_at` を持たせる。主キーはUUIDを基本にする。

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
- `delayed_retest`

### question_type

- `definition`
- `discrimination`
- `practice`
- `retest_same_construct`
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

- id UUID PRIMARY KEY
- display_code TEXT UNIQUE NOT NULL
- group_condition TEXT NOT NULL
- assignment_method TEXT NOT NULL DEFAULT `manual`
- consent_checked BOOLEAN NOT NULL DEFAULT false
- current_step TEXT NOT NULL DEFAULT `start`
- started_at TIMESTAMP NULL
- completed_at TIMESTAMP NULL
- created_at TIMESTAMP NOT NULL
- updated_at TIMESTAMP NOT NULL

`display_code` は `P001` のような画面表示用ID。個人名やメールアドレスは保存しない。

### participant_surveys

アンケート接続用の現行モデル。`/survey` 画面は暫定表示だが、DBモデルは用意されている。

- id UUID PRIMARY KEY
- participant_id UUID REFERENCES participants(id)
- phase TEXT NOT NULL
- ai_experience_level INT NULL
- programming_experience_level INT NULL
- llm_usage_level INT NULL
- self_rated_ai_knowledge INT NULL
- term_confidences JSONB NULL
- usability_rating INT NULL
- helpfulness_rating INT NULL
- perceived_hint_amount INT NULL
- free_comment TEXT NULL
- created_at TIMESTAMP NOT NULL

### terms

- id UUID PRIMARY KEY
- slug TEXT UNIQUE NOT NULL
- label TEXT NOT NULL
- description TEXT
- display_order INT NOT NULL
- is_active BOOLEAN NOT NULL DEFAULT true
- created_at TIMESTAMP NOT NULL

### term_assignments

参加者内比較を将来使う場合に備える。MVPでは参加者の `group_condition` と同じ値を保存してよい。

- id UUID PRIMARY KEY
- participant_id UUID REFERENCES participants(id)
- term_id UUID REFERENCES terms(id)
- group_condition TEXT NOT NULL
- is_learning_target BOOLEAN NOT NULL DEFAULT false
- selection_reason TEXT NULL
- priority_score FLOAT NULL
- created_at TIMESTAMP NOT NULL

### questions

- id UUID PRIMARY KEY
- term_id UUID REFERENCES terms(id)
- phase TEXT NOT NULL
- question_type TEXT NOT NULL
- body TEXT NOT NULL
- expected_answer TEXT
- expected_keywords JSONB NULL
- difficulty INT DEFAULT 1
- construct_key TEXT NOT NULL
- variant_key TEXT NOT NULL
- is_active BOOLEAN DEFAULT true
- created_at TIMESTAMP NOT NULL

`construct_key` は同じ構成概念を測る問題を束ねるキー。事前テストと再テストは同じ `construct_key` だが、`variant_key` と `body` は異なる。

### question_options

- id UUID PRIMARY KEY
- question_id UUID REFERENCES questions(id)
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

- id UUID PRIMARY KEY
- participant_id UUID REFERENCES participants(id)
- question_id UUID REFERENCES questions(id)
- option_order JSONB NOT NULL
- random_seed TEXT NOT NULL
- created_at TIMESTAMP NOT NULL

### attempts

- id UUID PRIMARY KEY
- participant_id UUID REFERENCES participants(id)
- term_id UUID REFERENCES terms(id)
- question_id UUID REFERENCES questions(id)
- phase TEXT NOT NULL
- attempt_index INT NOT NULL DEFAULT 1
- selected_option_id UUID NULL REFERENCES question_options(id)
- free_text_answer TEXT NULL
- reason_text TEXT NULL  # pretestでは常にNULL
- confidence INT NULL  # legacy nullable; pretestとlearningでは収集しない
- response_time_sec FLOAT NULL
- question_shown_at TIMESTAMP NULL
- answered_at TIMESTAMP NULL
- question_body_snapshot TEXT NULL
- option_order_snapshot JSONB NULL
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

- id UUID PRIMARY KEY
- participant_id UUID REFERENCES participants(id)
- term_id UUID REFERENCES terms(id)
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
- last_attempt_id UUID NULL REFERENCES attempts(id)
- last_tutor_turn_id UUID NULL REFERENCES tutor_turns(id)
- state_summary TEXT NULL
- updated_reason TEXT NULL
- created_at TIMESTAMP NOT NULL
- updated_at TIMESTAMP NOT NULL

Unique:

- participant_id + term_id

### tutor_sessions

- id UUID PRIMARY KEY
- participant_id UUID REFERENCES participants(id)
- term_id UUID REFERENCES terms(id)
- session_index INT NOT NULL
- group_condition TEXT NOT NULL
- started_at TIMESTAMP NOT NULL
- ended_at TIMESTAMP NULL
- created_at TIMESTAMP NOT NULL

### tutor_turns

- id UUID PRIMARY KEY
- tutor_session_id UUID REFERENCES tutor_sessions(id)
- turn_index INT NOT NULL
- scaffolding_level TEXT NULL
- teaching_strategy TEXT NOT NULL
- previous_teaching_strategy TEXT NULL
- strategy_changed BOOLEAN NOT NULL DEFAULT false
- tutor_message TEXT NOT NULL
- learner_prompt TEXT NULL
- practice_question_json JSONB NULL
- learner_response TEXT NULL
- learner_confidence INT NULL  # legacy nullable; learningでは収集しない
- ai_feedback TEXT NULL
- diagnosis_json JSONB NULL
- grading_json JSONB NULL
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

- id UUID PRIMARY KEY
- participant_id UUID REFERENCES participants(id)
- term_id UUID REFERENCES terms(id)
- previous_attempt_id UUID REFERENCES attempts(id)
- current_attempt_id UUID REFERENCES attempts(id)
- previous_misconception_type TEXT NOT NULL
- current_misconception_type TEXT NOT NULL
- is_same_type BOOLEAN NOT NULL
- phase TEXT NOT NULL
- created_at TIMESTAMP NOT NULL

`unknown` の継続は recurrence_events に入れない。別途attemptsで集計する。

### ai_call_logs

- id UUID PRIMARY KEY
- provider TEXT NOT NULL
- fallback_provider TEXT NULL
- purpose TEXT NOT NULL
- request_payload JSONB NOT NULL
- response_payload JSONB NULL
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
- summarize_learner_state

status values:

- success
- failed
- retried
- fallback_used
- pending_manual_review

### evaluation_summaries

現行実装の評価サマリーは参加者単位の最新集計として保存する。再計算のたびに新しい行を作成し、管理画面では最新行を参照する。既存カラム名との互換性のため `l0_correct_rate` を残すが、現行MVPでは `final_test` が存在する場合に `final_test` の選択式正答率を入れる。

- id UUID PRIMARY KEY
- participant_id UUID REFERENCES participants(id)
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

次段のログ拡張では、周回数が固定されない再テストを扱うため、以下のJSON列を追加候補にする。現時点ではスコア推移は `attempts` と `answer_history` から再計算できる形を正とし、保存済みsummaryだけに依存しない。

- score_timeline_json JSONB NULL
- misconception_timeline_json JSONB NULL
- learning_burden_json JSONB NULL
- condition_check_json JSONB NULL

`score_timeline_json` は `pretest`, `retest_1`, `retest_2`, ..., `final_test` の得点率、事前比差分ポイント、直前比差分ポイント、未達項目数を保持する。`misconception_timeline_json` は用語別に `pretest -> retest_n -> final_test` の誤概念タイプ推移と `resolved`, `same_type_recurred`, `changed_type`, `unknown_persisted`, `regressed` の変化分類を保持する。既存の `pretest_score`, `retest_score`, `l0_correct_rate` は互換用に残す。

### export_jobs

- id UUID PRIMARY KEY
- export_name TEXT NOT NULL
- file_path TEXT NOT NULL
- status TEXT NOT NULL
- row_count INT NULL
- created_at TIMESTAMP NOT NULL

### audit_events

- id UUID PRIMARY KEY
- actor TEXT NOT NULL
- action TEXT NOT NULL
- entity_type TEXT NOT NULL
- entity_id UUID NULL
- before_json JSONB NULL
- after_json JSONB NULL
- created_at TIMESTAMP NOT NULL

管理者による手動修正、データ削除、CSV出力を記録する。

## Indexes

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

## 削除方針

MVPでは物理削除でよい。ただし管理画面から削除した場合は `audit_events` に記録する。

削除対象:

- 参加者1名分の全データ
- 全実験データ
- export file

削除してはいけないもの:

- seed questions
- terms
- migration history
