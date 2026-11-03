from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID
from app.models import Base


settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {"connect_timeout": 5}
engine = create_engine(settings.database_url, future=True, pool_pre_ping=True, pool_timeout=10, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_lightweight_schema_updates()


def _ensure_lightweight_schema_updates() -> None:
    dialect_name = engine.dialect.name
    if dialect_name not in {"sqlite", "postgresql"}:
        return
    json_type = "JSON" if dialect_name == "sqlite" else "JSONB"
    datetime_type = "DATETIME" if dialect_name == "sqlite" else "TIMESTAMP"
    additions = {
        "participants": [
            ("show_pretest_results", "BOOLEAN"),
            ("show_retest_results", "BOOLEAN"),
            ("show_question_reviews", "BOOLEAN"),
            ("first_question_only", "BOOLEAN"),
            ("learning_material_glossary_mode", "VARCHAR(32)"),
            ("question_set_mode", "VARCHAR(32)"),
            ("test_page_mode", "VARCHAR(32)"),
            ("completion_reason", "TEXT"),
            ("learning_content_version", "INTEGER"),
            ("experiment_spec_version", "INTEGER"),
            ("protocol_id", "VARCHAR(80)"),
            ("option_order_mode", "VARCHAR(32)"),
            ("retest_cycles_completed", "INTEGER"),
            ("consent_document_version", "VARCHAR(80)"),
            ("consented_at", datetime_type),
        ],
        "participant_surveys": [
            ("survey_version", "VARCHAR(80)"),
            ("responses_json", json_type),
        ],
        "runtime_settings": [("first_question_only", "BOOLEAN"), ("question_set_mode", "VARCHAR(32)"), ("show_pretest_results", "BOOLEAN"), ("show_question_reviews", "BOOLEAN"), ("learning_material_glossary_mode", "VARCHAR(32)")],
        "attempts": [
            ("test_round", "TEXT"),
            ("question_shown_at", datetime_type),
            ("answered_at", datetime_type),
            ("question_body_snapshot", "TEXT"),
            ("option_order_snapshot", json_type),
            ("glossary_snapshot", json_type),
            ("question_review_acknowledged_at", datetime_type),
            ("test_page_timing_json", json_type),
            ("selected_option_ids", json_type),
        ],
        "tutor_turns": [
            ("material_viewed_at", datetime_type),
            ("question_shown_at", datetime_type),
            ("answered_at", datetime_type),
            ("response_time_sec", "FLOAT"),
        ],
        "tutor_sessions": [
            ("prefetch_state", "VARCHAR(32)"),
            ("prefetch_source_session_id", "VARCHAR(36)"),
            ("prefetch_requested_at", datetime_type),
            ("prefetch_generating_at", datetime_type),
            ("prefetch_ready_at", datetime_type),
            ("prefetch_consumed_at", datetime_type),
            ("prefetch_failed_at", datetime_type),
            ("prefetch_discarded_at", datetime_type),
            ("prefetch_error_code", "VARCHAR(80)"),
        ],
        "evaluation_summaries": [
            ("hypothesis_metrics_json", json_type),
            ("score_timeline_json", json_type),
            ("misconception_timeline_json", json_type),
            ("learning_burden_json", json_type),
            ("condition_check_json", json_type),
        ],
    }
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table, columns in additions.items():
            if table not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table)}
            for name, column_type in columns:
                if name not in existing_columns:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}"))
        _backfill_attempt_test_rounds(connection)
        _backfill_completion_reasons(connection)
        _backfill_evaluation_completion_flags(connection)
        _backfill_tutor_prefetch_states(connection)


def _backfill_attempt_test_rounds(connection) -> None:
    """Repair the retained easy format, never guess missing split-assessment rounds."""
    rows = connection.execute(
        text("SELECT id, participant_id, phase, question_id FROM attempts WHERE (test_round IS NULL OR test_round = '') AND participant_id IN (SELECT id FROM participants WHERE experiment_spec_version = :spec_version AND protocol_id = :protocol_id AND question_set_mode = :mode)"),
        {"spec_version": CURRENT_EXPERIMENT_SPEC_VERSION, "protocol_id": CURRENT_PROTOCOL_ID, "mode": "easy"},
    ).mappings().all()
    if not rows:
        return

    question_variants = dict(connection.execute(text("SELECT id, variant_key FROM questions")).all())
    for row in rows:
        phase = row["phase"]
        if phase == "pretest":
            test_round = "test"
        elif phase == "final_test":
            test_round = "retest_1"
        elif phase == "retest":
            variant_key = str(question_variants.get(row["question_id"], "") or "")
            try:
                variant_number = int(variant_key.removeprefix("retest_v"))
            except ValueError:
                variant_number = 1
            test_round = f"retest_{variant_number}"
        else:
            continue
        connection.execute(
            text("UPDATE attempts SET test_round = :test_round WHERE id = :attempt_id"),
            {"test_round": test_round, "attempt_id": row["id"]},
        )


def _backfill_completion_reasons(connection) -> None:
    """Repair completion metadata for finished participants from the audit trail."""
    connection.execute(
        text(
            """
            UPDATE participants
            SET completion_reason = CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM audit_events
                    WHERE audit_events.entity_type = 'participant'
                      AND audit_events.entity_id = participants.id
                      AND audit_events.action = 'give_up_experiment'
                ) THEN 'give_up'
                ELSE 'completed'
            END
            WHERE participants.current_step = 'finish'
              AND participants.experiment_spec_version = :spec_version
              AND participants.protocol_id = :protocol_id
              AND participants.completed_at IS NOT NULL
              AND (
                  participants.completion_reason IS NULL
                  OR participants.completion_reason = ''
                  OR EXISTS (
                      SELECT 1
                      FROM audit_events
                      WHERE audit_events.entity_type = 'participant'
                        AND audit_events.entity_id = participants.id
                        AND audit_events.action = 'give_up_experiment'
                  )
              )
            """
        ),
        {"spec_version": CURRENT_EXPERIMENT_SPEC_VERSION, "protocol_id": CURRENT_PROTOCOL_ID},
    )


def _backfill_evaluation_completion_flags(connection) -> None:
    """Repair current-version summaries only; historical trials must remain untouched."""
    if engine.dialect.name == "postgresql":
        connection.execute(
            text(
                """
                UPDATE evaluation_summaries AS summaries
                SET completed = (
                    participants.current_step = 'finish'
                    AND participants.completed_at IS NOT NULL
                    AND COALESCE(participants.completion_reason, '') <> 'give_up'
                )
                FROM participants
                WHERE participants.id = summaries.participant_id
                  AND participants.experiment_spec_version = :spec_version
                  AND participants.protocol_id = :protocol_id
                """
            ),
            {"spec_version": CURRENT_EXPERIMENT_SPEC_VERSION, "protocol_id": CURRENT_PROTOCOL_ID},
        )
        return

    connection.execute(
        text(
            """
            UPDATE evaluation_summaries
            SET completed = (
                SELECT CASE
                    WHEN participants.current_step = 'finish'
                     AND participants.completed_at IS NOT NULL
                     AND COALESCE(participants.completion_reason, '') <> 'give_up'
                    THEN 1
                    ELSE 0
                END
                FROM participants
                WHERE participants.id = evaluation_summaries.participant_id
                  AND participants.experiment_spec_version = :spec_version
                  AND participants.protocol_id = :protocol_id
            )
            WHERE EXISTS (
                SELECT 1
                FROM participants
                WHERE participants.id = evaluation_summaries.participant_id
                  AND participants.experiment_spec_version = :spec_version
                  AND participants.protocol_id = :protocol_id
            )
            """
        ),
        {"spec_version": CURRENT_EXPERIMENT_SPEC_VERSION, "protocol_id": CURRENT_PROTOCOL_ID},
    )


def _backfill_tutor_prefetch_states(connection) -> None:
    """Normalize missing prefetch state for current-version sessions only."""
    connection.execute(
        text(
            """
            UPDATE tutor_sessions
            SET prefetch_state = 'none'
            WHERE (prefetch_state IS NULL OR prefetch_state = '')
              AND participant_id IN (SELECT id FROM participants WHERE experiment_spec_version = :spec_version AND protocol_id = :protocol_id)
            """
        ),
        {"spec_version": CURRENT_EXPERIMENT_SPEC_VERSION, "protocol_id": CURRENT_PROTOCOL_ID},
    )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
