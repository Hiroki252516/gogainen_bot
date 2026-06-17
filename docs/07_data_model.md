# 07. Data Model

SQLite/PostgreSQL + SQLAlchemyで実装する。すべてのテーブルに `created_at` を持たせ、更新されるテーブルには `updated_at` を持たせる。主キーはUUID文字列を基本にする。

## Enum Values

### group_condition

- `control`
- `proposed`

### phase

- `pretest`
- `learning`
- `prerequisite` 学習セッション内部段階
- `concept_phase1` 学習セッション内部段階
- `concept_phase2` 学習セッション内部段階
- `retest`
- `post_survey`
- `l0_check` 旧互換
- `transfer` 旧互換
- `delayed_retest` 将来拡張

### learning_session_status

- `not_started`
- `prerequisite`
- `concept_phase1`
- `concept_phase2`
- `completed`
- `blocked`
- `failed_phase1`
- `failed_phase2`
- `failed` 旧互換

### misconception_type

- `M1`
- `M2`
- `M3`
- `M4` 旧互換/将来拡張
- `unknown`
- `ambiguous`
- `null`

### diagnosed_status

- `unknown`
- `misconception`
- `unstable_correct`
- `stable_correct`
- `ambiguous`

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

事前アンケートは現行フローでは作成しない。

### participant_surveys

- id UUID PRIMARY KEY
- participant_id UUID REFERENCES participants(id)
- phase TEXT NOT NULL
- ai_experience_level INT NULL 旧互換
- programming_experience_level INT NULL 旧互換
- llm_usage_level INT NULL 旧互換
- self_rated_ai_knowledge INT NULL 旧互換
- term_confidences JSON NULL 旧互換
- usability_rating INT NULL
- helpfulness_rating INT NULL
- perceived_hint_amount INT NULL
- free_comment TEXT NULL
- created_at TIMESTAMP NOT NULL

`phase` は通常 `post_survey` のみ使う。

### terms

- id UUID PRIMARY KEY
- slug TEXT UNIQUE NOT NULL
- label TEXT NOT NULL
- description TEXT
- display_order INT NOT NULL
- is_active BOOLEAN NOT NULL DEFAULT true
- created_at TIMESTAMP NOT NULL

### term_assignments

- id UUID PRIMARY KEY
- participant_id UUID REFERENCES participants(id)
- term_id UUID REFERENCES terms(id)
- group_condition TEXT NOT NULL
- is_learning_target BOOLEAN NOT NULL DEFAULT false
- selection_reason TEXT NULL
- priority_score FLOAT NULL
- created_at TIMESTAMP NOT NULL

`stable_correct` 以外の事前テスト結果を全件学習対象にする。

### questions / question_options / question_display_orders

事前テストと再テストの選択式問題を保存する。現行active phaseは `pretest` と `retest`。`l0_check` と `transfer` は旧互換・将来拡張用として非active化してよい。

`question_options.misconception_type` は正答でnull、誤答でM1/M2/M3、わからないでunknownを保存する。

### attempts

テストフェーズの回答を保存する。

- id UUID PRIMARY KEY
- participant_id UUID REFERENCES participants(id)
- term_id UUID REFERENCES terms(id)
- question_id UUID REFERENCES questions(id)
- phase TEXT NOT NULL
- attempt_index INT NOT NULL DEFAULT 1
- selected_option_id UUID NULL REFERENCES question_options(id)
- free_text_answer TEXT NULL
- reason_text TEXT NULL
- confidence INT NULL
- response_time_sec FLOAT NULL
- is_correct BOOLEAN NULL
- score FLOAT NULL
- diagnosed_status TEXT NULL
- misconception_type TEXT NULL
- secondary_misconception_type TEXT NULL
- misconception_confidence FLOAT NULL
- natural_language_diagnosis TEXT NULL
- recurrence_flag BOOLEAN NOT NULL DEFAULT false
- l0_success BOOLEAN NULL 旧互換
- transfer_success BOOLEAN NULL 旧互換
- requires_manual_review BOOLEAN NOT NULL DEFAULT false
- idempotency_key TEXT NULL
- created_at TIMESTAMP NOT NULL
- updated_at TIMESTAMP NOT NULL

### learner_states

事前テスト診断と再テスト再発の集計用状態を保存する。旧 `scaffolding_level` などは互換列として残すが、現行提案群の学習制御には使わない。

### learning_sessions

提案群・統制群の1対象概念あたりの学習セッションを保存する。現行v2スコープでは、両群とも `prerequisite -> concept_phase1 -> concept_phase2` を通る。提案群だけが誤概念・事前テスト診断・過去ログを使って戻り制御を行う。

- id UUID PRIMARY KEY
- participant_id UUID REFERENCES participants(id)
- term_id UUID REFERENCES terms(id)
- group_condition TEXT NOT NULL
- session_index INT NOT NULL
- status TEXT NOT NULL
- current_prerequisite_index INT DEFAULT 0
- term_pass_count INT DEFAULT 0
- concept_attempt_count INT DEFAULT 0 旧互換
- concept_phase1_attempt_count INT DEFAULT 0
- concept_phase2_attempt_count INT DEFAULT 0
- phase2_retry_count INT DEFAULT 0
- concept_material TEXT NULL
- concept_prompt TEXT NULL
- concept_expected_answer TEXT NULL
- phase2_prompt TEXT NULL
- phase2_light_conditions TEXT NULL
- phase2_expected_answer TEXT NULL
- last_feedback TEXT NULL
- blocked_reason TEXT NULL
- completed_at TIMESTAMP NULL
- created_at TIMESTAMP NOT NULL
- updated_at TIMESTAMP NOT NULL

### prerequisite_terms

提案群ではAIが生成した前提用語、統制群ではRAG教材に基づく一般小問を保存する。両群とも3件固定。統制群ではpass/failを保存するが、failしても戻り制御には使わない。

- id UUID PRIMARY KEY
- learning_session_id UUID REFERENCES learning_sessions(id)
- term_label TEXT NOT NULL
- material TEXT NOT NULL
- check_question TEXT NOT NULL
- expected_answer TEXT NOT NULL
- generation_reason TEXT NULL
- display_order INT NOT NULL
- status TEXT NOT NULL DEFAULT `not_started`
- attempt_count INT DEFAULT 0
- last_feedback TEXT NULL
- remediation_material TEXT NULL
- created_at TIMESTAMP NOT NULL
- updated_at TIMESTAMP NOT NULL

### term_understanding_attempts

前提用語/小問の記述回答を保存する。提案群ではgate判定、統制群ではログ保存として扱う。

- id UUID PRIMARY KEY
- prerequisite_term_id UUID REFERENCES prerequisite_terms(id)
- participant_id UUID REFERENCES participants(id)
- learning_session_id UUID REFERENCES learning_sessions(id)
- attempt_index INT NOT NULL
- learner_answer TEXT NOT NULL
- is_passed BOOLEAN NOT NULL
- score FLOAT NULL
- feedback TEXT NOT NULL
- remediation_material TEXT NULL
- grading_json JSON NULL
- created_at TIMESTAMP NOT NULL

### concept_understanding_attempts

概念フェーズ1/フェーズ2の記述回答を保存する。フェーズ1は教材あり、フェーズ2は教材本文なしで軽い条件だけを表示する。

- id UUID PRIMARY KEY
- learning_session_id UUID REFERENCES learning_sessions(id)
- participant_id UUID REFERENCES participants(id)
- attempt_index INT NOT NULL
- concept_phase TEXT NOT NULL DEFAULT `phase1`
- concept_material TEXT NOT NULL
- prompt TEXT NOT NULL
- material_shown BOOLEAN NOT NULL DEFAULT true
- light_condition_text TEXT NULL
- learner_answer TEXT NOT NULL
- is_passed BOOLEAN NOT NULL
- score FLOAT NULL
- feedback TEXT NOT NULL
- missing_prerequisite_ids JSON NULL
- review_prerequisite_ids JSON NULL
- independent_explanation_success BOOLEAN NULL
- return_to_phase1 BOOLEAN NOT NULL DEFAULT false
- rubric_scores JSON NULL
- grading_json JSON NULL
- created_at TIMESTAMP NOT NULL

### tutor_sessions / tutor_turns

旧互換ログ。現行参加者フローの統制群も `learning_sessions` 系テーブルを主ログにする。既存CSV互換や旧API切り分けのため残す。

### recurrence_events

再テストで事前テストと同じM1〜M3が出た場合に保存する。`unknown` の継続はrecurrenceではなく別集計する。

### ai_call_logs

purpose values:

- diagnose_answer
- generate_prerequisite_plan
- generate_control_prerequisite_plan
- grade_prerequisite_answer
- generate_concept_phase1_material
- grade_concept_phase1_answer
- generate_concept_phase2_prompt
- grade_concept_phase2_answer
- 旧互換: generate_concept_material
- 旧互換: grade_concept_answer
- generate_control_learning_turn
- grade_control_learning_answer
- grade_response
- summarize_learner_state
- 旧互換: generate_tutoring_turn, generate_feedback

### evaluation_summaries

- id UUID PRIMARY KEY
- participant_id UUID REFERENCES participants(id)
- group_condition TEXT NOT NULL
- pretest_score FLOAT NULL
- retest_score FLOAT NULL
- l0_correct_rate FLOAT NULL 旧互換/現行null
- transfer_correct_rate FLOAT NULL 旧互換/現行null
- same_misconception_recurrence_rate FLOAT NULL
- m1_recurrence_rate FLOAT NULL
- m2_recurrence_rate FLOAT NULL
- m3_recurrence_rate FLOAT NULL
- m4_failure_rate FLOAT NULL 旧互換/現行null
- unknown_persistence_rate FLOAT NULL
- prerequisite_pass_rate FLOAT NULL
- concept_pass_rate FLOAT NULL
- concept_phase1_pass_rate FLOAT NULL
- concept_phase2_success_rate FLOAT NULL
- phase2_after_retry_success_rate FLOAT NULL
- phase2_max_retry_rate FLOAT NULL
- phase2_pass_retest_correct_rate FLOAT NULL
- phase2_fail_retest_correct_rate FLOAT NULL
- learning_target_count INT NOT NULL DEFAULT 0
- completed BOOLEAN NOT NULL DEFAULT false
- created_at TIMESTAMP NOT NULL

### export_jobs / audit_events

CSV出力と管理者操作を記録する。

## Indexes

- participants.display_code unique
- terms.slug unique
- questions.term_id + phase
- attempts.participant_id + phase
- attempts.participant_id + term_id
- learner_states.participant_id + term_id unique
- learning_sessions.participant_id + term_id
- prerequisite_terms.learning_session_id + display_order
