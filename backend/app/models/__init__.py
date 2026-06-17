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
    display_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    group_condition: Mapped[str] = mapped_column(String(32), nullable=False)
    assignment_method: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    consent_checked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_step: Mapped[str] = mapped_column(String(64), default="start", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, nullable=False)


class ParticipantSurvey(Base):
    __tablename__ = "participant_surveys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(String(36), ForeignKey("participants.id"), nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
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
    expected_keywords: Mapped[list | None] = mapped_column(JSON)
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
    attempt_index: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    selected_option_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("question_options.id"))
    free_text_answer: Mapped[str | None] = mapped_column(Text)
    reason_text: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[int | None] = mapped_column(Integer)
    response_time_sec: Mapped[float | None] = mapped_column(Float)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    score: Mapped[float | None] = mapped_column(Float)
    diagnosed_status: Mapped[str | None] = mapped_column(String(64))
    misconception_type: Mapped[str | None] = mapped_column(String(32))
    secondary_misconception_type: Mapped[str | None] = mapped_column(String(32))
    misconception_confidence: Mapped[float | None] = mapped_column(Float)
    natural_language_diagnosis: Mapped[str | None] = mapped_column(Text)
    recurrence_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    l0_success: Mapped[bool | None] = mapped_column(Boolean)
    transfer_success: Mapped[bool | None] = mapped_column(Boolean)
    requires_manual_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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
    secondary_misconception: Mapped[str | None] = mapped_column(String(32))
    scaffolding_level: Mapped[str] = mapped_column(String(16), nullable=False)
    teaching_strategy: Mapped[str | None] = mapped_column(String(80))
    previous_teaching_strategy: Mapped[str | None] = mapped_column(String(80))
    stable_correct_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recurrence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    l0_success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    transfer_success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempt_id: Mapped[str | None] = mapped_column(String(36))
    last_tutor_turn_id: Mapped[str | None] = mapped_column(String(36))
    state_summary: Mapped[str | None] = mapped_column(Text)
    updated_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, nullable=False)


class LearningSession(Base):
    __tablename__ = "learning_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(String(36), ForeignKey("participants.id"), nullable=False)
    term_id: Mapped[str] = mapped_column(String(36), ForeignKey("terms.id"), nullable=False)
    group_condition: Mapped[str] = mapped_column(String(32), nullable=False)
    session_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="not_started", nullable=False)
    current_prerequisite_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    term_pass_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    concept_attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    concept_phase1_attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    concept_phase2_attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    phase2_retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    concept_material: Mapped[str | None] = mapped_column(Text)
    concept_prompt: Mapped[str | None] = mapped_column(Text)
    concept_expected_answer: Mapped[str | None] = mapped_column(Text)
    phase2_prompt: Mapped[str | None] = mapped_column(Text)
    phase2_light_conditions: Mapped[str | None] = mapped_column(Text)
    phase2_expected_answer: Mapped[str | None] = mapped_column(Text)
    last_feedback: Mapped[str | None] = mapped_column(Text)
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, nullable=False)


class PrerequisiteTerm(Base):
    __tablename__ = "prerequisite_terms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    learning_session_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_sessions.id"), nullable=False)
    term_label: Mapped[str] = mapped_column(String(160), nullable=False)
    material: Mapped[str] = mapped_column(Text, nullable=False)
    check_question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer: Mapped[str] = mapped_column(Text, nullable=False)
    generation_reason: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="not_started", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_feedback: Mapped[str | None] = mapped_column(Text)
    remediation_material: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, nullable=False)


class TermUnderstandingAttempt(Base):
    __tablename__ = "term_understanding_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    prerequisite_term_id: Mapped[str] = mapped_column(String(36), ForeignKey("prerequisite_terms.id"), nullable=False)
    participant_id: Mapped[str] = mapped_column(String(36), ForeignKey("participants.id"), nullable=False)
    learning_session_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_sessions.id"), nullable=False)
    attempt_index: Mapped[int] = mapped_column(Integer, nullable=False)
    learner_answer: Mapped[str] = mapped_column(Text, nullable=False)
    is_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    feedback: Mapped[str] = mapped_column(Text, nullable=False)
    remediation_material: Mapped[str | None] = mapped_column(Text)
    grading_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class ConceptUnderstandingAttempt(Base):
    __tablename__ = "concept_understanding_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    learning_session_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_sessions.id"), nullable=False)
    participant_id: Mapped[str] = mapped_column(String(36), ForeignKey("participants.id"), nullable=False)
    attempt_index: Mapped[int] = mapped_column(Integer, nullable=False)
    concept_phase: Mapped[str] = mapped_column(String(32), default="phase1", nullable=False)
    concept_material: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    material_shown: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    light_condition_text: Mapped[str | None] = mapped_column(Text)
    learner_answer: Mapped[str] = mapped_column(Text, nullable=False)
    is_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    feedback: Mapped[str] = mapped_column(Text, nullable=False)
    missing_prerequisite_ids: Mapped[list | None] = mapped_column(JSON)
    review_prerequisite_ids: Mapped[list | None] = mapped_column(JSON)
    independent_explanation_success: Mapped[bool | None] = mapped_column(Boolean)
    return_to_phase1: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rubric_scores: Mapped[dict | None] = mapped_column(JSON)
    grading_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class TutorSession(Base):
    __tablename__ = "tutor_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(String(36), ForeignKey("participants.id"), nullable=False)
    term_id: Mapped[str] = mapped_column(String(36), ForeignKey("terms.id"), nullable=False)
    session_index: Mapped[int] = mapped_column(Integer, nullable=False)
    group_condition: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class TutorTurn(Base):
    __tablename__ = "tutor_turns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tutor_session_id: Mapped[str] = mapped_column(String(36), ForeignKey("tutor_sessions.id"), nullable=False)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    scaffolding_level: Mapped[str | None] = mapped_column(String(16))
    teaching_strategy: Mapped[str] = mapped_column(String(80), nullable=False)
    previous_teaching_strategy: Mapped[str | None] = mapped_column(String(80))
    strategy_changed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tutor_message: Mapped[str] = mapped_column(Text, nullable=False)
    learner_prompt: Mapped[str | None] = mapped_column(Text)
    practice_question_json: Mapped[dict | None] = mapped_column(JSON)
    learner_response: Mapped[str | None] = mapped_column(Text)
    learner_confidence: Mapped[int | None] = mapped_column(Integer)
    ai_feedback: Mapped[str | None] = mapped_column(Text)
    diagnosis_json: Mapped[dict | None] = mapped_column(JSON)
    grading_json: Mapped[dict | None] = mapped_column(JSON)
    next_scaffolding_level: Mapped[str | None] = mapped_column(String(16))
    forbidden_help_given: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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
    l0_correct_rate: Mapped[float | None] = mapped_column(Float)
    transfer_correct_rate: Mapped[float | None] = mapped_column(Float)
    same_misconception_recurrence_rate: Mapped[float | None] = mapped_column(Float)
    m1_recurrence_rate: Mapped[float | None] = mapped_column(Float)
    m2_recurrence_rate: Mapped[float | None] = mapped_column(Float)
    m3_recurrence_rate: Mapped[float | None] = mapped_column(Float)
    m4_failure_rate: Mapped[float | None] = mapped_column(Float)
    unknown_persistence_rate: Mapped[float | None] = mapped_column(Float)
    prerequisite_pass_rate: Mapped[float | None] = mapped_column(Float)
    concept_pass_rate: Mapped[float | None] = mapped_column(Float)
    concept_phase1_pass_rate: Mapped[float | None] = mapped_column(Float)
    concept_phase2_success_rate: Mapped[float | None] = mapped_column(Float)
    phase2_after_retry_success_rate: Mapped[float | None] = mapped_column(Float)
    phase2_max_retry_rate: Mapped[float | None] = mapped_column(Float)
    phase2_pass_retest_correct_rate: Mapped[float | None] = mapped_column(Float)
    phase2_fail_retest_correct_rate: Mapped[float | None] = mapped_column(Float)
    learning_target_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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
