from __future__ import annotations

import csv
import json
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.models import (
    AICallLog,
    Attempt,
    AuditEvent,
    Base,
    EvaluationSummary,
    Participant,
    ParticipantSurvey,
    Question,
    QuestionDisplayOrder,
    QuestionOption,
    Term,
    TermAssignment,
    TutorSession,
    TutorTurn,
)
from app.db import session as database
from scripts import purge_easy_mode_data
from scripts.purge_easy_mode_data import (
    _contains_any,
    _contains_identifier_token,
    _local_paths_are_confined,
    execute_purge,
    inspect_counts,
    main,
)


def _participant(db: Session, display_code: str, mode: str) -> Participant:
    participant = Participant(display_code=display_code, group_condition="control", current_step="learning")
    db.add(participant)
    db.flush()
    db.execute(text("UPDATE participants SET question_set_mode=:mode WHERE id=:id"),
               {"mode": mode, "id": participant.id})
    return participant


def _mapping(path, rows):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE identity_mappings (participant_id TEXT PRIMARY KEY, display_code TEXT NOT NULL, student_number TEXT NOT NULL, created_at TEXT NOT NULL, registration_key TEXT NOT NULL UNIQUE)")
        db.executemany("INSERT INTO identity_mappings VALUES (?, ?, ?, ?, ?)", rows)


def _fixture(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'research-test.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE participants ADD COLUMN question_set_mode VARCHAR(32)"))
        connection.execute(text("ALTER TABLE runtime_settings ADD COLUMN question_set_mode VARCHAR(32)"))
    mapping_path = tmp_path / "identities.sqlite3"
    exports = tmp_path / "exports"
    exports.mkdir()
    with Session(engine) as db:
        term = Term(slug="llm_knowledge", label="LLM", display_order=1)
        db.add(term)
        db.flush()
        easy = _participant(db, "SYNTH-EASY", "easy")
        standard = _participant(db, "SYNTH-STD", "standard")
        easy_q = Question(term_id=term.id, phase="pretest", question_type="multi_select", body="easy question", construct_key="llm_knowledge_scenario-actions-easy-v1", variant_key="pretest_v1")
        standard_q = Question(term_id=term.id, phase="pretest", question_type="single", body="standard question", construct_key="llm_knowledge_split-actions-v5", variant_key="pretest_v1")
        db.add_all([easy_q, standard_q])
        db.flush()
        easy_option = QuestionOption(question_id=easy_q.id, option_label="A", body="easy option", is_correct=False)
        standard_option = QuestionOption(question_id=standard_q.id, option_label="A", body="standard option", is_correct=True)
        db.add_all([easy_option, standard_option])
        db.flush()
        db.add_all([
            Attempt(participant_id=easy.id, term_id=term.id, question_id=easy_q.id, phase="pretest", legacy_selected_option_id=easy_option.id),
            Attempt(participant_id=easy.id, term_id=term.id, question_id=easy_q.id, phase="pretest"),
            Attempt(participant_id=standard.id, term_id=term.id, question_id=standard_q.id, phase="pretest", legacy_selected_option_id=standard_option.id),
            ParticipantSurvey(participant_id=easy.id, phase="presurvey"),
            ParticipantSurvey(participant_id=standard.id, phase="presurvey"),
            TermAssignment(participant_id=easy.id, term_id=term.id, group_condition="control"),
            TermAssignment(participant_id=standard.id, term_id=term.id, group_condition="control"),
            QuestionDisplayOrder(participant_id=easy.id, question_id=easy_q.id, option_order=[easy_option.id], random_seed="easy"),
            QuestionDisplayOrder(participant_id=standard.id, question_id=standard_q.id, option_order=[standard_option.id], random_seed="standard"),
            EvaluationSummary(participant_id=easy.id, group_condition="control"),
            EvaluationSummary(participant_id=standard.id, group_condition="control"),
            AICallLog(provider="mock", purpose="material", request_payload={"participant_id": easy.id}, response_payload={"ok": True}, status="completed"),
            AICallLog(provider="mock", purpose="material", request_payload={"participant_id": standard.id}, response_payload={"ok": True}, status="completed"),
            AICallLog(provider="mock", purpose="material", request_payload={"participant_id": f"{easy.display_code}-OTHER"}, response_payload={"ok": True}, status="completed"),
            AuditEvent(actor="test", action="event", entity_type="participant", entity_id=easy.id, before_json={"display_code": easy.display_code}),
            AuditEvent(actor="test", action="event", entity_type="participant", entity_id=standard.id, before_json={"display_code": standard.display_code}),
        ])
        session = TutorSession(participant_id=easy.id, term_id=term.id, session_index=1, group_condition="control")
        db.add(session)
        db.flush()
        db.add(TutorTurn(tutor_session_id=session.id, turn_index=1, teaching_strategy="baseline", tutor_message="material"))
        db.flush()
        easy_id, standard_id = easy.id, standard.id
        _mapping(mapping_path, [
            (easy.id, easy.display_code, "SYNTHETIC-EASY-STUDENT", "2026-01-01", "easy-registration"),
            (standard.id, standard.display_code, "SYNTHETIC-STD-STUDENT", "2026-01-01", "standard-registration"),
        ])
        with (exports / "overview.csv").open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=["participant_id", "display_code", "score"])
            writer.writeheader()
            writer.writerow({"participant_id": easy.id, "display_code": easy.display_code, "score": "0"})
            writer.writerow({"participant_id": standard.id, "display_code": standard.display_code, "score": "1"})
        (exports / f"{easy.display_code}_logs.csv").write_text("header\nrecord\n", encoding="utf-8")
        (exports / f"{standard.display_code}_logs.csv").write_text("header\nrecord\n", encoding="utf-8")
        db.commit()
    return engine, mapping_path, exports, easy_id, standard_id


def test_purge_removes_only_retired_cohort_and_keeps_anonymous_counts(tmp_path):
    engine, mapping_path, exports, easy_id, standard_id = _fixture(tmp_path)
    counts = inspect_counts(engine, mapping_path, exports)
    assert counts["participants"] == 1
    assert counts["identity_mappings"] == 1
    assert counts["csv_rows"] == 1
    assert counts["csv_files"] == 1

    result = execute_purge(engine, mapping_path, exports)

    assert result["participants"] == 1
    with engine.connect() as db:
        assert db.execute(text("SELECT count(*) FROM participants")).scalar_one() == 1
        assert db.execute(text("SELECT id FROM participants")).scalar_one() == standard_id
        assert db.execute(text("SELECT count(*) FROM attempts")).scalar_one() == 1
        assert db.execute(text("SELECT count(*) FROM participant_surveys")).scalar_one() == 1
        assert db.execute(text("SELECT count(*) FROM tutor_turns")).scalar_one() == 0
        assert db.execute(text("SELECT count(*) FROM questions WHERE construct_key LIKE '%easy%'")).scalar_one() == 0
        assert db.execute(text("SELECT count(*) FROM questions")).scalar_one() == 1
        assert db.execute(text("SELECT count(*) FROM ai_call_logs")).scalar_one() == 2
        assert db.execute(text("SELECT count(*) FROM audit_events")).scalar_one() == 1
        audit = db.execute(text(f"SELECT participant_count, counts_json FROM easy_mode_purge_audits")).one()
        assert audit[0] == 1
        assert easy_id not in audit[1] and standard_id not in audit[1]
        assert "SYNTH-EASY" not in audit[1]
    with sqlite3.connect(mapping_path) as mapping:
        assert mapping.execute("SELECT participant_id FROM identity_mappings").fetchone()[0] == standard_id
    overview = list(csv.DictReader((exports / "overview.csv").open(encoding="utf-8-sig", newline="")))
    assert len(overview) == 1 and overview[0]["participant_id"] == standard_id
    assert not (exports / "SYNTH-EASY_logs.csv").exists()
    assert (exports / "SYNTH-STD_logs.csv").exists()
    assert "question_set_mode" not in {column["name"] for column in inspect(engine).get_columns("participants")}
    assert "question_set_mode" not in {column["name"] for column in inspect(engine).get_columns("runtime_settings")}
    engine.dispose()


def test_purge_retries_from_manifest_after_mapping_failure(tmp_path):
    engine, mapping_path, _exports, easy_id, standard_id = _fixture(tmp_path)
    mapping_path.write_text("not a sqlite database", encoding="utf-8")
    with pytest.raises(Exception):
        execute_purge(engine, mapping_path)
    with engine.connect() as db:
        assert db.execute(text("SELECT count(*) FROM participants")).scalar_one() == 1
        manifest = db.execute(text("SELECT participant_id FROM _easy_mode_purge_manifest WHERE participant_id != '__aggregate_counts__'")).scalar_one()
        assert manifest == easy_id
    mapping_path.unlink()
    _mapping(mapping_path, [
        (easy_id, "SYNTH-EASY", "SYNTHETIC-EASY-STUDENT", "2026-01-01", "easy-registration"),
        (standard_id, "SYNTH-STD", "SYNTHETIC-STD-STUDENT", "2026-01-01", "standard-registration"),
    ])
    execute_purge(engine, mapping_path)
    with engine.connect() as db:
        assert "_easy_mode_purge_manifest" not in inspect(db).get_table_names()
        assert db.execute(text("SELECT count(*) FROM easy_mode_purge_audits")).scalar_one() == 1
    engine.dispose()


def test_research_cli_requires_explicit_non_sqlite_environment(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    assert main([]) == 2
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./.local/test.db")
    monkeypatch.setenv("APP_ENV", "research")
    assert main(["--execute", "--confirm-database", "test", "--app-stopped"]) == 2


def test_development_debug_dry_run_is_read_only(tmp_path, monkeypatch, capsys):
    engine, mapping_path, exports, easy_id, standard_id = _fixture(tmp_path)
    mapping_before = sqlite3.connect(mapping_path).execute(
        "SELECT participant_id, display_code FROM identity_mappings ORDER BY participant_id"
    ).fetchall()
    csv_before = {path.name: path.read_bytes() for path in exports.glob("*.csv")}
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://app:app@127.0.0.1:5432/ai_tutor")
    monkeypatch.setenv("IDENTITY_MAPPING_PATH", str(mapping_path))
    monkeypatch.setattr(purge_easy_mode_data, "create_engine", lambda *args, **kwargs: engine)

    assert main(["--development-debug-data"]) == 0
    output = capsys.readouterr().out
    assert "participants: 1" in output
    assert easy_id not in output and standard_id not in output
    with engine.connect() as db:
        assert db.execute(text("SELECT count(*) FROM participants")).scalar_one() == 2
        assert "question_set_mode" in {
            column["name"] for column in inspect(engine).get_columns("participants")
        }
        assert "_easy_mode_purge_manifest" not in inspect(engine).get_table_names()
        assert "easy_mode_purge_audits" not in inspect(engine).get_table_names()
    with sqlite3.connect(mapping_path) as mapping:
        assert mapping.execute(
            "SELECT participant_id, display_code FROM identity_mappings ORDER BY participant_id"
        ).fetchall() == mapping_before
    assert {path.name: path.read_bytes() for path in exports.glob("*.csv")} == csv_before
    engine.dispose()


def test_development_debug_execute_removes_only_easy_records_and_keeps_exports(
    tmp_path, monkeypatch,
):
    engine, mapping_path, exports, easy_id, standard_id = _fixture(tmp_path)
    csv_before = {path.name: path.read_bytes() for path in exports.glob("*.csv")}
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/ai_tutor")
    monkeypatch.setenv("IDENTITY_MAPPING_PATH", str(mapping_path))
    monkeypatch.setattr(purge_easy_mode_data, "create_engine", lambda *args, **kwargs: engine)

    assert main([
        "--development-debug-data", "--execute", "--confirm-database", "ai_tutor",
        "--app-stopped",
    ]) == 0
    with engine.connect() as db:
        assert db.execute(text("SELECT id FROM participants")).scalar_one() == standard_id
        assert db.execute(text("SELECT count(*) FROM attempts")).scalar_one() == 1
        assert db.execute(text("SELECT count(*) FROM questions WHERE construct_key LIKE '%easy%'")).scalar_one() == 0
        assert db.execute(text("SELECT count(*) FROM easy_mode_purge_audits")).scalar_one() == 1
        assert "question_set_mode" not in {
            column["name"] for column in inspect(engine).get_columns("participants")
        }
        assert "question_set_mode" not in {
            column["name"] for column in inspect(engine).get_columns("runtime_settings")
        }
        audit = db.execute(text("SELECT counts_json FROM easy_mode_purge_audits")).scalar_one()
        assert easy_id not in audit and standard_id not in audit
    with sqlite3.connect(mapping_path) as mapping:
        assert mapping.execute("SELECT participant_id FROM identity_mappings").fetchone()[0] == standard_id
    assert {path.name: path.read_bytes() for path in exports.glob("*.csv")} == csv_before
    engine.dispose()


@pytest.mark.parametrize(
    ("app_env", "database_url", "argv"),
    [
        ("research", "postgresql://app:app@127.0.0.1:5432/ai_tutor",
         ["--development-debug-data"]),
        ("development", "sqlite:///tmp/test.db",
         ["--development-debug-data"]),
        ("development", "postgresql://app:app@example.com:5432/ai_tutor",
         ["--development-debug-data"]),
        ("development", "postgresql://app:app@127.0.0.1:5432/ai_tutor",
         ["--development-debug-data", "--execute", "--app-stopped"]),
        ("development", "postgresql://app:app@127.0.0.1:5432/ai_tutor",
         ["--development-debug-data", "--execute", "--confirm-database", "wrong", "--app-stopped"]),
        ("development", "postgresql://app:app@127.0.0.1:5432/ai_tutor",
         ["--development-debug-data", "--execute", "--confirm-database", "ai_tutor"]),
    ],
)
def test_development_debug_execution_guards_reject_before_connecting(
    monkeypatch, tmp_path, app_env, database_url, argv,
):
    mapping_path = tmp_path / "identities.sqlite3"
    mapping_path.touch()
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("IDENTITY_MAPPING_PATH", str(mapping_path))
    monkeypatch.setattr(
        purge_easy_mode_data, "create_engine",
        lambda *args, **kwargs: pytest.fail("guard must reject before connecting"),
    )
    assert main(argv) == 2


def test_development_mode_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", "postgresql://app:app@127.0.0.1:5432/ai_tutor")
    assert main([]) == 2


def test_development_debug_requires_existing_identity_mapping(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", "postgresql://app:app@127.0.0.1:5432/ai_tutor")
    monkeypatch.setenv("IDENTITY_MAPPING_PATH", str(tmp_path / "missing.sqlite3"))
    monkeypatch.setattr(
        purge_easy_mode_data, "create_engine",
        lambda *args, **kwargs: pytest.fail("missing mapping must reject before connecting"),
    )
    assert main(["--development-debug-data"]) == 2


def test_application_start_is_blocked_until_legacy_easy_participants_are_purged(tmp_path, monkeypatch):
    engine, mapping_path, exports, _easy_id, _standard_id = _fixture(tmp_path)
    monkeypatch.setattr(database, "engine", engine)

    with pytest.raises(RuntimeError, match="guarded purge utility"):
        database.init_db()

    execute_purge(engine, mapping_path, exports)
    database.init_db()
    engine.dispose()


def test_identifier_matching_does_not_remove_substrings_or_neighboring_codes():
    identifiers = {"SYNTH-EASY", "participant-123"}
    assert not _contains_any({"participant_id": "SYNTH-EASY-OTHER"}, identifiers)
    assert _contains_any({"participant_id": "SYNTH-EASY"}, identifiers)
    assert _contains_identifier_token("event for SYNTH-EASY completed", identifiers)
    assert not _contains_identifier_token("event for SYNTH-EASY-OTHER completed", identifiers)


def test_local_artifact_path_guard_rejects_symlinks(tmp_path):
    root = tmp_path / "backend" / ".local"
    exports = root / "exports"
    exports.mkdir(parents=True)
    database = root / "test.db"
    mapping = root / "test-identities.sqlite3"
    database.touch()
    mapping.touch()
    assert _local_paths_are_confined(database, mapping, exports, root)

    external = tmp_path / "external.csv"
    external.write_text("id\n", encoding="utf-8")
    (exports / "linked.csv").symlink_to(external)
    assert not _local_paths_are_confined(database, mapping, exports, root)
