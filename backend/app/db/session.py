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
    _assert_retired_question_mode_is_purged()
    _ensure_lightweight_schema_updates()


def _assert_retired_question_mode_is_purged() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if any(
        table in tables and "question_set_mode" in {
            column["name"] for column in inspector.get_columns(table)
        }
        for table in ("participants", "runtime_settings")
    ):
        raise RuntimeError(
            "legacy question-mode data must be removed with the guarded purge utility before startup"
        )


def _ensure_lightweight_schema_updates() -> None:
    dialect_name = engine.dialect.name
    if dialect_name not in {"sqlite", "postgresql"}:
        return
    json_type = "JSON" if dialect_name == "sqlite" else "JSONB"
    datetime_type = "DATETIME" if dialect_name == "sqlite" else "TIMESTAMP"
    additions = {
        "question_options": [("rationale", "TEXT")],
        "participants": [
            ("show_pretest_results", "BOOLEAN"),
            ("show_retest_results", "BOOLEAN"),
            ("show_question_reviews", "BOOLEAN"),
            ("first_question_only", "BOOLEAN"),
            ("test_content_mode", "VARCHAR(32)"),
            ("learning_material_glossary_mode", "VARCHAR(32)"),
            ("test_page_mode", "VARCHAR(32)"),
            ("completion_reason", "TEXT"),
            ("learning_content_version", "INTEGER"),
            ("experiment_spec_version", "INTEGER"),
            ("protocol_id", "VARCHAR(160)"),
            ("option_order_mode", "VARCHAR(32)"),
            ("retest_cycles_completed", "INTEGER"),
            ("consent_document_version", "VARCHAR(80)"),
            ("consented_at", datetime_type),
        ],
        "participant_surveys": [
            ("survey_version", "VARCHAR(80)"),
            ("responses_json", json_type),
        ],
        "runtime_settings": [("first_question_only", "BOOLEAN"), ("test_content_mode", "VARCHAR(32)"), ("show_pretest_results", "BOOLEAN"), ("show_question_reviews", "BOOLEAN"), ("learning_material_glossary_mode", "VARCHAR(32)")],
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
        if "participants" in existing_tables:
            _ensure_participant_code_capacity(connection, dialect_name)
            _ensure_protocol_id_capacity(
                connection,
                dialect_name,
                inspect(connection).get_columns("participants"),
            )
        _backfill_completion_reasons(connection)
        _backfill_evaluation_completion_flags(connection)
        _backfill_tutor_prefetch_states(connection)


def _ensure_participant_code_capacity(connection, dialect_name: str) -> None:
    """Widen participant identifiers and all database references without rewriting values."""
    if dialect_name != "postgresql":
        return

    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    participant_columns = {
        column["name"]: column for column in inspector.get_columns("participants")
    }
    current_length = getattr(participant_columns.get("id", {}).get("type"), "length", None)
    child_references: list[tuple[str, str, dict]] = []
    for table in sorted(tables - {"participants"}):
        for foreign_key in inspector.get_foreign_keys(table):
            if foreign_key.get("referred_table") == "participants" and "id" in foreign_key.get("referred_columns", []):
                for column in foreign_key.get("constrained_columns", []):
                    child_references.append((table, column, foreign_key))

    child_columns: set[tuple[str, str]] = set()
    for table, column, _ in child_references:
        metadata = next(
            (item for item in inspector.get_columns(table) if item["name"] == column),
            None,
        )
        length = getattr(metadata["type"], "length", None) if metadata else None
        if length is not None and length < 64:
            child_columns.add((table, column))

    participants_need_widening = current_length is not None and current_length < 64
    explicit_columns = {
        ("participants", "display_code"),
        ("idempotency_records", "participant_id"),
        ("audit_events", "entity_id"),
        ("participant_sessions", "participant_id"),
    }
    needs_explicit_widening = False
    for table, column in explicit_columns:
        if table not in tables:
            continue
        metadata = next(
            (item for item in inspector.get_columns(table) if item["name"] == column),
            None,
        )
        length = getattr(metadata["type"], "length", None) if metadata else None
        needs_explicit_widening = needs_explicit_widening or bool(metadata and (length is None or length < 64))
    if not participants_need_widening and not child_columns and not needs_explicit_widening:
        return

    preparer = connection.dialect.identifier_preparer

    def quoted(identifier: str) -> str:
        return preparer.quote(identifier)

    constraints: dict[tuple[str, str], dict] = {}
    for table, column, foreign_key in child_references:
        if (table, column) not in child_columns and not participants_need_widening:
            continue
        name = foreign_key.get("name")
        if not name:
            raise RuntimeError(f"Cannot safely widen unnamed foreign key on {table}.{column}")
        constraints[(table, name)] = foreign_key

    for table, name in constraints:
        connection.execute(
            text(f"ALTER TABLE {quoted(table)} DROP CONSTRAINT {quoted(name)}")
        )

    columns_to_widen = {("participants", "id"), ("participants", "display_code")}
    columns_to_widen.update(child_columns)
    for table, column in (
        ("idempotency_records", "participant_id"),
        ("audit_events", "entity_id"),
        ("participant_sessions", "participant_id"),
    ):
        if table not in tables:
            continue
        metadata = next(
            (item for item in inspector.get_columns(table) if item["name"] == column),
            None,
        )
        length = getattr(metadata["type"], "length", None) if metadata else None
        if metadata and (length is None or length < 64):
            columns_to_widen.add((table, column))

    for table, column in sorted(columns_to_widen):
        if table not in tables:
            continue
        metadata = next(
            (item for item in inspector.get_columns(table) if item["name"] == column),
            None,
        )
        length = getattr(metadata["type"], "length", None) if metadata else None
        if metadata and (length is None or length < 64):
            connection.execute(
                text(f"ALTER TABLE {quoted(table)} ALTER COLUMN {quoted(column)} TYPE VARCHAR(64)")
            )

    for (table, name), foreign_key in constraints.items():
        constrained = ", ".join(quoted(column) for column in foreign_key["constrained_columns"])
        referred = ", ".join(quoted(column) for column in foreign_key["referred_columns"])
        statement = (
            f"ALTER TABLE {quoted(table)} ADD CONSTRAINT {quoted(name)} "
            f"FOREIGN KEY ({constrained}) REFERENCES {quoted('participants')} ({referred})"
        )
        ondelete = (foreign_key.get("options") or {}).get("ondelete")
        onupdate = (foreign_key.get("options") or {}).get("onupdate")
        if ondelete:
            statement += f" ON DELETE {ondelete}"
        if onupdate:
            statement += f" ON UPDATE {onupdate}"
        connection.execute(text(statement))


def _ensure_protocol_id_capacity(connection, dialect_name: str, participant_columns: list[dict]) -> None:
    if dialect_name != "postgresql":
        return
    protocol_id = next((column for column in participant_columns if column["name"] == "protocol_id"), None)
    current_length = getattr(protocol_id["type"], "length", None) if protocol_id else None
    if current_length is not None and current_length < 160:
        connection.execute(
            text("ALTER TABLE participants ALTER COLUMN protocol_id TYPE VARCHAR(160)")
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
