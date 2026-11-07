"""Purge retired easy-mode records without exposing participant identifiers.

Research execution requires explicit process environment, confirmation of the
database name, confirmation that the application is stopped, and a separate
identity-mapping SQLite path. The default command is a count-only dry run.
"""
from __future__ import annotations

import argparse
import csv
import ipaddress
import json
import os
import re
import sqlite3
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url


MANIFEST_TABLE = "_easy_mode_purge_manifest"
AUDIT_TABLE = "easy_mode_purge_audits"
MANIFEST_COUNTS_KEY = "__aggregate_counts__"
JSON_FIELDS = {
    "ai_call_logs": ("request_payload", "response_payload"),
    "audit_events": ("before_json", "after_json"),
}


def _q(engine: Engine, name: str) -> str:
    return engine.dialect.identifier_preparer.quote(name)


def _contains_any(value: Any, identifiers: set[str]) -> bool:
    if isinstance(value, str):
        return value in identifiers
    if isinstance(value, dict):
        return any(_contains_any(key, identifiers) or _contains_any(item, identifiers)
                   for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_any(item, identifiers) for item in value)
    return False


def _contains_identifier_token(value: Any, identifiers: set[str]) -> bool:
    if not isinstance(value, str):
        return False
    for identifier in identifiers:
        if identifier and re.search(
            rf"(?<![\w-]){re.escape(identifier)}(?![\w-])", value
        ):
            return True
    return False


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    return value


def _tables_with_column(connection, table_names: set[str], column: str) -> list[str]:
    inspector = inspect(connection)
    return [table for table in sorted(table_names)
            if column in {col["name"] for col in inspector.get_columns(table)}]


def _easy_ids(connection, table_names: set[str]) -> tuple[list[str], dict[str, str]]:
    if "participants" not in table_names:
        return [], {}
    columns = {col["name"] for col in inspect(connection).get_columns("participants")}
    if "question_set_mode" not in columns:
        return [], {}
    rows = connection.execute(text(
        "SELECT id, display_code FROM participants WHERE lower(question_set_mode) = 'easy'"
    )).all()
    return [str(row[0]) for row in rows], {str(row[0]): str(row[1]) for row in rows}


def _easy_question_ids(connection, table_names: set[str]) -> list[str]:
    if "questions" not in table_names:
        return []
    columns = {col["name"] for col in inspect(connection).get_columns("questions")}
    clauses = []
    if "construct_key" in columns:
        clauses.append("lower(construct_key) LIKE '%easy%'")
    if "variant_key" in columns:
        clauses.append("lower(variant_key) LIKE '%easy%'")
    if not clauses:
        return []
    return [str(row[0]) for row in connection.execute(
        text("SELECT id FROM questions WHERE " + " OR ".join(clauses))
    ).all()]


def _all_manifest(connection, engine: Engine) -> tuple[set[str], dict[str, str], dict[str, int]]:
    if MANIFEST_TABLE not in inspect(connection).get_table_names():
        return set(), {}, {}
    rows = connection.execute(text(
        f"SELECT participant_id, display_code, counts_json FROM {_q(engine, MANIFEST_TABLE)}"
    )).all()
    identifiers = {str(row[0]) for row in rows if row[0] not in (None, MANIFEST_COUNTS_KEY)}
    codes = {str(row[0]): str(row[1]) for row in rows
             if row[0] not in (None, MANIFEST_COUNTS_KEY) and row[1] is not None}
    counts_row = next((row for row in rows if row[0] == MANIFEST_COUNTS_KEY), None)
    counts = json.loads(counts_row[2]) if counts_row else {}
    return identifiers, codes, {str(k): int(v) for k, v in counts.items()}


def inspect_counts(engine: Engine, mapping_path: Path | None = None,
                   csv_dir: Path | None = None) -> dict[str, int]:
    counts: Counter[str] = Counter()
    with engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        identifiers, codes, pending_counts = _all_manifest(connection, engine)
        if identifiers:
            counts["pending_participants"] = len(identifiers)
        else:
            ids, codes = _easy_ids(connection, tables)
            identifiers = set(ids)
            counts["participants"] = len(ids)
        if pending_counts:
            counts.update({f"pending_{key}": value for key, value in pending_counts.items()})
        if not identifiers:
            ids, codes = _easy_ids(connection, tables)
            identifiers = set(ids)
        for table in _tables_with_column(connection, tables, "participant_id"):
            if table in {"participants", MANIFEST_TABLE, AUDIT_TABLE}:
                continue
            if identifiers:
                count = connection.execute(text(
                    f"SELECT count(*) FROM {_q(engine, table)} WHERE participant_id IN :ids"
                ).bindparams(bindparam("ids", expanding=True)), {"ids": sorted(identifiers)}).scalar_one()
            else:
                count = 0
            if count:
                counts[table] = int(count)
        if "tutor_sessions" in tables and "tutor_turns" in tables and identifiers:
            counts["tutor_turns"] = int(connection.execute(text(
                "SELECT count(*) FROM tutor_turns t JOIN tutor_sessions s "
                "ON t.tutor_session_id = s.id WHERE s.participant_id IN :ids"
            ).bindparams(bindparam("ids", expanding=True)), {"ids": sorted(identifiers)}).scalar_one())
        question_ids = _easy_question_ids(connection, tables)
        counts["easy_questions"] = len(question_ids)
        if question_ids and "question_options" in tables:
            counts["easy_question_options"] = int(connection.execute(text(
                "SELECT count(*) FROM question_options WHERE question_id IN :ids"
            ).bindparams(bindparam("ids", expanding=True)), {"ids": question_ids}).scalar_one())
        linked_ids = identifiers | set(codes.values())
        for table in ("ai_call_logs", "audit_events"):
            counts[table] += len(_matching_json_row_ids(connection, engine, table, linked_ids))
        if identifiers and "idempotency_records" in tables:
            scopes = connection.execute(text(
                "SELECT scope FROM idempotency_records WHERE participant_id IS NULL"
            )).scalars().all()
            counts["idempotency_scope_records"] = sum(
                any(pid in str(scope).split(":") for pid in identifiers) for scope in scopes
            )
        if "participants" in tables and "question_set_mode" in {
            col["name"] for col in inspect(connection).get_columns("participants")
        }:
            counts["mode_columns"] = 1 + int(
                "runtime_settings" in tables and "question_set_mode" in {
                    col["name"] for col in inspect(connection).get_columns("runtime_settings")
                }
            )
    if mapping_path is not None and mapping_path.is_file() and identifiers:
        with sqlite3.connect(f"file:{mapping_path.resolve()}?mode=ro", uri=True) as mapping:
            if mapping.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='identity_mappings'").fetchone():
                counts["identity_mappings"] = sum(
                    mapping.execute("SELECT count(*) FROM identity_mappings WHERE participant_id = ?", (pid,)).fetchone()[0]
                    for pid in identifiers
                )
    if csv_dir is not None and csv_dir.is_dir() and codes:
        csv_rows, csv_files = _csv_removal_counts(csv_dir, identifiers, set(codes.values()))
        counts["csv_rows"] = csv_rows
        counts["csv_files"] = csv_files
    return dict(sorted(counts.items()))


def _row_contains_identifier(row: dict[str, Any], identifiers: set[str], codes: set[str]) -> bool:
    for key, value in row.items():
        if key and key.strip().lower() in {"participant_id", "display_code", "participant_code"}:
            if str(value) in identifiers or str(value) in codes:
                return True
    return False


def _csv_removal_counts(csv_dir: Path, identifiers: set[str], codes: set[str]) -> tuple[int, int]:
    rows_to_remove = 0
    files_to_remove = 0
    for path in csv_dir.glob("*.csv"):
        if any(path.name == f"{code}_logs.csv" or path.name == f"{code}_logs_excel.csv" for code in codes):
            files_to_remove += 1
            continue
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as source:
                reader = csv.DictReader(source)
                rows_to_remove += sum(_row_contains_identifier(row, identifiers, codes) for row in reader)
        except (OSError, UnicodeError, csv.Error):
            continue
    return rows_to_remove, files_to_remove


def _create_manifest(connection, engine: Engine) -> None:
    qtable = _q(engine, MANIFEST_TABLE)
    connection.execute(text(
        f"CREATE TABLE IF NOT EXISTS {qtable} (participant_id VARCHAR(36) PRIMARY KEY, "
        "display_code VARCHAR(32), counts_json TEXT NOT NULL)"
    ))


def _delete_json_rows(connection, engine: Engine, table: str, identifiers: set[str]) -> int:
    delete_ids = _matching_json_row_ids(connection, engine, table, identifiers)
    if delete_ids:
        connection.execute(text(f"DELETE FROM {_q(engine, table)} WHERE id IN :ids").bindparams(
            bindparam("ids", expanding=True)), {"ids": delete_ids})
    return len(delete_ids)


def _matching_json_row_ids(connection, engine: Engine, table: str, identifiers: set[str]) -> list[str]:
    if table not in inspect(connection).get_table_names():
        return []
    columns = {col["name"] for col in inspect(connection).get_columns(table)}
    wanted = [column for column in JSON_FIELDS.get(table, ()) if column in columns]
    if "id" not in columns:
        return []
    select_columns = ["id", *wanted]
    if table == "audit_events" and "entity_id" in columns:
        select_columns.append("entity_id")
    if table == "ai_call_logs" and "raw_text" in columns:
        select_columns.append("raw_text")
    rows = connection.execute(text(
        f"SELECT {', '.join(_q(engine, col) for col in select_columns)} FROM {_q(engine, table)}"
    )).mappings().all()
    delete_ids: list[str] = []
    for row in rows:
        matched = any(_contains_any(_json_value(row[column]), identifiers) for column in wanted)
        if table == "audit_events":
            matched = matched or row.get("entity_id") in identifiers
        if table == "ai_call_logs":
            matched = matched or _contains_identifier_token(row.get("raw_text"), identifiers)
        if matched:
            delete_ids.append(str(row["id"]))
    return delete_ids


def _delete_easy_records(engine: Engine) -> tuple[dict[str, int], set[str], dict[str, str]]:
    counts: Counter[str] = Counter()
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        _create_manifest(connection, engine)
        identifiers, codes, stored_counts = _all_manifest(connection, engine)
        if not identifiers:
            participant_ids, participant_codes = _easy_ids(connection, tables)
            identifiers = set(participant_ids)
            codes = participant_codes
            for participant_id in participant_ids:
                connection.execute(text(
                    f"INSERT INTO {_q(engine, MANIFEST_TABLE)} (participant_id, display_code, counts_json) "
                    "VALUES (:pid, :code, '{}')"
                ), {"pid": participant_id, "code": participant_codes[participant_id]})
        if not stored_counts:
            easy_questions = _easy_question_ids(connection, tables)
            if easy_questions:
                qids = easy_questions
                participant_columns = {col["name"] for col in inspect(connection).get_columns("participants")}
                if "question_set_mode" in participant_columns:
                    other_cohort = "lower(coalesce(p.question_set_mode, '')) <> 'easy'"
                else:
                    other_cohort = "1 = 1"
                non_easy_attempts = connection.execute(text(
                    "SELECT count(*) FROM attempts a JOIN participants p ON p.id = a.participant_id "
                    f"WHERE a.question_id IN :qids AND {other_cohort}"
                ).bindparams(bindparam("qids", expanding=True)), {"qids": qids}).scalar_one()
                non_easy_orders = connection.execute(text(
                    "SELECT count(*) FROM question_display_orders d JOIN participants p "
                    "ON p.id = d.participant_id WHERE d.question_id IN :qids "
                    f"AND {other_cohort}"
                ).bindparams(bindparam("qids", expanding=True)), {"qids": qids}).scalar_one()
                if non_easy_attempts or non_easy_orders:
                    raise RuntimeError("easy-only question assets are referenced outside the retired cohort")
            else:
                easy_questions = []
            counts["participants"] = len(identifiers)
            for table in _tables_with_column(connection, tables, "participant_id"):
                if table in {"participants", MANIFEST_TABLE, AUDIT_TABLE} or not identifiers:
                    continue
                count = connection.execute(text(
                    f"SELECT count(*) FROM {_q(engine, table)} WHERE participant_id IN :ids"
                ).bindparams(bindparam("ids", expanding=True)), {"ids": sorted(identifiers)}).scalar_one()
                if count:
                    counts[table] = int(count)
            if identifiers and "tutor_sessions" in tables and "tutor_turns" in tables:
                counts["tutor_turns"] = int(connection.execute(text(
                    "SELECT count(*) FROM tutor_turns t JOIN tutor_sessions s ON t.tutor_session_id=s.id "
                    "WHERE s.participant_id IN :ids"
                ).bindparams(bindparam("ids", expanding=True)), {"ids": sorted(identifiers)}).scalar_one())
            counts["easy_questions"] = len(easy_questions)
            if easy_questions and "question_options" in tables:
                counts["easy_question_options"] = int(connection.execute(text(
                    "SELECT count(*) FROM question_options WHERE question_id IN :ids"
                ).bindparams(bindparam("ids", expanding=True)), {"ids": easy_questions}).scalar_one())
            linked_identifiers = identifiers | set(codes.values())
            for table in ("ai_call_logs", "audit_events"):
                counts[table] += _delete_json_rows(connection, engine, table, linked_identifiers)
            if "idempotency_records" in tables:
                rows = connection.execute(text(
                    "SELECT id, scope FROM idempotency_records WHERE participant_id IS NULL"
                )).all()
                idempotency_ids = [row[0] for row in rows if any(pid in str(row[1]).split(":") for pid in identifiers)]
                if idempotency_ids:
                    connection.execute(text("DELETE FROM idempotency_records WHERE id IN :ids").bindparams(
                        bindparam("ids", expanding=True)), {"ids": idempotency_ids})
                    counts["idempotency_records"] += len(idempotency_ids)
            if identifiers:
                session_ids = [row[0] for row in connection.execute(text(
                    "SELECT id FROM tutor_sessions WHERE participant_id IN :ids"
                ).bindparams(bindparam("ids", expanding=True)), {"ids": sorted(identifiers)}).all()] if "tutor_sessions" in tables else []
                if session_ids and "tutor_turns" in tables:
                    connection.execute(text("DELETE FROM tutor_turns WHERE tutor_session_id IN :ids").bindparams(
                        bindparam("ids", expanding=True)), {"ids": session_ids})
                deletion_order = {
                    "participant_surveys": 10,
                    "term_assignments": 20,
                    "question_display_orders": 30,
                    "recurrence_events": 40,
                    "learner_states": 50,
                    "evaluation_summaries": 60,
                    "attempts": 70,
                    "idempotency_records": 80,
                    "tutor_sessions": 90,
                }
                participant_tables = _tables_with_column(connection, tables, "participant_id")
                participant_tables.sort(key=lambda table: deletion_order.get(table, 55))
                for table in participant_tables:
                    if table in {"participants", MANIFEST_TABLE, AUDIT_TABLE}:
                        continue
                    connection.execute(text(
                        f"DELETE FROM {_q(engine, table)} WHERE participant_id IN :ids"
                    ).bindparams(bindparam("ids", expanding=True)), {"ids": sorted(identifiers)})
                connection.execute(text("DELETE FROM participants WHERE id IN :ids").bindparams(
                    bindparam("ids", expanding=True)), {"ids": sorted(identifiers)})
            easy_questions = _easy_question_ids(connection, set(inspect(connection).get_table_names()))
            if easy_questions:
                if "question_display_orders" in tables:
                    connection.execute(text("DELETE FROM question_display_orders WHERE question_id IN :ids").bindparams(
                        bindparam("ids", expanding=True)), {"ids": easy_questions})
                option_ids = [row[0] for row in connection.execute(text(
                    "SELECT id FROM question_options WHERE question_id IN :ids"
                ).bindparams(bindparam("ids", expanding=True)), {"ids": easy_questions}).all()] if "question_options" in tables else []
                if "attempts" in tables:
                    connection.execute(text("DELETE FROM attempts WHERE question_id IN :ids").bindparams(
                        bindparam("ids", expanding=True)), {"ids": easy_questions})
                if "question_options" in tables:
                    connection.execute(text("DELETE FROM question_options WHERE question_id IN :ids").bindparams(
                        bindparam("ids", expanding=True)), {"ids": easy_questions})
                connection.execute(text("DELETE FROM questions WHERE id IN :ids").bindparams(
                    bindparam("ids", expanding=True)), {"ids": easy_questions})
            qtable = _q(engine, MANIFEST_TABLE)
            connection.execute(text(
                f"INSERT INTO {qtable} (participant_id, display_code, counts_json) "
                "VALUES (:key, NULL, :counts) ON CONFLICT (participant_id) DO UPDATE SET counts_json=:counts"
            ), {"key": MANIFEST_COUNTS_KEY, "counts": json.dumps(dict(counts), sort_keys=True)})
        return dict(counts), identifiers, codes


def _delete_identity_rows(path: Path, identifiers: set[str]) -> int:
    if not path.is_file():
        raise FileNotFoundError("identity mapping database is missing")
    deleted = 0
    with sqlite3.connect(path) as mapping:
        mapping.execute("PRAGMA secure_delete=ON")
        exists = mapping.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='identity_mappings'"
        ).fetchone()
        if not exists:
            raise RuntimeError("identity mapping schema is missing")
        for participant_id in identifiers:
            deleted += max(mapping.execute(
                "DELETE FROM identity_mappings WHERE participant_id = ?", (participant_id,)
            ).rowcount, 0)
        mapping.commit()
        mapping.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return deleted


def _persist_manifest_counts(engine: Engine, additions: dict[str, int]) -> dict[str, int]:
    with engine.begin() as connection:
        identifiers, _codes, counts = _all_manifest(connection, engine)
        for key, value in additions.items():
            counts.setdefault(key, int(value))
        connection.execute(text(
            f"UPDATE {_q(engine, MANIFEST_TABLE)} SET counts_json=:counts WHERE participant_id=:key"
        ), {"key": MANIFEST_COUNTS_KEY, "counts": json.dumps(counts, sort_keys=True)})
        return counts


def _purge_csv_exports(csv_dir: Path, identifiers: set[str], codes: set[str]) -> tuple[int, int]:
    removed_rows = 0
    removed_files = 0
    if not csv_dir.is_dir():
        return removed_rows, removed_files
    for path in csv_dir.glob("*.csv"):
        if any(path.name == f"{code}_logs.csv" or path.name == f"{code}_logs_excel.csv" for code in codes):
            path.unlink()
            removed_files += 1
            continue
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as source:
                reader = csv.DictReader(source)
                fieldnames = reader.fieldnames
                if not fieldnames:
                    continue
                kept = []
                file_removed_rows = 0
                for row in reader:
                    if _row_contains_identifier(row, identifiers, codes):
                        removed_rows += 1
                        file_removed_rows += 1
                    else:
                        kept.append(row)
            if not file_removed_rows:
                continue
            fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
            os.close(fd)
            temporary = Path(temporary_name)
            try:
                with temporary.open("w", encoding="utf-8-sig", newline="") as destination:
                    writer = csv.DictWriter(destination, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(kept)
                os.chmod(temporary, path.stat().st_mode & 0o777)
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        except (OSError, UnicodeError, csv.Error):
            raise RuntimeError("could not safely filter a local CSV export") from None
    return removed_rows, removed_files


def _finalize(engine: Engine, counts: dict[str, int]) -> None:
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        identifiers, codes, stored_counts = _all_manifest(connection, engine)
        if identifiers:
            if "participants" in tables:
                remaining = connection.execute(text(
                    "SELECT count(*) FROM participants WHERE id IN :ids"
                ).bindparams(bindparam("ids", expanding=True)), {"ids": sorted(identifiers)}).scalar_one()
                if remaining:
                    raise RuntimeError("participant purge is incomplete")
            for table in _tables_with_column(connection, tables, "participant_id"):
                if table in {"participants", MANIFEST_TABLE, AUDIT_TABLE}:
                    continue
                remaining = connection.execute(text(
                    f"SELECT count(*) FROM {_q(engine, table)} WHERE participant_id IN :ids"
                ).bindparams(bindparam("ids", expanding=True)), {"ids": sorted(identifiers)}).scalar_one()
                if remaining:
                    raise RuntimeError("participant-linked purge is incomplete")
            if _matching_json_row_ids(connection, engine, "ai_call_logs", identifiers | set(codes.values())):
                raise RuntimeError("AI log purge is incomplete")
            if _matching_json_row_ids(connection, engine, "audit_events", identifiers | set(codes.values())):
                raise RuntimeError("audit purge is incomplete")
        if _easy_question_ids(connection, tables):
            raise RuntimeError("question asset purge is incomplete")
        final_counts = stored_counts or counts
        if AUDIT_TABLE not in tables:
            connection.execute(text(
                f"CREATE TABLE {_q(engine, AUDIT_TABLE)} (id VARCHAR(36) PRIMARY KEY, "
                "completed_at TIMESTAMP NOT NULL, participant_count INTEGER NOT NULL, counts_json TEXT NOT NULL)"
            ))
        if MANIFEST_TABLE in tables:
            connection.execute(text(f"DROP TABLE {_q(engine, MANIFEST_TABLE)}"))
        for table in ("participants", "runtime_settings"):
            if table not in tables:
                continue
            columns = {col["name"] for col in inspect(connection).get_columns(table)}
            if "question_set_mode" in columns:
                connection.execute(text(f"ALTER TABLE {_q(engine, table)} DROP COLUMN question_set_mode"))
        connection.execute(text(
            f"INSERT INTO {_q(engine, AUDIT_TABLE)} (id, completed_at, participant_count, counts_json) "
            "VALUES (:id, :completed_at, :participant_count, :counts)"
        ), {
            "id": f"purge-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}",
            "completed_at": datetime.now(UTC).replace(tzinfo=None),
            "participant_count": int(final_counts.get("participants", 0)),
            "counts": json.dumps(final_counts, sort_keys=True),
        })


def execute_purge(engine: Engine, identity_path: Path, csv_dir: Path | None = None) -> dict[str, int]:
    counts, identifiers, _codes = _delete_easy_records(engine)
    # Codes are recoverable from the temporary manifest after a failed attempt.
    with engine.connect() as connection:
        _ids, persisted_codes, stored_counts = _all_manifest(connection, engine)
    if persisted_codes:
        _codes = persisted_codes
    elif _codes:
        pass
    else:
        _codes = {}
    external_counts = inspect_counts(engine, identity_path, csv_dir)
    additions = {key: external_counts.get(key, 0) for key in ("identity_mappings", "csv_rows", "csv_files")}
    counts = _persist_manifest_counts(engine, additions)
    _delete_identity_rows(identity_path, identifiers)
    if csv_dir is not None:
        _purge_csv_exports(csv_dir, identifiers, set(_codes.values()))
    final_counts = counts or stored_counts
    _finalize(engine, final_counts)
    return final_counts


def _print_counts(counts: dict[str, int], *, title: str) -> None:
    print(title)
    if not counts:
        print("  no matching records")
        return
    for name, count in counts.items():
        print(f"  {name}: {count}")


def _local_paths() -> tuple[Path, Path, Path, Path]:
    backend = Path(__file__).resolve().parents[1]
    root = backend / ".local"
    return root / "test.db", root / "test-identities.sqlite3", root / "exports", root


def _local_paths_are_confined(database_path: Path, mapping_path: Path,
                              csv_dir: Path, root: Path) -> bool:
    backend = root.parent.resolve()
    expected_root = backend / ".local"
    if root.is_symlink() or root.resolve(strict=False) != expected_root:
        return False
    for path in (database_path, mapping_path, csv_dir):
        if path.is_symlink() or path.parent.resolve(strict=False) != expected_root:
            return False
    if csv_dir.exists():
        if any(path.is_symlink() for path in csv_dir.glob("*.csv")):
            return False
        if any(path.resolve(strict=False).parent != csv_dir.resolve(strict=False)
               for path in csv_dir.glob("*.csv")):
            return False
    return True


def _run_local(args: argparse.Namespace) -> int:
    database_path, mapping_path, csv_dir, root = _local_paths()
    if not _local_paths_are_confined(database_path, mapping_path, csv_dir, root):
        print("local artifact path guard failed", file=sys.stderr)
        return 2
    if not database_path.is_file() or not mapping_path.is_file():
        print("local artifact databases are missing; no data was changed", file=sys.stderr)
        return 2
    engine = create_engine(f"sqlite:///{database_path}", future=True)
    try:
        if not args.execute:
            _print_counts(inspect_counts(engine, mapping_path, csv_dir), title="Local-only dry run")
            return 0
        if not args.confirm_local_artifacts:
            print("execution requires --confirm-local-artifacts", file=sys.stderr)
            return 2
        counts = execute_purge(engine, mapping_path, csv_dir)
        _print_counts(counts, title="Local artifact purge completed (anonymous counts)")
        return 0
    except Exception:
        print("local artifact purge failed; retry is safe and no identifiers were emitted", file=sys.stderr)
        return 1
    finally:
        engine.dispose()


def _run_research(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL")
    app_env = os.environ.get("APP_ENV", "").strip().lower()
    if not database_url or app_env != "research":
        print("research execution requires explicit DATABASE_URL and APP_ENV=research", file=sys.stderr)
        return 2
    url = make_url(database_url)
    if not url.drivername.startswith("postgresql") or not url.database:
        print("research purge refuses SQLite and non-PostgreSQL databases", file=sys.stderr)
        return 2
    identity_path_value = os.environ.get("IDENTITY_MAPPING_PATH")
    if not identity_path_value:
        print("execution requires explicit IDENTITY_MAPPING_PATH", file=sys.stderr)
        return 2
    identity_path = Path(identity_path_value).expanduser().resolve()
    if not identity_path.is_file():
        print("identity mapping database is missing; no research rows were changed", file=sys.stderr)
        return 2
    engine = create_engine(url, future=True, pool_pre_ping=True)
    try:
        if not args.execute:
            _print_counts(inspect_counts(engine, identity_path), title="Research-only dry run")
            return 0
        if args.confirm_database != url.database or not args.app_stopped:
            print("execution requires the exact database-name confirmation and --app-stopped", file=sys.stderr)
            return 2
        counts = execute_purge(engine, identity_path)
        _print_counts(counts, title="Research purge completed (anonymous counts)")
        return 0
    except Exception:
        print("research purge failed; retry from the durable manifest, no identifiers were emitted", file=sys.stderr)
        return 1
    finally:
        engine.dispose()


def _is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    if host.rstrip(".").lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _run_development_debug(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL")
    app_env = os.environ.get("APP_ENV", "").strip().lower()
    if not database_url or app_env != "development":
        print("development debug purge requires DATABASE_URL and APP_ENV=development", file=sys.stderr)
        return 2

    try:
        url = make_url(database_url)
    except Exception:
        print("development debug purge requires a valid local PostgreSQL URL", file=sys.stderr)
        return 2
    if (not url.drivername.lower().startswith("postgresql") or not url.database
            or not _is_loopback_host(url.host)):
        print("development debug purge only permits PostgreSQL on a loopback host", file=sys.stderr)
        return 2

    identity_path_value = os.environ.get("IDENTITY_MAPPING_PATH")
    if not identity_path_value:
        print("development debug purge requires IDENTITY_MAPPING_PATH", file=sys.stderr)
        return 2
    identity_path = Path(identity_path_value).expanduser().resolve()
    if not identity_path.is_file():
        print("identity mapping database is missing; no rows were changed", file=sys.stderr)
        return 2

    if args.execute and (args.confirm_database != url.database or not args.app_stopped):
        print("execution requires the exact database-name confirmation and --app-stopped", file=sys.stderr)
        return 2

    engine = create_engine(url, future=True, pool_pre_ping=True)
    try:
        if not args.execute:
            _print_counts(inspect_counts(engine, identity_path),
                          title="Development-only dry run (anonymous counts)")
            return 0
        counts = execute_purge(engine, identity_path)
        _print_counts(counts, title="Development debug purge completed (anonymous counts)")
        return 0
    except Exception:
        print("development debug purge failed; no identifiers were emitted", file=sys.stderr)
        return 1
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-artifacts", action="store_true", help="target only backend/.local/test.db and its local companions")
    parser.add_argument("--development-debug-data", action="store_true",
                        help="explicitly target retired easy-mode debug records in a local development PostgreSQL database")
    parser.add_argument("--execute", action="store_true", help="execute deletion; otherwise counts-only dry run")
    parser.add_argument("--confirm-local-artifacts", action="store_true")
    parser.add_argument("--confirm-database", help="exact PostgreSQL database name for execution")
    parser.add_argument("--app-stopped", action="store_true", help="confirm all app workers using the target DB are stopped")
    args = parser.parse_args(argv)
    if args.local_artifacts and args.development_debug_data:
        parser.error("--local-artifacts and --development-debug-data cannot be combined")
    if args.local_artifacts:
        if args.confirm_database or args.app_stopped:
            parser.error("database confirmations cannot be combined with --local-artifacts")
        return _run_local(args)
    if args.confirm_local_artifacts:
        parser.error("--confirm-local-artifacts requires --local-artifacts")
    if args.development_debug_data:
        return _run_development_debug(args)
    return _run_research(args)


if __name__ == "__main__":
    raise SystemExit(main())
