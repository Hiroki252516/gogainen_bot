from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid.uuid4())


def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    show_pretest_results: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    display_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    group_condition: Mapped[str] = mapped_column(String(32), nullable=False)
    assignment_method: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    consent_checked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_document_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    consented_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    current_step: Mapped[str] = mapped_column(String(64), default="start", nullable=False)
    learning_content_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    question_set_mode: Mapped[str | None] = mapped_column(String(32), nullable=True, default="standard")
    experiment_spec_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    protocol_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    option_order_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    retest_cycles_completed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completion_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, nullable=False)


class RuntimeSetting(Base):
    __tablename__ = "runtime_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    show_pretest_results: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    option_order_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="debug_fixed")
    question_set_mode: Mapped[str | None] = mapped_column(String(32), nullable=True, default="standard")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, nullable=False)


class ParticipantSurvey(Base):
    __tablename__ = "participant_surveys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(String(36), ForeignKey("participants.id"), nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    survey_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    responses_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ai_experience_level: Mapped[int | None] = mapped_column(Integer)
    programming_experience_level: Mapped[int | None] = mapped_column(Integer)
    llm_usage_level: Mapped[int | None] = mapped_column(Integer)
    self_rated_ai_knowledge: Mapped[int | None] = mapped_column(Integer)
    term_confidences: Mapped[dict | None] = mapped_column(JSON)
    usability_rating: Mapped[int | None] = mapped_column(Integer)
    helpfulness_rating: Mapped[int | None] = mapped_column(Integer)
    perceived_hint_amount: Mapped[int | None] = mapped_column(Integer)
    free_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("scope", "idempotency_key", name="uq_idempotency_scope_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scope: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    participant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_json: Mapped[dict | list | None] = mapped_column(JSON)
    owner_token: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, nullable=False)


class Term(Base):
    __tablename__ = "terms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class TermAssignment(Base):
    __tablename__ = "term_assignments"
    __table_args__ = (UniqueConstraint("participant_id", "term_id", name="uq_term_assignment"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(String(36), ForeignKey("participants.id"), nullable=False)
    term_id: Mapped[str] = mapped_column(String(36), ForeignKey("terms.id"), nullable=False)
    group_condition: Mapped[str] = mapped_column(String(32), nullable=False)
    is_learning_target: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    selection_reason: Mapped[str | None] = mapped_column(Text)
    priority_score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    term_id: Mapped[str] = mapped_column(String(36), ForeignKey("terms.id"), nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    question_type: Mapped[str] = mapped_column(String(64), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer: Mapped[str | None] = mapped_column(Text)
    legacy_expected_keywords: Mapped[list | None] = mapped_column("expected_keywords", JSON)
    difficulty: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    construct_key: Mapped[str] = mapped_column(String(120), nullable=False)
    variant_key: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class QuestionOption(Base):
    __tablename__ = "question_options"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("questions.id"), nullable=False)
    option_label: Mapped[str] = mapped_column(String(16), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    misconception_type: Mapped[str | None] = mapped_column(String(32))
    rationale: Mapped[str | None] = mapped_column(Text)
    default_order: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class QuestionDisplayOrder(Base):
    __tablename__ = "question_display_orders"
    __table_args__ = (UniqueConstraint("participant_id", "question_id", name="uq_question_display_order"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(String(36), ForeignKey("participants.id"), nullable=False)
    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("questions.id"), nullable=False)
    option_order: Mapped[list] = mapped_column(JSON, nullable=False)
    random_seed: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(String(36), ForeignKey("participants.id"), nullable=False)
    term_id: Mapped[str] = mapped_column(String(36), ForeignKey("terms.id"), nullable=False)
    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("questions.id"), nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    test_round: Mapped[str | None] = mapped_column(String(32))
    attempt_index: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    legacy_selected_option_id: Mapped[str | None] = mapped_column("selected_option_id", String(36), ForeignKey("question_options.id"))
    selected_option_ids: Mapped[list | None] = mapped_column(JSON)
    legacy_free_text_answer: Mapped[str | None] = mapped_column("free_text_answer", Text)
    legacy_reason_text: Mapped[str | None] = mapped_column("reason_text", Text)
    legacy_confidence: Mapped[int | None] = mapped_column("confidence", Integer)
    response_time_sec: Mapped[float | None] = mapped_column(Float)
    question_shown_at: Mapped[datetime | None] = mapped_column(DateTime)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime)
    question_body_snapshot: Mapped[str | None] = mapped_column(Text)
    option_order_snapshot: Mapped[list | None] = mapped_column(JSON)
    glossary_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    score: Mapped[float | None] = mapped_column(Float)
    diagnosed_status: Mapped[str | None] = mapped_column(String(64))
    misconception_type: Mapped[str | None] = mapped_column(String(32))
    legacy_secondary_misconception_type: Mapped[str | None] = mapped_column("secondary_misconception_type", String(32))
    misconception_confidence: Mapped[float | None] = mapped_column(Float)
    natural_language_diagnosis: Mapped[str | None] = mapped_column(Text)
    recurrence_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    legacy_l0_success: Mapped[bool | None] = mapped_column("l0_success", Boolean)
    legacy_transfer_success: Mapped[bool | None] = mapped_column("transfer_success", Boolean)
    legacy_requires_manual_review: Mapped[bool] = mapped_column("requires_manual_review", Boolean, default=False, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, nullable=False)


class LearnerState(Base):
    __tablename__ = "learner_states"
    __table_args__ = (UniqueConstraint("participant_id", "term_id", name="uq_learner_state"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(String(36), ForeignKey("participants.id"), nullable=False)
    term_id: Mapped[str] = mapped_column(String(36), ForeignKey("terms.id"), nullable=False)
    current_status: Mapped[str] = mapped_column(String(64), nullable=False)
    primary_misconception: Mapped[str | None] = mapped_column(String(32))
    legacy_secondary_misconception: Mapped[str | None] = mapped_column("secondary_misconception", String(32))
    legacy_scaffolding_level: Mapped[str] = mapped_column("scaffolding_level", String(16), nullable=False, default="not_applicable")
    teaching_strategy: Mapped[str | None] = mapped_column(String(80))
    legacy_previous_teaching_strategy: Mapped[str | None] = mapped_column("previous_teaching_strategy", String(80))
    stable_correct_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recurrence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    legacy_l0_success_count: Mapped[int] = mapped_column("l0_success_count", Integer, default=0, nullable=False)
    legacy_transfer_success_count: Mapped[int] = mapped_column("transfer_success_count", Integer, default=0, nullable=False)
    last_attempt_id: Mapped[str | None] = mapped_column(String(36))
    last_tutor_turn_id: Mapped[str | None] = mapped_column(String(36))
    state_summary: Mapped[str | None] = mapped_column(Text)
    updated_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, nullable=False)


class TutorSession(Base):
    __tablename__ = "tutor_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(String(36), ForeignKey("participants.id"), nullable=False)
    term_id: Mapped[str] = mapped_column(String(36), ForeignKey("terms.id"), nullable=False)
    session_index: Mapped[int] = mapped_column(Integer, nullable=False)
    group_condition: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    # ``none`` is the normal interactive-session state.  The other values
    # describe a first-turn material prepared for a later learning target.
    # These columns are intentionally kept on the session rather than exposed
    # by the participant API so the prefetch lifecycle remains an audit detail.
    prefetch_state: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    prefetch_source_session_id: Mapped[str | None] = mapped_column(String(36))
    prefetch_requested_at: Mapped[datetime | None] = mapped_column(DateTime)
    prefetch_generating_at: Mapped[datetime | None] = mapped_column(DateTime)
    prefetch_ready_at: Mapped[datetime | None] = mapped_column(DateTime)
    prefetch_consumed_at: Mapped[datetime | None] = mapped_column(DateTime)
    prefetch_failed_at: Mapped[datetime | None] = mapped_column(DateTime)
    prefetch_discarded_at: Mapped[datetime | None] = mapped_column(DateTime)
    prefetch_error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class TutorTurn(Base):
    __tablename__ = "tutor_turns"

    material_viewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tutor_session_id: Mapped[str] = mapped_column(String(36), ForeignKey("tutor_sessions.id"), nullable=False)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    legacy_scaffolding_level: Mapped[str | None] = mapped_column("scaffolding_level", String(16))
    teaching_strategy: Mapped[str] = mapped_column(String(80), nullable=False)
    legacy_previous_teaching_strategy: Mapped[str | None] = mapped_column("previous_teaching_strategy", String(80))
    legacy_strategy_changed: Mapped[bool] = mapped_column("strategy_changed", Boolean, default=False, nullable=False)
    tutor_message: Mapped[str] = mapped_column(Text, nullable=False)
    learner_prompt: Mapped[str | None] = mapped_column(Text)
    practice_question_json: Mapped[dict | None] = mapped_column(JSON)
    learner_response: Mapped[str | None] = mapped_column(Text)
    legacy_learner_confidence: Mapped[int | None] = mapped_column("learner_confidence", Integer)
    ai_feedback: Mapped[str | None] = mapped_column(Text)
    diagnosis_json: Mapped[dict | None] = mapped_column(JSON)
    grading_json: Mapped[dict | None] = mapped_column(JSON)
    legacy_next_scaffolding_level: Mapped[str | None] = mapped_column("next_scaffolding_level", String(16))
    legacy_forbidden_help_given: Mapped[bool] = mapped_column("forbidden_help_given", Boolean, default=False, nullable=False)
    question_shown_at: Mapped[datetime | None] = mapped_column(DateTime)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime)
    response_time_sec: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, nullable=False)


class RecurrenceEvent(Base):
    __tablename__ = "recurrence_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(String(36), ForeignKey("participants.id"), nullable=False)
    term_id: Mapped[str] = mapped_column(String(36), ForeignKey("terms.id"), nullable=False)
    previous_attempt_id: Mapped[str] = mapped_column(String(36), ForeignKey("attempts.id"), nullable=False)
    current_attempt_id: Mapped[str] = mapped_column(String(36), ForeignKey("attempts.id"), nullable=False)
    previous_misconception_type: Mapped[str] = mapped_column(String(32), nullable=False)
    current_misconception_type: Mapped[str] = mapped_column(String(32), nullable=False)
    is_same_type: Mapped[bool] = mapped_column(Boolean, nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class AICallLog(Base):
    __tablename__ = "ai_call_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    fallback_provider: Mapped[str | None] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(80), nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    response_payload: Mapped[dict | None] = mapped_column(JSON)
    raw_text: Mapped[str | None] = mapped_column(Text)
    codex_thread_id: Mapped[str | None] = mapped_column(String(128))
    codex_turn_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class EvaluationSummary(Base):
    __tablename__ = "evaluation_summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(String(36), ForeignKey("participants.id"), nullable=False)
    group_condition: Mapped[str] = mapped_column(String(32), nullable=False)
    pretest_score: Mapped[float | None] = mapped_column(Float)
    retest_score: Mapped[float | None] = mapped_column(Float)
    attainment_correct_rate: Mapped[float | None] = mapped_column("l0_correct_rate", Float)
    legacy_transfer_correct_rate: Mapped[float | None] = mapped_column("transfer_correct_rate", Float)
    same_misconception_recurrence_rate: Mapped[float | None] = mapped_column(Float)
    m1_recurrence_rate: Mapped[float | None] = mapped_column(Float)
    legacy_m2_recurrence_rate: Mapped[float | None] = mapped_column("m2_recurrence_rate", Float)
    m3_recurrence_rate: Mapped[float | None] = mapped_column(Float)
    legacy_m4_failure_rate: Mapped[float | None] = mapped_column("m4_failure_rate", Float)
    legacy_unknown_persistence_rate: Mapped[float | None] = mapped_column("unknown_persistence_rate", Float)
    learning_target_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    score_timeline_json: Mapped[dict | None] = mapped_column(JSON)
    misconception_timeline_json: Mapped[dict | None] = mapped_column(JSON)
    learning_burden_json: Mapped[dict | None] = mapped_column(JSON)
    condition_check_json: Mapped[dict | None] = mapped_column(JSON)
    hypothesis_metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    export_name: Mapped[str] = mapped_column(String(80), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(36))
    before_json: Mapped[dict | None] = mapped_column(JSON)
    after_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
