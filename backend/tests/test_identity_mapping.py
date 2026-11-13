import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from admin_client import AuthenticatedTestClient as TestClient
from sqlalchemy import text

from app.main import app
from app.db.session import SessionLocal, engine
from app.core.config import get_settings
from app.models import AuditEvent, IdempotencyRecord, Participant
from app.services import identity_mapping

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


def test_registration_validates_but_does_not_persist_research_code():
    key = str(uuid4())
    research_code = "001202611120001"
    response = register(research_code, key)
    assert response.status_code == 200, response.text
    participant_id = response.json()["participant_id"]
    assert research_code not in response.text
    assert not Path(get_settings().identity_mapping_path).exists()

    with SessionLocal() as db:
        participant = db.get(Participant, participant_id)
        assert participant.test_content_mode == "four_topic_fundamentals"
        assert participant.consent_document_version == "consent-2026-11-12-revised-v1"
        record = db.query(IdempotencyRecord).filter_by(idempotency_key=key).one()
        assert research_code not in record.request_hash
        assert research_code not in json.dumps(record.response_json)

    with engine.connect() as connection:
        tables = connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).all()
        for (table_name,) in tables:
            contents = connection.execute(text(f'SELECT * FROM "{table_name}"')).all()
            assert research_code not in str(contents)

    for path in (f"/api/admin/participants/{participant_id}/logs.csv", f"/api/admin/participants/{participant_id}/logs.xlsx"):
        exported = client.get(path)
        assert exported.status_code == 200
        assert research_code.encode() not in exported.content

    replay = register("999202611129999", key)
    assert replay.status_code == 200
    assert replay.json() == response.json()
    with SessionLocal() as db:
        assert db.query(Participant).filter_by(id=participant_id).count() == 1


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
