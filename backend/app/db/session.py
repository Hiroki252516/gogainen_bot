from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import Base


settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, future=True, pool_pre_ping=True, connect_args=connect_args)
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
        "attempts": [
            ("question_shown_at", datetime_type),
            ("answered_at", datetime_type),
            ("question_body_snapshot", "TEXT"),
            ("option_order_snapshot", json_type),
        ],
        "tutor_turns": [
            ("question_shown_at", datetime_type),
            ("answered_at", datetime_type),
            ("response_time_sec", "FLOAT"),
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


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
