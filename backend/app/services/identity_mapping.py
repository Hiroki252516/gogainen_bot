"""Direct identifiers live here only, outside the research SQLAlchemy database."""
from __future__ import annotations

import csv
import io
import sqlite3
import unicodedata
from contextlib import contextmanager
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.engine import make_url

from app.core.config import get_settings

CONSENT_DOCUMENT_VERSION = "consent-2026-11-04-draft-v2"


def validate_student_number(value: str) -> str:
    # Check the original input too: a trailing newline must not disappear in strip().
    if any(unicodedata.category(char).startswith("C") for char in value):
        raise HTTPException(400, "学籍番号に改行・制御文字は使用できません。")
    normalized = value.strip()
    if not 1 <= len(normalized) <= 64:
        raise HTTPException(400, "学籍番号は1〜64文字で入力してください。")
    return normalized


@contextmanager
def connection():
    path = Path(get_settings().identity_mapping_path).resolve()
    research_url = make_url(get_settings().database_url)
    if research_url.drivername.startswith("sqlite") and research_url.database not in {None, ":memory:"}:
        if path == Path(research_url.database).resolve():
            raise RuntimeError("対応表の保存先は研究DBから分離してください。")
    if path.is_relative_to(Path(get_settings().export_dir).resolve()):
        raise RuntimeError("対応表の保存先は研究用エクスポートから分離してください。")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.touch(mode=0o600, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA secure_delete=ON")
        db.execute("""CREATE TABLE IF NOT EXISTS identity_mappings (
            participant_id TEXT PRIMARY KEY, display_code TEXT NOT NULL,
            student_number TEXT NOT NULL, created_at TEXT NOT NULL,
            registration_key TEXT NOT NULL UNIQUE)""")
        db.commit()
        yield db
    finally:
        db.close()


def save_mapping(participant_id: str, display_code: str, student_number: str,
                 created_at: str, registration_key: str) -> None:
    with connection() as db, db:
        # A failed/crashed research transaction may have left a staged mapping.
        # Only the owner of the same idempotency reservation reaches this call.
        db.execute("DELETE FROM identity_mappings WHERE registration_key = ?", (registration_key,))
        db.execute("INSERT INTO identity_mappings VALUES (?, ?, ?, ?, ?)",
                   (participant_id, display_code, student_number, created_at, registration_key))


def list_mappings() -> list[dict]:
    with connection() as db:
        return [dict(row) for row in db.execute(
            "SELECT participant_id, display_code, student_number, created_at "
            "FROM identity_mappings ORDER BY created_at, participant_id")]


def delete_mapping(participant_id: str | None = None) -> int:
    with connection() as db:
        with db:
            if participant_id is None:
                count = db.execute("DELETE FROM identity_mappings").rowcount
            else:
                count = db.execute("DELETE FROM identity_mappings WHERE participant_id = ?", (participant_id,)).rowcount
        return count


def mapping_csv(rows: list[dict]) -> str:
    def safe(value: str) -> str:
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    keys = ("student_number", "participant_id", "display_code", "created_at")
    writer.writerow(keys)
    for row in rows:
        writer.writerow([safe(str(row[key])) for key in keys])
    return "\ufeff" + output.getvalue()
