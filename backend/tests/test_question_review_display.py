from __future__ import annotations

import asyncio
from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from admin_client import AuthenticatedTestClient
from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID
from app.db.session import SessionLocal
from app.main import app
from app.models import Attempt, Base, Participant, Question, QuestionOption, Term, now
from app.seed.seed_questions import seed_database
from app.services import experiment
from app.services.question_review_display import current_setting
from split_api_support import complete_presurvey, create_trial, ok, select_roles


SETTING_ENDPOINT = "/api/admin/question-review-display"


@contextmanager
def set_question_reviews(enabled: bool):
    admin = AuthenticatedTestClient(app)
    previous = ok(admin.get(SETTING_ENDPOINT))["enabled"]
    ok(admin.put(SETTING_ENDPOINT, json={"enabled": enabled}))
    try:
        yield
    finally:
        ok(admin.put(SETTING_ENDPOINT, json={"enabled": previous}))


@pytest.fixture
def review_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        seed_database(db)
        participant = Participant(
            display_code=f"QR-UNIT-{uuid4().hex[:8]}",
            group_condition="control",
            current_step="pretest",
            experiment_spec_version=CURRENT_EXPERIMENT_SPEC_VERSION,
            protocol_id=CURRENT_PROTOCOL_ID,
            learning_content_version=15,
            show_question_reviews=True,
            option_order_mode="debug_fixed",
        )
        db.add(participant)
        db.commit()
        yield db, participant
    engine.dispose()


def _question_rows(db: Session, phase: str) -> list[dict]:
    source_phase = "retest" if phase == "final_test" else phase
    variant = "pretest_v1" if phase == "pretest" else "retest_v1"
    questions = (
        db.query(Question)
        .join(Term, Term.id == Question.term_id)
        .filter(
            Question.phase == source_phase,
            Question.variant_key.in_([f"{variant}_q1", f"{variant}_q2"]),
        )
        .order_by(Term.display_order, Question.variant_key)
        .all()
    )
    return [
        {
            "question_id": question.id,
            "term_slug": db.get(Term, question.term_id).slug,
            "term_label": db.get(Term, question.term_id).label,
        }
        for question in questions
    ]


def _add_answer(db: Session, participant: Participant, question: Question, phase: str, *, correct: bool) -> Attempt:
    options = db.query(QuestionOption).filter_by(question_id=question.id).all()
    selected = next(option for option in options if option.is_correct is correct)
    option_snapshot = [
        {"option_id": option.id, "label": chr(ord("A") + index), "body": option.body}
        for index, option in enumerate(options)
    ]
    attempt = Attempt(
        participant_id=participant.id,
        term_id=question.term_id,
        question_id=question.id,
        phase=phase,
        test_round="test" if phase == "pretest" else "retest_1",
        attempt_index=1,
        selected_option_ids=[selected.id],
        option_order_snapshot=option_snapshot,
        question_body_snapshot=question.body,
    )
    db.add(attempt)
    db.flush()
    return attempt


def _register(client: AuthenticatedTestClient, suffix: str) -> str:
    response = ok(client.post(
        "/api/registrations",
        json={
            "assignment_code": "A",
            "consent_checked": True,
            "student_number": f"QR-{suffix}-{uuid4().hex[:8]}",
        },
    ))
    complete_presurvey(client, response["participant_id"])
    return response["participant_id"]


def test_question_review_setting_defaults_on_and_admin_api_is_strict():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        assert current_setting(db) is True
    engine.dispose()

    assert TestClient(app).get(SETTING_ENDPOINT).status_code == 401
    client = AuthenticatedTestClient(app)
    response = ok(client.get(SETTING_ENDPOINT))
    assert response["applies_to"] == "new_standard_participants_only"
    assert client.get(SETTING_ENDPOINT).headers["cache-control"] == "no-store"
    for value in (None, 0, 1, "false", "true", [], {}):
        assert client.put(SETTING_ENDPOINT, json={"enabled": value}).status_code == 422
    assert client.put(SETTING_ENDPOINT, json={"enabled": True, "extra": 1}).status_code == 422


def test_registration_snapshots_reviews_for_standard_only_and_preserves_legacy_null():
    client = AuthenticatedTestClient(app)
    previous_review = ok(client.get(SETTING_ENDPOINT))["enabled"]
    previous_order = ok(client.get("/api/admin/option-order"))["mode"]
    participant_ids: list[str] = []
    legacy_id: str | None = None
    try:
        ok(client.put(SETTING_ENDPOINT, json={"enabled": True}))
        standard_on = _register(client, "STANDARD-ON")
        participant_ids.append(standard_on)
        ok(client.put(SETTING_ENDPOINT, json={"enabled": False}))
        standard_off = _register(client, "STANDARD-OFF")
        participant_ids.append(standard_off)

        with SessionLocal() as db:
            assert db.get(Participant, standard_on).show_question_reviews is True
            assert db.get(Participant, standard_off).show_question_reviews is False

            legacy = Participant(
                display_code=f"QR-OLD-{uuid4().hex[:8]}",
                group_condition="control",
                current_step="start",
                experiment_spec_version=27,
                protocol_id="experiment-plan-2026-10-29-split-tests-v1",
                show_question_reviews=None,
            )
            db.add(legacy)
            db.commit()
            legacy_id = legacy.id

        from app.db import session as database

        database.init_db()
        with SessionLocal() as db:
            assert db.get(Participant, legacy_id).show_question_reviews is None
            assert db.get(Participant, standard_on).show_question_reviews is True
            assert db.get(Participant, standard_off).show_question_reviews is False
    finally:
        for participant_id in participant_ids:
            ok(client.delete(f"/api/admin/participants/{participant_id}"))
        if legacy_id:
            with SessionLocal() as db:
                legacy = db.get(Participant, legacy_id)
                if legacy is not None:
                    db.delete(legacy)
                    db.commit()
        ok(client.put(SETTING_ENDPOINT, json={"enabled": previous_review}))
        ok(client.put("/api/admin/option-order", json={"mode": previous_order}))


def test_pair_review_requires_both_answers_is_private_and_acknowledgement_is_idempotent():
    with set_question_reviews(True):
        with create_trial("A", "debug_fixed") as (client, participant_id):
            questions = ok(client.get(f"/api/experiment/{participant_id}/pretest"))["questions"]
            term_slug = questions[0]["term_slug"]
            pair = [question for question in questions if question["term_slug"] == term_slug]
            assert len(pair) == 2

            selected_ids = [
                select_roles(pair[0], ["unknown"]),
                select_roles(pair[1], [None]),
            ]
            for question, option_ids in zip(pair[:1], selected_ids[:1], strict=True):
                response = client.post(
                    "/api/attempts",
                    json={
                        "participant_id": participant_id,
                        "question_id": question["question_id"],
                        "phase": "pretest",
                        "selected_option_ids": option_ids,
                    },
                )
                assert response.status_code == 200, response.text
            assert ok(client.get(f"/api/experiment/{participant_id}/pretest"))["pending_question_review"] is None

            incomplete = client.post(
                f"/api/participants/{participant_id}/question-review-acknowledgements",
                json={"phase": "pretest", "term_slug": term_slug},
            )
            assert incomplete.status_code == 409

            second = pair[1]
            response = client.post(
                "/api/attempts",
                json={
                    "participant_id": participant_id,
                    "question_id": second["question_id"],
                    "phase": "pretest",
                    "selected_option_ids": selected_ids[1],
                },
            )
            assert response.status_code == 200, response.text
            review = ok(client.get(f"/api/experiment/{participant_id}/pretest"))["pending_question_review"]
            assert set(review) == {"phase", "term_slug", "term_label", "results"}
            assert review["term_slug"] == term_slug
            assert len(review["results"]) == 2

            for index, result in enumerate(review["results"]):
                question = pair[index]
                option_id = selected_ids[index][0]
                selected = next(option for option in question["options"] if option["option_id"] == option_id)
                assert set(result) == {"question_number", "selected_option", "is_correct"}
                assert result["question_number"] == index + 1
                assert result["selected_option"] == {"label": selected["label"], "body": selected["body"]}
                assert result["is_correct"] is (index == 1)
                assert set(result["selected_option"]) == {"label", "body"}

            ack_url = f"/api/participants/{participant_id}/question-review-acknowledgements"
            ack_payload = {"phase": "pretest", "term_slug": term_slug}
            first_ack = client.post(ack_url, json=ack_payload)
            second_ack = client.post(ack_url, json=ack_payload)
            assert first_ack.status_code == second_ack.status_code == 200
            assert second_ack.json() == first_ack.json()
            assert first_ack.json()["current_step"] == "pretest"
            with SessionLocal() as db:
                acknowledged = db.query(Attempt).filter_by(
                    participant_id=participant_id,
                    phase="pretest",
                    question_id=second["question_id"],
                ).one()
                acknowledged_at = acknowledged.question_review_acknowledged_at
                assert acknowledged_at is not None
            assert ok(client.get(f"/api/experiment/{participant_id}/pretest"))["pending_question_review"] is None
            with SessionLocal() as db:
                assert db.query(Attempt).filter_by(
                    participant_id=participant_id,
                    phase="pretest",
                    question_id=second["question_id"],
                ).one().question_review_acknowledged_at == acknowledged_at


def test_out_of_order_ack_and_pretest_diagnosis_are_rejected_without_scoring():
    with set_question_reviews(True):
        with create_trial("B", "randomized") as (client, participant_id):
            questions = ok(client.get(f"/api/experiment/{participant_id}/pretest"))["questions"]
            for question in questions:
                selected_ids = select_roles(question, ["unknown"])
                response = client.post(
                    "/api/attempts",
                    json={
                        "participant_id": participant_id,
                        "question_id": question["question_id"],
                        "phase": "pretest",
                        "selected_option_ids": selected_ids,
                    },
                )
                assert response.status_code == 200, response.text

            review = ok(client.get(f"/api/experiment/{participant_id}/pretest"))["pending_question_review"]
            assert review is not None
            wrong_order = client.post(
                f"/api/participants/{participant_id}/question-review-acknowledgements",
                json={"phase": "pretest", "term_slug": questions[-1]["term_slug"]},
            )
            assert wrong_order.status_code == 409

            diagnosis = client.post(f"/api/participants/{participant_id}/diagnose-pretest", json={})
            assert diagnosis.status_code == 409
            with SessionLocal() as db:
                participant = db.get(Participant, participant_id)
                attempts = db.query(Attempt).filter_by(participant_id=participant_id, phase="pretest").all()
                assert participant.current_step == "pretest"
                assert len(attempts) == 6
                assert all(attempt.is_correct is None and attempt.score is None for attempt in attempts)
                assert all(attempt.question_review_acknowledged_at is None for attempt in attempts)


@pytest.mark.parametrize("phase", ["retest", "final_test"])
def test_score_phase_rejects_an_unacknowledged_review_without_partial_scoring(review_db, phase):
    db, participant = review_db
    participant.current_step = phase
    rows = _question_rows(db, phase)
    assert len(rows) == 6
    for row in rows:
        question = db.get(Question, row["question_id"])
        _add_answer(db, participant, question, phase, correct=False)

    with pytest.raises(HTTPException) as error:
        asyncio.run(experiment.score_phase(db, participant.id, phase))
    assert error.value.status_code == 409
    db.expire_all()
    attempts = db.query(Attempt).filter_by(participant_id=participant.id, phase=phase).all()
    assert len(attempts) == 6
    assert all(attempt.is_correct is None and attempt.score is None for attempt in attempts)


def test_none_variant_key_is_safe_and_acknowledged_term_skips_both_questions(review_db, monkeypatch):
    db, participant = review_db
    rows = _question_rows(db, "pretest")
    first = db.get(Question, rows[0]["question_id"])
    first.variant_key = None
    assert experiment.pending_question_review(db, participant.id, "pretest", [rows[0]]) is None

    monkeypatch.setattr(experiment, "question_payloads", lambda *_args, **_kwargs: [rows[0]])
    with pytest.raises(HTTPException) as error:
        experiment.acknowledge_question_review(db, participant.id, "pretest", rows[0]["term_slug"])
    assert error.value.status_code == 409

    db.rollback()
    rows = _question_rows(db, "pretest")
    attempts_by_question = {}
    for row in rows:
        question = db.get(Question, row["question_id"])
        attempts_by_question[question.id] = _add_answer(db, participant, question, "pretest", correct=False)
    acknowledged_term = rows[0]["term_slug"]
    attempts_by_question[rows[1]["question_id"]].question_review_acknowledged_at = now()
    attempts_by_question[rows[0]["question_id"]].option_order_snapshot = None
    db.flush()

    selected_attempt_ids: list[str] = []
    original_selected_options = experiment._selected_options

    def record_selected_options(session, attempt):
        selected_attempt_ids.append(attempt.id)
        return original_selected_options(session, attempt)

    monkeypatch.setattr(experiment, "_selected_options", record_selected_options)
    pending = experiment.pending_question_review(db, participant.id, "pretest", rows)
    assert pending is not None
    assert pending["term_slug"] == rows[2]["term_slug"]
    assert len(selected_attempt_ids) == 4
    assert attempts_by_question[rows[0]["question_id"]].id not in selected_attempt_ids
    assert attempts_by_question[rows[1]["question_id"]].id not in selected_attempt_ids
    assert acknowledged_term == rows[0]["term_slug"]
