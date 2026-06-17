from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import Base


settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, future=True, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_compatible_columns()


def _ensure_compatible_columns() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    column_specs = {
        "learning_sessions": {
            "concept_phase1_attempt_count": "INTEGER",
            "concept_phase2_attempt_count": "INTEGER",
            "phase2_retry_count": "INTEGER",
            "phase2_prompt": "TEXT",
            "phase2_light_conditions": "TEXT",
            "phase2_expected_answer": "TEXT",
        },
        "prerequisite_terms": {
            "generation_reason": "TEXT",
        },
        "concept_understanding_attempts": {
            "concept_phase": "VARCHAR(32)",
            "material_shown": "BOOLEAN",
            "light_condition_text": "TEXT",
            "independent_explanation_success": "BOOLEAN",
            "return_to_phase1": "BOOLEAN",
            "rubric_scores": "JSON",
        },
        "evaluation_summaries": {
            "prerequisite_pass_rate": "FLOAT",
            "concept_pass_rate": "FLOAT",
            "concept_phase1_pass_rate": "FLOAT",
            "concept_phase2_success_rate": "FLOAT",
            "phase2_after_retry_success_rate": "FLOAT",
            "phase2_max_retry_rate": "FLOAT",
            "phase2_pass_retest_correct_rate": "FLOAT",
            "phase2_fail_retest_correct_rate": "FLOAT",
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
