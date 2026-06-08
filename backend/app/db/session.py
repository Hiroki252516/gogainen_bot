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
    if "evaluation_summaries" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("evaluation_summaries")}
    missing = [column for column in ("prerequisite_pass_rate", "concept_pass_rate") if column not in existing]
    if not missing:
        return
    with engine.begin() as conn:
        for column in missing:
            if engine.dialect.name == "postgresql":
                conn.execute(text(f"ALTER TABLE evaluation_summaries ADD COLUMN IF NOT EXISTS {column} FLOAT"))
            else:
                conn.execute(text(f"ALTER TABLE evaluation_summaries ADD COLUMN {column} FLOAT"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
