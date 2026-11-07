from __future__ import annotations

import csv
import io
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from admin_client import AuthenticatedTestClient
from app.db import session as database
from app.db.session import SessionLocal
from app.main import app
from app.models import Attempt, Base, Participant
from app.services.experiment import LOG_CSV_COLUMNS, _learning_burden
from split_api_support import complete_presurvey, create_trial, ok, select_roles


def _page_payload(participant_id, page_questions, *, selected_ids=None, page_id=None):
    selected_ids = selected_ids or [select_roles(question, [None])[0] for question in page_questions]
    return {
        "participant_id": participant_id,
        "phase": "pretest",
        "term_slug": page_questions[0]["term_slug"],
        "test_round": page_questions[0]["test_round"],
        "page_id": page_id or str(uuid4()),
        "answers": [
            {"question_id": question["question_id"], "selected_option_ids": [choice_id]}
            for question, choice_id in zip(page_questions, selected_ids, strict=True)
        ],
        "question_shown_at": "2026-10-30T01:00:00Z",
        "answered_at": "2026-10-30T01:00:08Z",
        "elapsed_time_sec": 8.0,
    }


def test_registration_freezes_test_page_mode_for_new_participants():
    client = AuthenticatedTestClient(app)
    participant_id = None
    try:
        participant_id = ok(client.post("/api/registrations", json={
            "assignment_code": "A",
            "consent_checked": True,
            "student_number": f"TERM-PAGE-{uuid4().hex}",
        }))["participant_id"]
        complete_presurvey(client, participant_id)
        with SessionLocal() as db:
            participant = db.get(Participant, participant_id)
            assert participant.test_page_mode == "per_term"
        response = ok(client.get(f"/api/experiment/{participant_id}/pretest"))
        assert response["test_page_mode"] == "per_term"
        assert len(response["questions"]) == 3
    finally:
        if participant_id:
            ok(client.delete(f"/api/admin/participants/{participant_id}"))


def test_null_page_mode_remains_unmodified_and_uses_legacy_display():
    with create_trial("A", "debug_fixed") as (client, participant_id):
        with SessionLocal() as db:
            participant = db.get(Participant, participant_id)
            participant.test_page_mode = None
            db.commit()

        response = ok(client.get(f"/api/experiment/{participant_id}/pretest"))
        assert response["test_page_mode"] == "per_question"
        with SessionLocal() as db:
            assert db.get(Participant, participant_id).test_page_mode is None


def test_term_page_endpoint_is_atomic_idempotent_and_records_one_shared_duration():
    with create_trial("B", "randomized") as (client, participant_id):
        response = ok(client.get(f"/api/experiment/{participant_id}/pretest"))
        assert response["test_page_mode"] == "per_term"
        page_questions = response["questions"][:2]
        assert [question["term_slug"] for question in page_questions] == [page_questions[0]["term_slug"]] * 2

        bad_payload = _page_payload(participant_id, page_questions)
        bad_payload["answers"][1]["selected_option_ids"] = ["not-an-option"]
        failed = client.post("/api/attempts/term-page", json=bad_payload, headers={"Idempotency-Key": "atomic-page-invalid"})
        assert failed.status_code == 400
        with SessionLocal() as db:
            assert db.query(Attempt).filter_by(participant_id=participant_id, phase="pretest").count() == 0

        payload = _page_payload(participant_id, page_questions)
        no_key = client.post("/api/attempts/term-page", json=payload)
        assert no_key.status_code == 400
        key = f"atomic-page-{uuid4().hex}"
        saved = ok(client.post("/api/attempts/term-page", json=payload, headers={"Idempotency-Key": key}))
        assert saved == {"saved": True, "saved_question_count": 2, "page_id": payload["page_id"]}
        assert ok(client.post("/api/attempts/term-page", json=payload, headers={"Idempotency-Key": key})) == saved

        conflict_payload = {**payload, "elapsed_time_sec": 9.0}
        conflict = client.post("/api/attempts/term-page", json=conflict_payload, headers={"Idempotency-Key": key})
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["error_code"] == "idempotency_key_conflict"

        with SessionLocal() as db:
            attempts = db.query(Attempt).filter_by(participant_id=participant_id, phase="pretest").all()
            assert len(attempts) == 2
            assert all(attempt.response_time_sec is None for attempt in attempts)
            assert {attempt.test_page_timing_json["page_id"] for attempt in attempts} == {payload["page_id"]}
            assert all(attempt.test_page_timing_json["measurement_version"] == "term_page_v1" for attempt in attempts)
            assert all(attempt.test_page_timing_json["elapsed_time_sec"] == 8.0 for attempt in attempts)
            assert _learning_burden(db, participant_id, attempts)["total_test_time_sec"] == 8.0

        reviewed = ok(client.get(f"/api/experiment/{participant_id}/pretest"))
        assert all(question["answer_status"] == "submitted" for question in reviewed["questions"][:2])
        assert not any(key in saved for key in ("is_correct", "correct_option_ids", "misconception_type"))

        logs = ok(client.get(f"/api/admin/participants/{participant_id}/logs"))
        assert logs["participant"]["test_page_mode"] == "per_term"
        assert logs["participant"]["effective_test_page_mode"] == "per_term"
        answer_rows = [row for row in logs["answer_history"] if row["phase"] == "pretest"]
        assert len(answer_rows) == 2
        assert all(row["response_time_unit"] == "term_page" for row in answer_rows)
        assert all(row["response_time_sec"] is None for row in answer_rows)

        csv_response = client.get(f"/api/admin/participants/{participant_id}/logs.csv")
        assert csv_response.status_code == 200
        assert next(csv.reader(io.StringIO(csv_response.text))) == LOG_CSV_COLUMNS


def test_term_page_conflict_keeps_existing_answer_and_does_not_save_its_pair():
    with create_trial("A", "debug_fixed") as (client, participant_id):
        questions = ok(client.get(f"/api/experiment/{participant_id}/pretest"))["questions"]
        pair = questions[:2]
        original_choice = select_roles(pair[0], ["unknown"])[0]
        ok(client.post("/api/attempts", json={
            "participant_id": participant_id,
            "phase": "pretest",
            "question_id": pair[0]["question_id"],
            "selected_option_ids": [original_choice],
        }))
        payload = _page_payload(participant_id, pair)
        mismatch = select_roles(pair[0], [None])[0]
        assert mismatch != original_choice
        payload["answers"][0]["selected_option_ids"] = [mismatch]
        response = client.post("/api/attempts/term-page", json=payload, headers={"Idempotency-Key": f"conflict-{uuid4().hex}"})
        assert response.status_code == 409
        assert response.json()["detail"]["error_code"] == "answer_already_submitted"
        with SessionLocal() as db:
            attempts = db.query(Attempt).filter_by(participant_id=participant_id, phase="pretest").all()
            assert len(attempts) == 1
            assert attempts[0].selected_option_ids == [original_choice]


def test_term_page_completes_matching_partial_answer_without_replacing_it():
    with create_trial("A", "debug_fixed") as (client, participant_id):
        page_questions = ok(client.get(f"/api/experiment/{participant_id}/pretest"))["questions"][:2]
        existing_choice = select_roles(page_questions[0], ["M1"])[0]
        ok(client.post("/api/attempts", json={
            "participant_id": participant_id,
            "phase": "pretest",
            "question_id": page_questions[0]["question_id"],
            "selected_option_ids": [existing_choice],
            "response_time_sec": 3.5,
        }))
        payload = _page_payload(participant_id, page_questions)
        payload["answers"][0]["selected_option_ids"] = [existing_choice]
        result = client.post("/api/attempts/term-page", json=payload, headers={"Idempotency-Key": f"partial-{uuid4().hex}"})
        assert result.status_code == 200, result.text
        with SessionLocal() as db:
            attempts = db.query(Attempt).filter_by(participant_id=participant_id, phase="pretest").all()
            assert len(attempts) == 2
            existing = next(attempt for attempt in attempts if attempt.question_id == page_questions[0]["question_id"])
            assert existing.selected_option_ids == [existing_choice]
            assert existing.response_time_sec is None
            assert existing.test_page_timing_json["page_id"] == payload["page_id"]
            assert all(attempt.test_page_timing_json["page_id"] == payload["page_id"] for attempt in attempts)


def test_page_mode_and_timing_columns_migrate_repeatably_without_backfill(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'term-page-migration.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        participant = Participant(display_code="OLD-TERM-PAGE", group_condition="control", experiment_spec_version=27)
        db.add(participant)
        db.commit()
        participant_id = participant.id

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE participants DROP COLUMN test_page_mode"))
        connection.execute(text("ALTER TABLE attempts DROP COLUMN test_page_timing_json"))
    monkeypatch.setattr(database, "engine", engine)
    database.init_db()
    database.init_db()

    with Session(engine) as db:
        assert db.get(Participant, participant_id).test_page_mode is None
    assert "test_page_mode" in {column["name"] for column in inspect(engine).get_columns("participants")}
    assert "test_page_timing_json" in {column["name"] for column in inspect(engine).get_columns("attempts")}
    engine.dispose()
