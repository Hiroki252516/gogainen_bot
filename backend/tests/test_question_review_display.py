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
from app.core.question_sets import ASSESSMENT_MODE_BANK_VERSIONS
from app.db.session import SessionLocal
from app.main import app
from app.models import Attempt, Base, Participant, Question, QuestionOption, RuntimeSetting, Term, now
from app.seed.seed_questions import seed_database
from app.services import experiment
from split_api_support import complete_presurvey, create_trial, ok, select_roles

@contextmanager
def set_question_reviews(enabled: bool):
    assert enabled is True
    yield


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
            test_content_mode="application",
            learning_content_version=15,
            show_question_reviews=True,
            first_question_only=True,
            option_order_mode="debug_fixed",
        )
        db.add(participant)
        db.commit()
        yield db, participant
    engine.dispose()


def _question_rows(db: Session, phase: str, numbers: tuple[int, ...] = (1,)) -> list[dict]:
    source_phase = "retest" if phase == "final_test" else phase
    variant = "pretest_v1" if phase == "pretest" else "retest_v1"
    questions = (
        db.query(Question)
        .join(Term, Term.id == Question.term_id)
        .filter(
            Question.phase == source_phase,
            Question.is_active.is_(True),
            Question.construct_key.endswith(ASSESSMENT_MODE_BANK_VERSIONS["application"]),
            Question.variant_key.in_([f"{variant}_q{number}" for number in numbers]),
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


def test_question_review_is_fixed_on_and_setting_api_is_removed():
    for client in (TestClient(app), AuthenticatedTestClient(app)):
        assert client.get("/api/admin/question-review-display").status_code == 404
        assert client.put("/api/admin/question-review-display", json={"enabled": False}).status_code == 404


def test_registration_snapshots_reviews_for_standard_only_and_preserves_legacy_null():
    client = AuthenticatedTestClient(app)
    previous_order = ok(client.get("/api/admin/option-order"))["mode"]
    participant_ids: list[str] = []
    legacy_id: str | None = None
    previous_settings = None
    try:
        with SessionLocal() as db:
            row = db.get(RuntimeSetting, 1)
            if row is None:
                row = RuntimeSetting(id=1)
                db.add(row)
            previous_settings = (row.show_question_reviews, row.first_question_only)
            row.show_question_reviews = False
            row.first_question_only = False
            db.commit()
        participant_id = _register(client, "FIXED-ON")
        participant_ids.append(participant_id)

        with SessionLocal() as db:
            participant = db.get(Participant, participant_id)
            assert participant.show_question_reviews is True
            assert participant.first_question_only is True
            assert participant.show_pretest_results is False
            assert participant.show_retest_results is False
            assert len(experiment.question_payloads(db, participant_id, "pretest")) == 3

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
            assert db.get(Participant, participant_id).show_question_reviews is True
    finally:
        for participant_id in participant_ids:
            ok(client.delete(f"/api/admin/participants/{participant_id}"))
        if legacy_id:
            with SessionLocal() as db:
                legacy = db.get(Participant, legacy_id)
                if legacy is not None:
                    db.delete(legacy)
                    db.commit()
        if previous_settings is not None:
            with SessionLocal() as db:
                row = db.get(RuntimeSetting, 1)
                row.show_question_reviews, row.first_question_only = previous_settings
                db.commit()
        ok(client.put("/api/admin/option-order", json={"mode": previous_order}))


def test_legacy_pair_review_waits_for_both_question_answers(review_db):
    db, participant = review_db
    participant.experiment_spec_version = 40
    participant.protocol_id = "experiment-plan-2026-11-07-control-shared-prompt-v1"
    participant.first_question_only = False
    rows = _question_rows(db, "pretest", numbers=(1, 2))
    assert len(rows) == 6

    term_slug = rows[0]["term_slug"]
    pair = [row for row in rows if row["term_slug"] == term_slug]
    assert len(pair) == 2
    assert [
        db.get(Question, row["question_id"]).variant_key for row in pair
    ] == ["pretest_v1_q1", "pretest_v1_q2"]

    first = db.get(Question, pair[0]["question_id"])
    _add_answer(db, participant, first, "pretest", correct=False)
    assert experiment.pending_question_review(db, participant.id, "pretest", rows) is None

    second = db.get(Question, pair[1]["question_id"])
    _add_answer(db, participant, second, "pretest", correct=False)
    review = experiment.pending_question_review(db, participant.id, "pretest", rows)
    assert review is not None
    assert review["term_slug"] == term_slug
    assert [result["question_number"] for result in review["results"]] == [1, 2]


def test_single_question_review_is_private_and_acknowledgement_is_idempotent():
    with set_question_reviews(True):
        with create_trial("A", "debug_fixed", first_question_only=True) as (client, participant_id):
            questions = ok(client.get(f"/api/experiment/{participant_id}/pretest"))["questions"]
            question = questions[0]
            term_slug = question["term_slug"]
            assert len([item for item in questions if item["term_slug"] == term_slug]) == 1
            assert ok(client.get(f"/api/experiment/{participant_id}/pretest"))["pending_question_review"] is None

            ack_url = f"/api/participants/{participant_id}/question-review-acknowledgements"
            ack_payload = {"phase": "pretest", "term_slug": term_slug}
            assert client.post(ack_url, json=ack_payload).status_code == 409

            selected_ids = select_roles(question, ["unknown"])
            response = client.post("/api/attempts", json={
                "participant_id": participant_id,
                "question_id": question["question_id"],
                "phase": "pretest",
                "selected_option_ids": selected_ids,
            })
            assert response.status_code == 200, response.text
            review = ok(client.get(f"/api/experiment/{participant_id}/pretest"))["pending_question_review"]
            assert set(review) == {"phase", "term_slug", "term_label", "results"}
            assert review["term_slug"] == term_slug
            assert len(review["results"]) == 1
            result = review["results"][0]
            selected = next(option for option in question["options"] if option["option_id"] == selected_ids[0])
            assert set(result) == {"question_number", "selected_option", "is_correct"}
            assert result["question_number"] == 1
            assert result["selected_option"] == {"label": selected["label"], "body": selected["body"]}
            assert result["is_correct"] is False
            assert set(result["selected_option"]) == {"label", "body"}

            first_ack = client.post(ack_url, json=ack_payload)
            second_ack = client.post(ack_url, json=ack_payload)
            assert first_ack.status_code == second_ack.status_code == 200
            assert second_ack.json() == first_ack.json()
            with SessionLocal() as db:
                acknowledged = db.query(Attempt).filter_by(
                    participant_id=participant_id,
                    phase="pretest",
                    question_id=question["question_id"],
                ).one()
                assert acknowledged.question_review_acknowledged_at is not None
            assert ok(client.get(f"/api/experiment/{participant_id}/pretest"))["pending_question_review"] is None


def test_out_of_order_ack_and_pretest_diagnosis_are_rejected_without_scoring():
    with set_question_reviews(True):
        with create_trial("B", "randomized", first_question_only=True) as (client, participant_id):
            questions = ok(client.get(f"/api/experiment/{participant_id}/pretest"))["questions"]
            assert len(questions) == 3
            for question in questions:
                selected_ids = select_roles(question, ["unknown"])
                response = client.post("/api/attempts", json={
                    "participant_id": participant_id,
                    "question_id": question["question_id"],
                    "phase": "pretest",
                    "selected_option_ids": selected_ids,
                })
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
                assert len(attempts) == 3
                assert all(attempt.is_correct is None and attempt.score is None for attempt in attempts)
                assert all(attempt.question_review_acknowledged_at is None for attempt in attempts)


@pytest.mark.parametrize("phase", ["retest", "final_test"])
def test_score_phase_rejects_an_unacknowledged_review_without_partial_scoring(review_db, phase):
    db, participant = review_db
    participant.current_step = phase
    rows = _question_rows(db, phase)
    assert len(rows) == 3
    for row in rows:
        question = db.get(Question, row["question_id"])
        _add_answer(db, participant, question, phase, correct=False)

    with pytest.raises(HTTPException) as error:
        asyncio.run(experiment.score_phase(db, participant.id, phase))
    assert error.value.status_code == 409
    db.expire_all()
    attempts = db.query(Attempt).filter_by(participant_id=participant.id, phase=phase).all()
    assert len(attempts) == 3
    assert all(attempt.is_correct is None and attempt.score is None for attempt in attempts)


def test_none_variant_key_is_safe_and_acknowledged_question_skips_review(review_db, monkeypatch):
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
    attempts_by_question[rows[0]["question_id"]].question_review_acknowledged_at = now()
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
    assert pending["term_slug"] == rows[1]["term_slug"]
    assert selected_attempt_ids == [
        attempts_by_question[rows[1]["question_id"]].id,
        attempts_by_question[rows[2]["question_id"]].id,
    ]
    assert attempts_by_question[rows[0]["question_id"]].id not in selected_attempt_ids
    assert acknowledged_term == rows[0]["term_slug"]
