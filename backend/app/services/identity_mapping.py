"""Validation and deletion cleanup for legacy external identity mappings."""
from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.engine import make_url

from app.core.config import get_settings

CONSENT_DOCUMENT_VERSION = "consent-2026-11-12-revised-v1"


def validate_research_code(value: str) -> str:
    if re.fullmatch(r"[0-9]{1,64}", value) is None:
        raise HTTPException(400, "研究用コードは半角数字1〜64桁で入力してください。")
    return value


def _mapping_path() -> Path:
    path = Path(get_settings().identity_mapping_path).resolve()
    research_url = make_url(get_settings().database_url)
    if research_url.drivername.startswith("sqlite") and research_url.database not in {None, ":memory:"}:
        if path == Path(research_url.database).resolve():
            raise RuntimeError("対応表の保存先は研究DBから分離してください。")
    if path.is_relative_to(Path(get_settings().export_dir).resolve()):
        raise RuntimeError("対応表の保存先は研究用エクスポートから分離してください。")
    return path


def delete_participant_mappings(participant_id: str) -> int:
    """Remove only this participant's rows when an explicit deletion is requested.

    Registration and ordinary reads do not open, create, or migrate this SQLite file.
    """
    path = _mapping_path()
    if not path.is_file():
        return 0

    deleted = 0
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute("PRAGMA secure_delete=ON")
        tables = {
            row[0]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for table in ("identity_mappings", "research_code_mappings"):
            if table in tables:
                deleted += db.execute(
                    f'DELETE FROM "{table}" WHERE participant_id = ?', (participant_id,)
                ).rowcount
    return deleted
