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
- `l0_check`
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
- `L1`
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
- is_correct BOOLEAN NULL
- score FLOAT NULL
- diagnosed_status TEXT NULL
- misconception_type TEXT NULL
- secondary_misconception_type TEXT NULL
- misconception_confidence FLOAT NULL
- natural_language_diagnosis TEXT NULL
- recurrence_flag BOOLEAN NOT NULL DEFAULT false
- l0_success BOOLEAN NULL
- requires_manual_review BOOLEAN NOT NULL DEFAULT false
- idempotency_key TEXT NULL
- created_at TIMESTAMP NOT NULL
- updated_at TIMESTAMP NOT NULL

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
- created_at TIMESTAMP NOT NULL
- updated_at TIMESTAMP NOT NULL

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

- id UUID PRIMARY KEY
- participant_id UUID REFERENCES participants(id)
- group_condition TEXT NOT NULL
- pretest_score FLOAT NULL
- retest_score FLOAT NULL
- l0_correct_rate FLOAT NULL
- same_misconception_recurrence_rate FLOAT NULL
- m1_recurrence_rate FLOAT NULL
- m2_recurrence_rate FLOAT NULL
- m3_recurrence_rate FLOAT NULL
- m4_failure_rate FLOAT NULL
- unknown_persistence_rate FLOAT NULL
- learning_target_count INT NOT NULL DEFAULT 0
- completed BOOLEAN NOT NULL DEFAULT false
- created_at TIMESTAMP NOT NULL

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
