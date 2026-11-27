import json
import re
import sqlite3
import time
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from admin_client import AuthenticatedTestClient as TestClient
from sqlalchemy import String, text
from sqlalchemy.dialects.postgresql import dialect as postgresql_dialect

from app.main import app
from app.db import session as db_session_module
from app.db.session import SessionLocal, engine
from app.core.config import get_settings
from app.models import AuditEvent, IdempotencyRecord, Participant, ParticipantSession, now
from app.services.idempotency import request_fingerprint
from app.services import identity_mapping
from app.services.participant_auth import _cookie_name, _secret, _token_hash, _token_signature
from app.core.question_sets import LEARNING_CONTENT_VERSION

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_mappings(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "identity_mapping_path", str(tmp_path / "identities.sqlite3"))


def register(research_code=None, key=None):
    if research_code is None:
        research_code = str(uuid4().int)
    return client.post(
        "/api/registrations",
        json={"assignment_code": "A", "consent_checked": True, "research_code": research_code},
        headers={"Idempotency-Key": key or str(uuid4())},
    )


@pytest.mark.parametrize("research_code", ["", "   ", "1" * 65, "123\n", "123\t", "1\x002", "１２３"])
def test_invalid_research_codes_are_not_echoed_or_persisted(research_code):
    response = register(research_code)
    assert response.status_code == 400
    assert not research_code or research_code not in response.text
    assert not Path(get_settings().identity_mapping_path).exists()


def test_registration_discards_research_code_and_uses_generated_id_and_display_code():
    key = str(uuid4())
    research_code = "001202611120001"
    response = register(research_code, key)
    assert response.status_code == 200, response.text
    participant_id = response.json()["participant_id"]
    assert participant_id != research_code
    assert re.fullmatch(r"[0-9a-f-]{36}", participant_id)
    assert response.json()["display_code"].startswith("P")
    assert re.fullmatch(r"P\d{3,}", response.json()["display_code"])
    assert "participant_code" not in response.json()
    assert "set-cookie" in response.headers
    assert not Path(get_settings().identity_mapping_path).exists()

    with SessionLocal() as db:
        participant = db.get(Participant, participant_id)
        assert participant.id == participant_id
        assert participant.display_code == response.json()["display_code"]
        assert participant.test_content_mode == "four_topic_fundamentals"
        assert participant.consent_document_version == "consent-2026-11-27-generated-participant-id-v1"
        record = db.query(IdempotencyRecord).filter_by(idempotency_key=key).one()
        expected_hash = request_fingerprint({
            "assignment_code": "A",
            "consent_checked": True,
            "consent_document_version": "consent-2026-11-27-generated-participant-id-v1",
        })
        assert record.request_hash == expected_hash
        assert record.response_json["participant_id"] == participant_id
        assert research_code not in json.dumps(record.response_json)
        assert db.query(ParticipantSession).filter_by(participant_id=participant_id).count() == 1
        assert participant_code_not_persisted(db, research_code)

    for path in (f"/api/admin/participants/{participant_id}/logs.csv", f"/api/admin/participants/{participant_id}/logs.xlsx"):
        exported = client.get(path)
        assert exported.status_code == 200
        assert response.json()["display_code"] in exported.headers["content-disposition"]
        if path.endswith(".csv"):
            assert b"participant_code" in exported.content.splitlines()[0]
            assert participant_id.encode() in exported.content
            assert research_code.encode() not in exported.content

    anonymous = TestClient(app)
    assert anonymous.get(f"/api/participants/{participant_id}/presurvey").status_code == 401
    assert client.get(f"/api/participants/{participant_id}/presurvey").status_code == 200

    replay = register(research_code, key)
    assert replay.status_code == 200
    assert replay.json() == response.json()
    replay_with_different_code = register("987654321", key)
    assert replay_with_different_code.status_code == 200
    assert replay_with_different_code.json() == response.json()
    with SessionLocal() as db:
        assert db.query(Participant).filter_by(id=participant_id).count() == 1
        assert db.query(ParticipantSession).filter_by(participant_id=participant_id).count() == 3

    duplicate = register(research_code)
    assert duplicate.status_code == 200
    assert duplicate.json()["participant_id"] != participant_id


def participant_code_not_persisted(db, research_code):
    for row in db.query(IdempotencyRecord).all():
        assert research_code not in json.dumps(row.response_json)
    for row in db.query(AuditEvent).all():
        assert research_code not in json.dumps([row.before_json, row.after_json])
    return True


def test_v64_participant_resumes_only_with_its_existing_valid_session():
    participant_code = "001202611120001"
    protocol_id = "experiment-plan-2026-11-23-participant-code-primary-identifier-presurvey-weekly-frequency-understanding-anchor-v1"
    with SessionLocal() as db:
        participant = Participant(
            id=participant_code,
            display_code=participant_code,
            group_condition="proposed",
            consent_checked=True,
            current_step="presurvey",
            experiment_spec_version=64,
            protocol_id=protocol_id,
            learning_content_version=LEARNING_CONTENT_VERSION,
        )
        db.add(participant)
        secret = _secret()
        expires_unix = int(time.time()) + 3600
        payload = f"v1.existing-v64-session.{expires_unix}"
        token = f"{payload}.{_token_signature(payload, secret)}"
        db.add(ParticipantSession(
            token_hash=_token_hash(token),
            participant_id=participant_code,
            expires_at=now() + timedelta(hours=1),
        ))
        db.commit()

    cookie_name = _cookie_name(participant_code, _secret())
    anonymous = TestClient(app)
    assert anonymous.get(f"/api/participants/{participant_code}/current-step").status_code == 401
    resumed = TestClient(app)
    resumed.cookies.set(cookie_name, token)
    response = resumed.get(f"/api/participants/{participant_code}/current-step")
    assert response.status_code == 200, response.text
    assert response.json()["can_resume"] is True
    assert response.json()["step"] == "presurvey"
    logs = client.get(f"/api/admin/participants/{participant_code}/logs")
    assert logs.status_code == 200
    assert logs.json()["participant"]["participant_code"] == participant_code
    assert logs.json()["participant"]["participant_id"] == participant_code
    exported = client.get(f"/api/admin/participants/{participant_code}/logs.csv")
    assert exported.status_code == 200
    assert participant_code.encode() in exported.content
    assert b"participant_code" in exported.content.splitlines()[0]
    with SessionLocal() as db:
        saved = db.get(Participant, participant_code)
        assert saved.id == participant_code
        assert saved.experiment_spec_version == 64
        assert saved.protocol_id == protocol_id


def test_existing_mapping_file_is_unchanged_by_registration(tmp_path, monkeypatch):
    path = tmp_path / "existing-identities.sqlite3"
    monkeypatch.setattr(get_settings(), "identity_mapping_path", str(path))
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE identity_mappings (participant_id TEXT PRIMARY KEY, display_code TEXT, student_number TEXT, created_at TEXT, registration_key TEXT)")
        db.execute("CREATE TABLE research_code_mappings (participant_id TEXT PRIMARY KEY, research_code TEXT, display_code TEXT, created_at TEXT, registration_key TEXT)")
        db.execute("INSERT INTO identity_mappings VALUES ('old-pid', 'P-OLD', 'S-001', '2026-01-01', 'old-key')")
        db.execute("INSERT INTO research_code_mappings VALUES ('old-pid', '000123', 'P-OLD', '2026-01-01', 'old-key')")
    before = path.read_bytes()

    response = register("003202611120003")
    assert response.status_code == 200, response.text
    assert path.read_bytes() == before


def test_mapping_management_apis_are_removed():
    routes = [
        ("GET", "/api/admin/identity-mappings"),
        ("GET", "/api/admin/identity-mappings.csv"),
        ("DELETE", "/api/admin/identity-mappings"),
        ("DELETE", "/api/admin/identity-mappings/p-1"),
        ("GET", "/api/admin/research-code-mappings"),
        ("GET", "/api/admin/research-code-mappings.csv"),
        ("DELETE", "/api/admin/research-code-mappings"),
        ("DELETE", "/api/admin/research-code-mappings/p-1"),
    ]
    for method, path in routes:
        response = client.request(method, path)
        assert response.status_code == 404, (method, path, response.text)


def test_new_registrations_are_fixed_to_four_topic_mode():
    assert client.get("/api/admin/test-content-mode").json() == {
        "mode": "four_topic_fundamentals",
        "label": "4用語版",
        "applies_to": "new_participants_only",
    }
    assert client.put("/api/admin/test-content-mode", json={"mode": "application"}).status_code == 409
    assert client.put("/api/admin/test-content-mode", json={"mode": "basic_understanding"}).status_code == 409
    assert client.put("/api/admin/test-content-mode", json={"mode": "four_topic_fundamentals"}).status_code == 200
    created = register()
    assert created.status_code == 200, created.text
    with SessionLocal() as db:
        participant = db.get(Participant, created.json()["participant_id"])
        assert participant.test_content_mode == "four_topic_fundamentals"


def test_registration_validation_does_not_echo_unexpected_identifier_fields():
    response = client.post("/api/registrations", json={
        "assignment_code": "A", "consent_checked": True, "research_code": "012345",
        "student_number": {"secret": "DO-NOT-ECHO"},
    })
    assert response.status_code == 422
    assert "DO-NOT-ECHO" not in response.text
    assert client.post("/api/participants", json={"assignment_code": "A", "consent_checked": True}).status_code == 422


def _create_mapping_rows(participant_id: str, other_id: str) -> None:
    path = get_settings().identity_mapping_path
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS identity_mappings (participant_id TEXT PRIMARY KEY, display_code TEXT NOT NULL, student_number TEXT NOT NULL, created_at TEXT NOT NULL, registration_key TEXT NOT NULL UNIQUE)")
        db.execute("CREATE TABLE IF NOT EXISTS research_code_mappings (participant_id TEXT PRIMARY KEY, research_code TEXT NOT NULL UNIQUE, display_code TEXT NOT NULL, created_at TEXT NOT NULL, registration_key TEXT NOT NULL UNIQUE)")
        for pid, code in ((participant_id, "TARGET"), (other_id, "KEEP")):
            db.execute("INSERT INTO identity_mappings VALUES (?, ?, ?, ?, ?)", (pid, f"P-{code}", f"S-{code}", "2026-11-12", f"student-{code}"))
            db.execute("INSERT INTO research_code_mappings VALUES (?, ?, ?, ?, ?)", (pid, f"R-{code}", f"P-{code}", "2026-11-12", f"research-{code}"))


def test_explicit_participant_deletion_cleans_only_matching_legacy_mapping_rows():
    created = register()
    assert created.status_code == 200
    participant_id = created.json()["participant_id"]
    _create_mapping_rows(participant_id, "unrelated-pid")

    deleted = client.delete(f"/api/admin/participants/{participant_id}")
    assert deleted.status_code == 200, deleted.text
    with sqlite3.connect(get_settings().identity_mapping_path) as db:
        assert db.execute("SELECT participant_id FROM identity_mappings").fetchall() == [("unrelated-pid",)]
        assert db.execute("SELECT participant_id FROM research_code_mappings").fetchall() == [("unrelated-pid",)]
    with SessionLocal() as db:
        event = db.query(AuditEvent).filter_by(action="delete_participant", entity_id=participant_id).one()
        assert event.after_json["identity_mapping_cleanup"] == "complete"


def test_mapping_cleanup_closes_sqlite_connection(tmp_path, monkeypatch):
    path = tmp_path / "identities.sqlite3"
    path.touch()
    connections = []
    original_connect = sqlite3.connect

    class TrackingConnection(sqlite3.Connection):
        was_closed = False

        def close(self):
            self.was_closed = True
            super().close()

    def tracked_connect(*args, **kwargs):
        kwargs["factory"] = TrackingConnection
        connection = original_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(get_settings(), "identity_mapping_path", str(path))
    monkeypatch.setattr(identity_mapping.sqlite3, "connect", tracked_connect)

    assert identity_mapping.delete_participant_mappings("participant-1") == 0
    assert len(connections) == 1
    assert connections[0].was_closed


def test_mapping_cleanup_failure_is_durable_and_retryable(monkeypatch):
    created = register()
    participant_id = created.json()["participant_id"]
    _create_mapping_rows(participant_id, "unrelated-pid")
    original_delete = identity_mapping.delete_participant_mappings

    def fail_once(pid):
        assert pid == participant_id
        raise sqlite3.OperationalError("isolated mapping cleanup failure")

    monkeypatch.setattr(identity_mapping, "delete_participant_mappings", fail_once)
    response = client.delete(f"/api/admin/participants/{participant_id}")
    assert response.status_code == 503
    with SessionLocal() as db:
        assert db.get(Participant, participant_id) is None
        event = db.query(AuditEvent).filter_by(action="delete_participant", entity_id=participant_id).one()
        assert event.after_json["identity_mapping_cleanup"] == "pending"

    monkeypatch.setattr(identity_mapping, "delete_participant_mappings", original_delete)
    retry = client.delete(f"/api/admin/participants/{participant_id}")
    assert retry.status_code == 200
    with sqlite3.connect(get_settings().identity_mapping_path) as db:
        assert db.execute("SELECT participant_id FROM identity_mappings ORDER BY participant_id").fetchall() == [("unrelated-pid",)]
        assert db.execute("SELECT participant_id FROM research_code_mappings ORDER BY participant_id").fetchall() == [("unrelated-pid",)]
    with SessionLocal() as db:
        event = db.query(AuditEvent).filter_by(action="delete_participant", entity_id=participant_id).one()
        assert event.after_json["identity_mapping_cleanup"] == "complete"


def test_postgres_participant_code_columns_are_widened_with_foreign_keys_preserved(monkeypatch):
    columns = {
        "participants": [
            {"name": "id", "type": String(36)},
            {"name": "display_code", "type": String(36)},
        ],
        "attempts": [{"name": "participant_id", "type": String(36)}],
        "tutor_sessions": [{"name": "participant_id", "type": String(36)}],
        "participant_sessions": [{"name": "participant_id", "type": String(64)}],
        "idempotency_records": [{"name": "participant_id", "type": String(36)}],
        "audit_events": [{"name": "entity_id", "type": String(36)}],
    }
    foreign_keys = {
        "attempts": [{
            "name": "fk_attempt_participant",
            "constrained_columns": ["participant_id"],
            "referred_table": "participants",
            "referred_columns": ["id"],
            "options": {"ondelete": "CASCADE"},
        }],
        "tutor_sessions": [{
            "name": "fk_tutor_session_participant",
            "constrained_columns": ["participant_id"],
            "referred_table": "participants",
            "referred_columns": ["id"],
            "options": {},
        }],
        "participant_sessions": [{
            "name": "fk_participant_session_participant",
            "constrained_columns": ["participant_id"],
            "referred_table": "participants",
            "referred_columns": ["id"],
            "options": {"ondelete": "CASCADE"},
        }],
    }

    class Inspector:
        def get_table_names(self):
            return list(columns)

        def get_columns(self, table):
            return columns[table]

        def get_foreign_keys(self, table):
            return foreign_keys.get(table, [])

    class Connection:
        dialect = postgresql_dialect()

        def __init__(self):
            self.statements = []

        def execute(self, statement):
            sql = str(statement)
            self.statements.append(sql)
            if " ALTER COLUMN " in sql and " TYPE VARCHAR(64)" in sql:
                table = sql.split("ALTER TABLE ", 1)[1].split(" ALTER COLUMN ", 1)[0].strip('"')
                column = sql.split(" ALTER COLUMN ", 1)[1].split(" TYPE ", 1)[0].strip('"')
                next(item for item in columns[table] if item["name"] == column)["type"] = String(64)

    inspector = Inspector()
    connection = Connection()
    monkeypatch.setattr(db_session_module, "inspect", lambda _: inspector)

    db_session_module._ensure_participant_code_capacity(connection, "postgresql")

    statements = "\n".join(connection.statements)
    for table, column in (
        ("participants", "id"),
        ("participants", "display_code"),
        ("attempts", "participant_id"),
        ("tutor_sessions", "participant_id"),
        ("idempotency_records", "participant_id"),
        ("audit_events", "entity_id"),
    ):
        assert f"ALTER TABLE {table} ALTER COLUMN {column} TYPE VARCHAR(64)" in statements
    assert "DROP CONSTRAINT fk_attempt_participant" in statements
    assert "ADD CONSTRAINT fk_attempt_participant FOREIGN KEY (participant_id) REFERENCES participants (id) ON DELETE CASCADE" in statements
    assert "ADD CONSTRAINT fk_participant_session_participant FOREIGN KEY (participant_id) REFERENCES participants (id) ON DELETE CASCADE" in statements

    executed_count = len(connection.statements)
    db_session_module._ensure_participant_code_capacity(connection, "postgresql")
    assert len(connection.statements) == executed_count
