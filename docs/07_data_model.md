# 07. Data Model

PostgreSQL + SQLAlchemy + Alembicを使用する。

## Tables

### participants

- id UUID PRIMARY KEY
- display_code TEXT UNIQUE NOT NULL
- group_condition TEXT NOT NULL CHECK control/proposed
- created_at TIMESTAMP NOT NULL
- completed_at TIMESTAMP NULL

### participant_surveys

- id UUID PRIMARY KEY
- participant_id UUID REFERENCES participants(id)
- ai_experience_level INT
- programming_experience_level INT
- llm_usage_level INT
- self_rated_ai_knowledge INT
- created_at TIMESTAMP NOT NULL

### terms

- id UUID PRIMARY KEY
- slug TEXT UNIQUE NOT NULL
- label TEXT NOT NULL
- description TEXT

### questions

- id UUID PRIMARY KEY
- term_id UUID REFERENCES terms(id)
- phase TEXT NOT NULL
- question_type TEXT NOT NULL
- body TEXT NOT NULL
- expected_answer TEXT
- difficulty INT DEFAULT 1
- is_active BOOLEAN DEFAULT true

phase values:

- pretest
- learning
- retest
- l0_check
- transfer

question_type values:

- definition
- discrimination
- practice
- retest_same_construct
- transfer

### question_options

- id UUID PRIMARY KEY
- question_id UUID REFERENCES questions(id)
- option_label TEXT NOT NULL
- body TEXT NOT NULL
- is_correct BOOLEAN NOT NULL
- misconception_type TEXT NULL
- display_order INT

misconception_type values:

- M1
- M2
- M3
- M4
- unknown
- ambiguous
- null

### attempts

- id UUID PRIMARY KEY
- participant_id UUID REFERENCES participants(id)
- question_id UUID REFERENCES questions(id)
- phase TEXT NOT NULL
- selected_option_id UUID NULL REFERENCES question_options(id)
- free_text_answer TEXT NULL
- reason_text TEXT NULL
- confidence INT NULL
- is_correct BOOLEAN NULL
- diagnosed_status TEXT NULL
- misconception_type TEXT NULL
- misconception_confidence FLOAT NULL
- response_time_sec FLOAT NULL
- created_at TIMESTAMP NOT NULL

### learner_states

- id UUID PRIMARY KEY
- participant_id UUID REFERENCES participants(id)
- term_id UUID REFERENCES terms(id)
- current_status TEXT NOT NULL
- primary_misconception TEXT NULL
- secondary_misconception TEXT NULL
- scaffolding_level TEXT NOT NULL
- teaching_strategy TEXT NULL
- stable_correct_count INT DEFAULT 0
- recurrence_count INT DEFAULT 0
- l0_success_count INT DEFAULT 0
- transfer_success_count INT DEFAULT 0
- last_attempt_id UUID NULL REFERENCES attempts(id)
- updated_at TIMESTAMP NOT NULL

current_status values:

- unknown
- misconception
- unstable_correct
- stable_correct
- transfer_ready
- mastered
- needs_review

### tutor_sessions

- id UUID PRIMARY KEY
- participant_id UUID REFERENCES participants(id)
- term_id UUID REFERENCES terms(id)
- session_index INT NOT NULL
- group_condition TEXT NOT NULL
- started_at TIMESTAMP NOT NULL
- ended_at TIMESTAMP NULL

### tutor_turns

- id UUID PRIMARY KEY
- tutor_session_id UUID REFERENCES tutor_sessions(id)
- turn_index INT NOT NULL
- scaffolding_level TEXT NOT NULL
- teaching_strategy TEXT NOT NULL
- tutor_message TEXT NOT NULL
- learner_response TEXT NULL
- ai_feedback TEXT NULL
- diagnosis_json JSONB NULL
- next_scaffolding_level TEXT NULL
- created_at TIMESTAMP NOT NULL

### recurrence_events

- id UUID PRIMARY KEY
- participant_id UUID REFERENCES participants(id)
- term_id UUID REFERENCES terms(id)
- previous_attempt_id UUID REFERENCES attempts(id)
- current_attempt_id UUID REFERENCES attempts(id)
- previous_misconception_type TEXT NOT NULL
- current_misconception_type TEXT NOT NULL
- is_same_type BOOLEAN NOT NULL
- created_at TIMESTAMP NOT NULL

### ai_call_logs

- id UUID PRIMARY KEY
- provider TEXT NOT NULL
- purpose TEXT NOT NULL
- request_payload JSONB NOT NULL
- response_payload JSONB NULL
- raw_text TEXT NULL
- codex_thread_id TEXT NULL
- codex_turn_id TEXT NULL
- status TEXT NOT NULL
- error_message TEXT NULL
- created_at TIMESTAMP NOT NULL

purpose values:

- diagnose_answer
- generate_tutoring_turn
- grade_response
- generate_feedback

### evaluation_summaries

- id UUID PRIMARY KEY
- participant_id UUID REFERENCES participants(id)
- pretest_score FLOAT
- retest_score FLOAT
- l0_correct_rate FLOAT
- transfer_correct_rate FLOAT
- same_misconception_recurrence_rate FLOAT
- m1_recurrence_rate FLOAT
- m2_recurrence_rate FLOAT
- m3_recurrence_rate FLOAT
- m4_failure_rate FLOAT
- created_at TIMESTAMP NOT NULL
