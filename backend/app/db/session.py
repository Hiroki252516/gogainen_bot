from collections.abc import Generator
import time

from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import Base


settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, future=True, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db(max_attempts: int = 15, retry_delay_sec: float = 1.0) -> None:
    for attempt in range(1, max_attempts + 1):
        try:
            Base.metadata.create_all(bind=engine)
            _ensure_compatible_columns()
            return
        except OperationalError:
            if attempt == max_attempts:
                raise
            time.sleep(retry_delay_sec)


def _ensure_compatible_columns() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    column_specs = {
        "participants": {
            "content_version_id": "VARCHAR(36)",
        },
        "questions": {
            "content_version_id": "VARCHAR(36)",
        },
        "learning_sessions": {
            "content_version_id": "VARCHAR(36)",
            "prerequisite_set_version": "VARCHAR(160)",
            "current_stage": "VARCHAR(64)",
            "current_prerequisite_key": "VARCHAR(120)",
            "current_slot_key": "VARCHAR(180)",
            "current_attempt_index": "INTEGER DEFAULT 1",
            "current_cycle_index": "INTEGER DEFAULT 1",
            "current_material_id": "VARCHAR(36)",
            "review_return_slot_key": "VARCHAR(180)",
            "review_prerequisite_key": "VARCHAR(120)",
            "phase2_forced_completion": "BOOLEAN DEFAULT FALSE",
            "technical_block_reason": "TEXT",
            "concept_phase1_attempt_count": "INTEGER",
            "concept_phase2_attempt_count": "INTEGER",
            "phase2_retry_count": "INTEGER",
            "phase2_prompt": "TEXT",
            "phase2_light_conditions": "TEXT",
            "phase2_expected_answer": "TEXT",
            "phase1_cycle_index": "INTEGER DEFAULT 1",
            "phase1_cycle_attempt_count": "INTEGER DEFAULT 0",
            "pending_clarification": "JSON",
        },
        "prerequisite_terms": {
            "generation_reason": "TEXT",
            "current_status": "VARCHAR(64) DEFAULT 'unknown'",
            "primary_misconception_type": "VARCHAR(32)",
            "secondary_misconception_type": "VARCHAR(32)",
            "resolution_stage": "VARCHAR(32) DEFAULT 'none'",
            "teaching_strategy": "VARCHAR(80)",
            "latest_observation_id": "VARCHAR(36)",
            "diagnostic_focus": "JSON",
        },
        "learner_states": {
            "resolution_stage": "VARCHAR(32) DEFAULT 'none'",
            "latest_observation_id": "VARCHAR(36)",
        },
        "term_understanding_attempts": {
            "diagnosis_observation_id": "VARCHAR(36)",
            "attempt_kind": "VARCHAR(32) DEFAULT 'normal'",
            "counts_toward_limit": "BOOLEAN DEFAULT TRUE",
            "clarification_parent_attempt_id": "VARCHAR(36)",
            "presented_question": "TEXT",
            "diagnostic_focus": "JSON",
            "primary_misconception_type": "VARCHAR(32)",
            "secondary_misconception_type": "VARCHAR(32)",
        },
        "concept_understanding_attempts": {
            "concept_phase": "VARCHAR(32)",
            "material_shown": "BOOLEAN",
            "light_condition_text": "TEXT",
            "independent_explanation_success": "BOOLEAN",
            "return_to_phase1": "BOOLEAN",
            "rubric_scores": "JSON",
            "diagnosis_observation_id": "VARCHAR(36)",
            "phase1_cycle_index": "INTEGER DEFAULT 1",
            "attempt_kind": "VARCHAR(32) DEFAULT 'normal'",
            "counts_toward_limit": "BOOLEAN DEFAULT TRUE",
            "clarification_parent_attempt_id": "VARCHAR(36)",
            "presented_question": "TEXT",
            "diagnostic_focus": "JSON",
            "primary_misconception_type": "VARCHAR(32)",
            "secondary_misconception_type": "VARCHAR(32)",
        },
        "evaluation_summaries": {
            "pretest_score_all_terms": "FLOAT",
            "retest_score_all_terms": "FLOAT",
            "learning_target_retest_score": "FLOAT",
            "non_target_retest_retention_rate": "FLOAT",
            "prerequisite_pass_rate": "FLOAT",
            "prerequisite_required_question_accuracy": "FLOAT",
            "prerequisite_first_attempt_accuracy": "FLOAT",
            "prerequisite_retry_recovery_rate": "FLOAT",
            "prerequisite_forced_resolution_rate": "FLOAT",
            "concept_pass_rate": "FLOAT",
            "concept_phase1_pass_rate": "FLOAT",
            "phase1_all_questions_pass_rate": "FLOAT",
            "phase1_forced_resolution_rate": "FLOAT",
            "concept_phase2_success_rate": "FLOAT",
            "no_material_concept_discrimination_accuracy": "FLOAT",
            "phase2_after_retry_success_rate": "FLOAT",
            "phase2_max_retry_rate": "FLOAT",
            "phase2_forced_completion_rate": "FLOAT",
            "phase2_pass_retest_correct_rate": "FLOAT",
            "phase2_fail_retest_correct_rate": "FLOAT",
            "learning_misconception_persistence_rate": "FLOAT",
            "m1_resolution_rate": "FLOAT",
            "m2_resolution_rate": "FLOAT",
            "m3_resolution_rate": "FLOAT",
            "strategy_next_response_success_rate": "FLOAT",
            "phase2_misconception_recurrence_rate": "FLOAT",
            "learning_resolved_retest_correct_rate": "FLOAT",
        },
    }
    missing_by_table: dict[str, list[tuple[str, str]]] = {}
    for table, specs in column_specs.items():
        if table not in tables:
            continue
        existing = {column["name"] for column in inspector.get_columns(table)}
        missing = [(column, column_type) for column, column_type in specs.items() if column not in existing]
        if missing:
            missing_by_table[table] = missing
    if not missing_by_table:
        return
    with engine.begin() as conn:
        for table, missing in missing_by_table.items():
            for column, column_type in missing:
                if engine.dialect.name == "postgresql":
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {column_type}"))
                else:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
