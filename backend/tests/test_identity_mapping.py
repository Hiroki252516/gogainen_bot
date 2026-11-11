import asyncio
import json
import sqlite3
from uuid import uuid4

import pytest
from admin_client import AuthenticatedTestClient as TestClient
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session as SQLAlchemySession

from app.main import app
from app.db.session import SessionLocal, engine
from app.core.config import get_settings
from app.models import AICallLog, AuditEvent, Participant, IdempotencyRecord
from app.services import identity_mapping
from app.services.experiment import _record_ai_log
from app.services.idempotency import registration_key_was_deleted

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_mappings(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "identity_mapping_path", str(tmp_path / "identities.sqlite3"))


def register(research_code=None, key=None):
    if research_code is None:
        research_code = str(uuid4().int)
    return client.post("/api/registrations", json={"assignment_code": "A", "consent_checked": True,
                                                "research_code": research_code},
                       headers={"Idempotency-Key": key or str(uuid4())})


@pytest.mark.parametrize("research_code", ["", "   ", "1" * 65, "123\n", "123\t", "1\x002", "１２３"])
def test_invalid_research_codes_are_not_echoed(research_code):
    response = register(research_code)
    assert response.status_code == 400
    assert not identity_mapping.list_research_code_mappings()


def test_registration_preserves_leading_zeroes_and_replay_does_not_restore_deleted_mapping():
    key = str(uuid4())
    research_code = "001202611110001"
    response = register(research_code, key)
    assert response.status_code == 200
    pid = response.json()["participant_id"]
    assert register(research_code, key).json() == response.json()
    rows = client.get("/api/admin/research-code-mappings")
    assert rows.headers["cache-control"] == "no-store"
    assert rows.json()["mappings"][0]["research_code"] == research_code
    csv = client.get("/api/admin/research-code-mappings.csv")
    assert csv.content.startswith(b"\xef\xbb\xbf")
    assert research_code in csv.text
    assert research_code not in response.text
    with SessionLocal() as db:
        p = db.get(Participant, pid)
        assert p.consented_at and p.consent_document_version == identity_mapping.CONSENT_DOCUMENT_VERSION
        record = db.query(IdempotencyRecord).filter_by(idempotency_key=key).one()
        assert research_code not in json.dumps(record.response_json)
    # Scan every table, including raw prompts, idempotency and audit data.
    with engine.connect() as connection:
        for table in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'")):
            contents = connection.execute(text(f'SELECT * FROM "{table[0]}"')).all()
            assert research_code not in str(contents)
    exported = client.get(f"/api/admin/participants/{pid}/logs.csv")
    assert exported.status_code == 200 and research_code not in exported.text
    exported_xlsx = client.get(f"/api/admin/participants/{pid}/logs.xlsx")
    assert exported_xlsx.status_code == 200 and research_code.encode() not in exported_xlsx.content
    assert client.delete(f"/api/admin/research-code-mappings/{pid}").json()["deleted_count"] == 1
    assert register(research_code, key).json() == response.json()
    assert client.get("/api/admin/research-code-mappings").json()["mappings"] == []
    with SessionLocal() as db:
        assert db.get(Participant, pid) is not None


def test_delete_all_preserves_research_and_securely_removes_identifier():
    codes = ["002026111100001", "002026111100002"]
    ids = [register(code).json()["participant_id"] for code in codes]
    assert client.delete("/api/admin/research-code-mappings").json() == {"deleted_count": 2}
    assert not identity_mapping.list_research_code_mappings()
    with SessionLocal() as db:
        assert all(db.get(Participant, pid) for pid in ids)

    # The legacy student-number table is independent and is not affected by the new endpoint.
    for pid, code in zip(ids, codes):
        identity_mapping.save_mapping(pid, f"LEGACY-{pid}", f"STUDENT-{pid}", "2026-11-11T00:00:00", f"LEGACY-{pid}")
    assert client.delete("/api/admin/identity-mappings").json() == {"deleted_count": 2}
    assert not identity_mapping.list_mappings()
    from pathlib import Path
    assert b"STUDENT-" not in Path(get_settings().identity_mapping_path).read_bytes()
    with SessionLocal() as db:
        assert all(db.get(Participant, pid) for pid in ids)


def test_withdrawal_deletes_mapping_and_rejects_late_ai_log():
    key = str(uuid4())
    pid = register("003202611110003", key).json()["participant_id"]
    identity_mapping.save_mapping(pid, "P-OLD", "OLD-STUDENT", "2026-11-11T00:00:00", "legacy-withdrawal")
    result = client.delete(f"/api/admin/participants/{pid}")
    assert result.status_code == 200
    assert not identity_mapping.list_mappings()
    assert not identity_mapping.list_research_code_mappings()
    assert register(key=key).status_code == 409
    assert not identity_mapping.list_research_code_mappings()
    with SessionLocal() as db:
        deletion = db.query(AuditEvent).filter_by(action="delete_participant", entity_id=pid).one()
        assert deletion.after_json["identity_mapping_cleanup"] == "complete"
        with pytest.raises(HTTPException) as exc:
            _record_ai_log(db, AICallLog(provider="mock", purpose="generate_tutoring_turn",
                                       status="success", request_payload={"participant_id": pid}))
        assert exc.value.status_code == 404
        assert not db.query(AICallLog).filter(AICallLog.request_payload.contains(pid)).all()


def test_retired_registration_query_matches_exact_array_member_without_changing_audit():
    key = f'{uuid4()}-"_%[]日本語'
    with SessionLocal() as db:
        events = [
            AuditEvent(actor="test", action=action, entity_type=entity_type,
                       before_json=payload)
            for action, entity_type, payload in (
                ("delete_participant", "participant", {"registration_keys": ["another-key", key]}),
                ("delete_participant", "participant", {"display_code": "legacy-without-keys"}),
                ("delete_participant", "participant", None),
                ("delete_participant", "participant", {"registration_keys": []}),
                ("other_action", "participant", {"registration_keys": [f"{key}-other-action"]}),
                ("delete_participant", "other_entity", {"registration_keys": [f"{key}-other-entity"]}),
            )
        ]
        db.add_all(events)
        db.commit()
        before = {row.id: json.dumps(row.before_json, sort_keys=True) for row in events}
        assert registration_key_was_deleted(db, key)
        assert not registration_key_was_deleted(db, key[:12])
        assert not registration_key_was_deleted(db, f"{key}-other-action")
        assert not registration_key_was_deleted(db, f"{key}-other-entity")
        db.expire_all()
        assert {row.id: json.dumps(row.before_json, sort_keys=True) for row in events} == before


def test_identity_deletion_failure_is_durable_and_retryable(monkeypatch):
    key = str(uuid4())
    pid = register(key=key).json()["participant_id"]
    identity_mapping.save_mapping(pid, "P-OLD", "OLD-STUDENT", "2026-11-11T00:00:00", "legacy-cleanup")
    original_delete = identity_mapping.delete_participant_mappings

    def fail_mapping_delete(participant_id):
        assert participant_id == pid
        # The durable research deletion and cleanup marker precede this DB.
        with SessionLocal() as observer:
            assert observer.get(Participant, pid) is None
            event = observer.query(AuditEvent).filter_by(action="delete_participant", entity_id=pid).one()
            assert event.after_json["identity_mapping_cleanup"] == "pending"
        raise sqlite3.OperationalError("isolated mapping deletion failure")

    monkeypatch.setattr(identity_mapping, "delete_participant_mappings", fail_mapping_delete)
    with TestClient(app, raise_server_exceptions=False) as no_raise:
        response = no_raise.delete(f"/api/admin/participants/{pid}")
    assert response.status_code == 503
    with SessionLocal() as db:
        assert db.get(Participant, pid) is None
        assert not db.query(IdempotencyRecord).filter_by(idempotency_key=key).one_or_none()
        event = db.query(AuditEvent).filter_by(action="delete_participant", entity_id=pid).one()
        assert event.after_json["identity_mapping_cleanup"] == "pending"
    assert [row["participant_id"] for row in identity_mapping.list_research_code_mappings()] == [pid]
    assert [row["participant_id"] for row in identity_mapping.list_mappings()] == [pid]
    assert register(key=key).status_code == 409

    monkeypatch.setattr(identity_mapping, "delete_participant_mappings", original_delete)
    retry = client.delete(f"/api/admin/participants/{pid}")
    assert retry.status_code == 200
    assert not identity_mapping.list_research_code_mappings()
    assert not identity_mapping.list_mappings()
    with SessionLocal() as db:
        event = db.query(AuditEvent).filter_by(action="delete_participant", entity_id=pid).one()
        assert event.after_json["identity_mapping_cleanup"] == "complete"


def test_research_delete_commit_failure_keeps_identity_mapping(monkeypatch):
    pid = register().json()["participant_id"]
    from app import main as main_module

    original_delete = main_module.delete_participant
    original_commit = SQLAlchemySession.commit
    mapping_delete_calls = []
    original_mapping_delete = identity_mapping.delete_participant_mappings

    def stage_then_fail_commit(db, participant_id):
        result = original_delete(db, participant_id)
        db.info["fail_research_delete_commit"] = True
        return result

    def fail_selected_commit(db):
        if db.info.pop("fail_research_delete_commit", False):
            raise sqlite3.OperationalError("isolated research commit failure")
        return original_commit(db)

    def record_mapping_delete(participant_id):
        mapping_delete_calls.append(participant_id)
        return original_mapping_delete(participant_id)

    monkeypatch.setattr(main_module, "delete_participant", stage_then_fail_commit)
    monkeypatch.setattr(SQLAlchemySession, "commit", fail_selected_commit)
    monkeypatch.setattr(identity_mapping, "delete_participant_mappings", record_mapping_delete)
    with TestClient(app, raise_server_exceptions=False) as no_raise:
        response = no_raise.delete(f"/api/admin/participants/{pid}")

    assert response.status_code == 500
    assert mapping_delete_calls == []
    assert [row["participant_id"] for row in identity_mapping.list_research_code_mappings()] == [pid]
    with SessionLocal() as db:
        assert db.get(Participant, pid) is not None
        assert not db.query(AuditEvent).filter_by(action="delete_participant", entity_id=pid).one_or_none()


def test_cleanup_status_commit_failure_is_recovered_idempotently(monkeypatch):
    pid = register().json()["participant_id"]
    original_commit = SQLAlchemySession.commit

    def fail_cleanup_status_commit(db):
        if any(
            isinstance(row, AuditEvent)
            and (row.after_json or {}).get("identity_mapping_cleanup") == "complete"
            for row in db.dirty
        ):
            raise sqlite3.OperationalError("isolated cleanup status commit failure")
        return original_commit(db)

    monkeypatch.setattr(SQLAlchemySession, "commit", fail_cleanup_status_commit)
    with TestClient(app, raise_server_exceptions=False) as no_raise:
        response = no_raise.delete(f"/api/admin/participants/{pid}")

    assert response.status_code == 503
    assert not identity_mapping.list_research_code_mappings()
    with SessionLocal() as db:
        assert db.get(Participant, pid) is None
        event = db.query(AuditEvent).filter_by(action="delete_participant", entity_id=pid).one()
        assert event.after_json["identity_mapping_cleanup"] == "pending"

    monkeypatch.setattr(SQLAlchemySession, "commit", original_commit)
    retry = client.delete(f"/api/admin/participants/{pid}")
    assert retry.status_code == 200
    assert not identity_mapping.list_research_code_mappings()
    with SessionLocal() as db:
        event = db.query(AuditEvent).filter_by(action="delete_participant", entity_id=pid).one()
        assert event.after_json["identity_mapping_cleanup"] == "complete"


def test_startup_recovers_pending_identity_mapping_deletion(monkeypatch):
    pid = register().json()["participant_id"]
    original_delete = identity_mapping.delete_participant_mappings

    def fail_once(participant_id):
        raise sqlite3.OperationalError("simulated process-time identity store outage")

    monkeypatch.setattr(identity_mapping, "delete_participant_mappings", fail_once)
    with TestClient(app, raise_server_exceptions=False) as no_raise:
        response = no_raise.delete(f"/api/admin/participants/{pid}")
    assert response.status_code == 503
    assert [row["participant_id"] for row in identity_mapping.list_research_code_mappings()] == [pid]

    monkeypatch.setattr(identity_mapping, "delete_participant_mappings", original_delete)
    with TestClient(app) as restarted:
        assert restarted.get("/api/health").status_code == 200
    assert not identity_mapping.list_research_code_mappings()
    with SessionLocal() as db:
        event = db.query(AuditEvent).filter_by(action="delete_participant", entity_id=pid).one()
        assert event.after_json["identity_mapping_cleanup"] == "complete"


def test_mapping_failure_does_not_create_participant_and_same_key_can_retry(monkeypatch):
    key = str(uuid4())
    original = identity_mapping.save_research_code_mapping
    with SessionLocal() as db:
        before = db.query(Participant).count()
    def save_then_fail(*args, **kwargs):
        original(*args, **kwargs)
        raise sqlite3.OperationalError("isolated failure")
    monkeypatch.setattr(identity_mapping, "save_research_code_mapping", save_then_fail)
    with TestClient(app, raise_server_exceptions=False) as no_raise:
        response = no_raise.post("/api/registrations", json={"assignment_code": "A", "consent_checked": True,
                                                            "research_code": "004202611110004"},
                                 headers={"Idempotency-Key": key})
    assert response.status_code == 500 and "004202611110004" not in response.text
    with SessionLocal() as db:
        assert db.query(Participant).count() == before
    assert not identity_mapping.list_research_code_mappings()
    monkeypatch.setattr(identity_mapping, "save_research_code_mapping", original)
    assert register("004202611110004", key).status_code == 200


def test_validation_does_not_echo_malformed_identifier():
    response = client.post("/api/registrations", json={
        "assignment_code": "A", "consent_checked": True, "research_code": "012345",
        "student_number": {"secret": "DO-NOT-ECHO"},
    })
    assert response.status_code == 422 and "DO-NOT-ECHO" not in response.text
    assert client.post("/api/participants", json={"assignment_code": "A", "consent_checked": True}).status_code == 422


def test_duplicate_research_code_is_rejected_without_leaking_or_creating_second_participant():
    research_code = "005202611110005"
    first = register(research_code)
    assert first.status_code == 200
    with SessionLocal() as db:
        before = db.query(Participant).count()
    duplicate = register(research_code)
    assert duplicate.status_code == 409
    assert research_code not in duplicate.text
    with SessionLocal() as db:
        assert db.query(Participant).count() == before
    assert len([row for row in identity_mapping.list_research_code_mappings() if row["research_code"] == research_code]) == 1


def test_same_registration_key_rejects_a_different_code_without_echoing_either_value():
    key = str(uuid4())
    first_code, second_code = "009202611110009", "010202611110010"
    first = register(first_code, key)
    assert first.status_code == 200
    replay = register(second_code, key)
    assert replay.status_code == 409
    assert first_code not in replay.text and second_code not in replay.text
    assert identity_mapping.research_code_for_registration_key(key) == first_code


def test_delete_while_ai_is_pending_does_not_recreate_logs(monkeypatch):
    from app.services import experiment
    pid = register().json()["participant_id"]

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        class DelayedBackend:
            provider = "mock"
            async def generate_correct_answer_summary(self, payload):
                entered.set()
                await release.wait()
                return {"summary": "合成の説明"}
        monkeypatch.setattr(experiment, "get_ai_backend", lambda **kwargs: DelayedBackend())
        with SessionLocal() as db:
            task = asyncio.create_task(experiment._ai_call(db, "generate_correct_answer_summary", {"participant_id": pid}))
            await entered.wait()
            with SessionLocal() as deleting:
                experiment.delete_participant(deleting, pid)
            release.set()
            with pytest.raises(HTTPException) as exc:
                await task
            assert exc.value.status_code == 404
    asyncio.run(scenario())
    with SessionLocal() as db:
        assert not any((row.request_payload or {}).get("participant_id") == pid for row in db.query(AICallLog))


def test_identity_store_cannot_use_research_database(monkeypatch):
    from sqlalchemy.engine import make_url
    monkeypatch.setattr(get_settings(), "identity_mapping_path", make_url(get_settings().database_url).database)
    with pytest.raises(RuntimeError, match="研究DB"):
        identity_mapping.list_mappings()


def test_blank_retry_key_still_rolls_back_when_mapping_fails(monkeypatch):
    def fail(*args):
        raise sqlite3.OperationalError("isolated failure")
    monkeypatch.setattr(identity_mapping, "save_research_code_mapping", fail)
    with SessionLocal() as db:
        before = db.query(Participant).count()
    with TestClient(app, raise_server_exceptions=False) as no_raise:
        response = no_raise.post("/api/registrations", json={"assignment_code": "A", "consent_checked": True,
                                                            "research_code": "006202611110006"},
                                 headers={"Idempotency-Key": "   "})
    assert response.status_code == 500
    with SessionLocal() as db:
        assert db.query(Participant).count() == before


def test_csv_formula_cells_are_neutralized():
    import csv
    import io
    register("007202611110007")
    response = client.get("/api/admin/research-code-mappings.csv")
    row = list(csv.reader(io.StringIO(response.text.lstrip("\ufeff"))))[1]
    assert row[0] == "007202611110007"


def test_research_mapping_and_legacy_mapping_are_separate():
    response = register("008202611110008")
    pid = response.json()["participant_id"]
    identity_mapping.save_mapping(pid, "P-LEGACY", "OLD-STUDENT-NUMBER", "2026-11-11T00:00:00", "legacy-key")

    assert client.get("/api/admin/identity-mappings").json()["mappings"][0]["student_number"] == "OLD-STUDENT-NUMBER"
    assert client.get("/api/admin/research-code-mappings").json()["mappings"][0]["research_code"] == "008202611110008"
    assert client.delete(f"/api/admin/research-code-mappings/{pid}").json()["deleted_count"] == 1
    assert identity_mapping.list_mappings()[0]["student_number"] == "OLD-STUDENT-NUMBER"
