from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
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
            ("completion_reason", "TEXT"),
        ],
        "attempts": [
            ("test_round", "TEXT"),
            ("question_shown_at", datetime_type),
            ("answered_at", datetime_type),
            ("question_body_snapshot", "TEXT"),
            ("option_order_snapshot", json_type),
            ("selected_option_ids", json_type),
        ],
        "tutor_turns": [
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
    """Populate round names for attempts created before the test_round column existed."""
    rows = connection.execute(
        text("SELECT id, participant_id, phase, question_id FROM attempts WHERE test_round IS NULL OR test_round = ''")
    ).mappings().all()
    if not rows:
        return

    question_variants = dict(connection.execute(text("SELECT id, variant_key FROM questions")).all())
    participants_with_final_test = {
        row[0]
        for row in connection.execute(text("SELECT DISTINCT participant_id FROM attempts WHERE phase = 'final_test'")).all()
    }
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
            offset = 1 if row["participant_id"] in participants_with_final_test else 0
            test_round = f"retest_{variant_number + offset}"
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
        )
    )


def _backfill_evaluation_completion_flags(connection) -> None:
    """Keep every historical summary's completion flag consistent with its participant."""
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
                """
            )
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
            )
            WHERE EXISTS (
                SELECT 1
                FROM participants
                WHERE participants.id = evaluation_summaries.participant_id
            )
            """
        )
    )


def _backfill_tutor_prefetch_states(connection) -> None:
    """Make historical tutor sessions explicit normal sessions.

    Older databases have no prefetch lifecycle.  A nullable column is added
    during the lightweight migration, then all existing rows are normalized to
    ``none`` so application code can treat the state as non-null.
    """
    connection.execute(
        text(
            """
            UPDATE tutor_sessions
            SET prefetch_state = 'none'
            WHERE prefetch_state IS NULL OR prefetch_state = ''
            """
        )
    )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
