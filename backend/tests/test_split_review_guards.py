import asyncio
from copy import deepcopy
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import main as main_module
from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID
from app.ai.mock_backend import MockAIBackend
from app.ai.teaching_contract import tutoring_material_length_metrics, validate_teaching_contract
from app.models import Attempt, Base, LearnerState, Participant, Question, Term, TutorSession, TutorTurn
from app.seed.seed_questions import seed_database
from app.services import experiment
from app.services.split_assessment import generation_scope, latest_failed_attempts, learning_spec
from app.db.session import SessionLocal
from app.db import session as database
from split_api_support import answer_test, create_trial, ok


@pytest.fixture
def history_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        seed_database(db)
        yield db
    engine.dispose()


def build_history(db, first_post="retest", last_round=2, latest_correct=False):
    participant = Participant(
        display_code="ROUND-GUARD", group_condition="proposed",
        experiment_spec_version=27, protocol_id="experiment-plan-2026-10-29-split-tests-v1",
    )
    db.add(participant)
    db.flush()
    term = db.query(Term).filter_by(slug="llm_knowledge").one()
    attempts = []
    for round_number in range(last_round + 1):
        phase = "pretest" if round_number == 0 else first_post if round_number == 1 else "retest"
        variant = "pretest_v1" if round_number == 0 else f"retest_v{round_number}"
        for number in (1, 2):
            question = db.query(Question).filter_by(term_id=term.id, variant_key=f"{variant}_q{number}").one()
            correct = number == 2 or (latest_correct and round_number == last_round) or (round_number == 0 and first_post == "final_test")
            attempt = Attempt(
                participant_id=participant.id, term_id=term.id, question_id=question.id, phase=phase,
                test_round="test" if round_number == 0 else f"retest_{round_number}", attempt_index=1,
                is_correct=correct, misconception_type=None if correct else "M1",
                created_at=datetime(2026, 10, 29) + timedelta(minutes=round_number * 10 + number),
            )
            db.add(attempt)
            attempts.append(attempt)
    db.commit()
    return participant, term, attempts


@pytest.mark.parametrize("first_post", ["retest", "final_test"])
@pytest.mark.parametrize("last_round", [1, 2])
@pytest.mark.parametrize("latest_correct", [False, True])
def test_valid_rounds_select_only_latest_failed_item(history_db, first_post, last_round, latest_correct):
    db = history_db
    participant, term, attempts = build_history(db, first_post, last_round, latest_correct)
    assert {a.attempt_index for a in attempts} == {1}
    result = latest_failed_attempts(db, participant, term.id)
    assert [a.id for a in result] == ([] if latest_correct else [attempts[-2].id])
    assert not db.dirty


@pytest.mark.parametrize("round_number", [0, 1, 2])
@pytest.mark.parametrize("bad_round", [None, "", "invalid", "wrong"])
def test_missing_or_mismatched_round_is_rejected_without_repair(history_db, round_number, bad_round):
    db = history_db
    participant, term, attempts = build_history(db)
    damaged = attempts[round_number * 2 + 1]  # Even a correct answer must be checked.
    damaged.test_round = ("retest_1" if round_number == 0 else "test") if bad_round == "wrong" else bad_round
    db.commit()
    before = deepcopy(db.execute(select(Attempt.__table__)).mappings().all())
    for operation in (latest_failed_attempts, learning_spec, generation_scope):
        with pytest.raises(HTTPException) as error:
            operation(db, participant, term.id if operation is latest_failed_attempts else term)
        assert error.value.status_code == 503
        assert error.value.detail["error_code"] == "split_test_round_unavailable"
    assert db.execute(select(Attempt.__table__)).mappings().all() == before
    assert not db.dirty


def test_missing_rounds_do_not_merge_two_retests(history_db):
    db = history_db
    participant, term, attempts = build_history(db)
    for attempt in attempts[2:]:
        attempt.test_round = None
    db.commit()
    with pytest.raises(HTTPException) as error:
        latest_failed_attempts(db, participant, term.id)
    assert error.value.detail["error_code"] == "split_test_round_unavailable"
    assert all(a.test_round is None and a.attempt_index == 1 for a in attempts[2:])


def test_final_test_cannot_claim_the_second_variant(history_db):
    db = history_db
    participant, term, attempts = build_history(db)
    for attempt in attempts[-2:]:
        attempt.phase = "final_test"
    db.commit()
    with pytest.raises(HTTPException) as error:
        latest_failed_attempts(db, participant, term.id)
    assert error.value.detail["error_code"] == "split_test_round_unavailable"


def test_pending_and_other_participant_rounds_are_not_used(history_db):
    db = history_db
    participant, term, attempts = build_history(db)
    other = Participant(display_code="UNRELATED-ROUND", group_condition="control")
    db.add(other)
    db.flush()
    for pid, correct in ((participant.id, None), (other.id, False)):
        db.add(Attempt(participant_id=pid, term_id=term.id, question_id=attempts[-1].question_id,
                       phase="retest", test_round=None, attempt_index=1, is_correct=correct,
                       created_at=datetime(2026, 10, 30)))
    db.commit()
    assert [a.id for a in latest_failed_attempts(db, participant, term.id)] == [attempts[-2].id]


@pytest.mark.parametrize("first_post", ["retest", "final_test"])
@pytest.mark.parametrize("missing", [None, ""])
def test_startup_does_not_guess_or_rewrite_split_rounds(history_db, monkeypatch, first_post, missing):
    db = history_db
    participant, term, attempts = build_history(db, first_post)
    for attempt in attempts:
        attempt.test_round = missing
    db.commit()
    before = deepcopy(db.execute(select(Attempt.__table__)).mappings().all())
    monkeypatch.setattr(database, "engine", db.get_bind())
    database.init_db()
    database.init_db()
    db.expire_all()
    assert db.execute(select(Attempt.__table__)).mappings().all() == before
    with pytest.raises(HTTPException) as error:
        latest_failed_attempts(db, participant, term.id)
    assert error.value.detail["error_code"] == "split_test_round_unavailable"


@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("bad_round", [None, "", "retest_1"])
def test_bad_round_stops_generation_before_ai_and_allows_retry(monkeypatch, group, bad_round):
    monkeypatch.setattr(main_module, "schedule_prefetch", lambda *args: None)
    monkeypatch.setattr(main_module.tutor_prefetch_registry, "prepare", lambda *args: None)
    with create_trial(group, "debug_fixed") as (client, pid):
        questions, _ = answer_test(client, pid, "pretest", "llm_knowledge", ("M1", "M3"))
        session = ok(client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "llm_knowledge"}))
        sid = session["tutor_session_id"]
        with SessionLocal() as db:
            damaged = db.query(Attempt).filter_by(participant_id=pid, question_id=questions[1]["question_id"]).one()
            damaged.test_round = bad_round
            attempt_id = damaged.id
            db.commit()

        def snapshot():
            with SessionLocal() as db:
                records = {}
                for model in (Participant, Attempt, LearnerState, TutorSession, TutorTurn):
                    column = model.id if model is Participant else model.tutor_session_id if model is TutorTurn else model.participant_id
                    records[model.__tablename__] = deepcopy(db.execute(select(model.__table__).where(column == (sid if model is TutorTurn else pid)).order_by(model.id)).mappings().all())
                return records

        async def forbidden_ai(*args, **kwargs):
            pytest.fail("inconsistent rounds must not reach AI generation")

        before = snapshot()
        url = f"/api/tutor-sessions/{sid}/turns"
        headers = {"Idempotency-Key": "round-guard-generation"}
        with monkeypatch.context() as patch:
            patch.setattr(experiment, "_ai_call", forbidden_ai)
            for _ in range(2):
                response = client.post(url, json={}, headers=headers)
                assert response.status_code == 503, response.text
                assert response.json()["detail"]["error_code"] == "split_test_round_unavailable"
                assert snapshot() == before
        with SessionLocal() as db:
            db.get(Attempt, attempt_id).test_round = "test"
            db.commit()
        restored = ok(client.post(url, json={}, headers=headers))
        assert len(restored["practice_question"]["questions"]) == 2


def mock_payload(kind):
    primary = {
        "claim_id": "primary", "misconception_type": kind,
        "observed_claim": "Wrong primary claim", "corrected_claim": "Correct mechanism",
        "mechanism_explanation": "How the mechanism works", "contrast_example": "A contrasting example",
        "wrong_category": "Wrong primary claim", "correct_category": "Correct category",
        "boundary_criterion": "How to distinguish categories",
    }
    secondary = {**primary, "claim_id": "secondary", "observed_claim": "Wrong secondary claim"}
    return {
        "group_condition": "proposed", "active_misconception_type": kind,
        "term": {"label": "Memory", "description": "Records are saved, retrieved and updated."},
        "pretest_target": primary, "pretest_targets": [primary, secondary],
        "learning_scope": {"topics": ["Saving", "Updating"], "selected_errors": []},
    }


@pytest.mark.parametrize("kind", ["M1", "M3"])
@pytest.mark.parametrize("damage", [
    "container_dict", "container_string", "container_int", "container_false",
    "entry_none", "entry_string", "entry_list",
    "missing_observed", "none_observed", "blank_observed", "int_observed",
    "missing_id", "none_id", "blank_id", "int_id",
])
def test_mock_rejects_invalid_scoped_targets_before_building_material(monkeypatch, kind, damage):
    payload = mock_payload(kind)
    if damage.startswith("container_"):
        payload["pretest_targets"] = {"container_dict": {}, "container_string": "invalid", "container_int": 1, "container_false": False}[damage]
    elif damage.startswith("entry_"):
        payload["pretest_targets"][1] = {"entry_none": None, "entry_string": "invalid", "entry_list": []}[damage]
    else:
        field = "observed_claim" if damage.endswith("observed") else "claim_id"
        if damage.startswith("missing"):
            payload["pretest_targets"][1].pop(field)
        else:
            payload["pretest_targets"][1][field] = None if damage.startswith("none") else "  " if damage.startswith("blank") else 1
    before = deepcopy(payload)

    def forbidden_material(*args, **kwargs):
        pytest.fail("invalid targets must be rejected before generating evidence")

    monkeypatch.setattr("app.ai.mock_backend.mock_mandatory_elements", forbidden_material)
    with pytest.raises(ValueError, match=r"pretest_targets"):
        asyncio.run(MockAIBackend().generate_tutoring_turn(payload))
    assert payload == before


@pytest.mark.parametrize("kind,mixed", [("M1", False), ("M3", False), ("M3", True)])
def test_valid_mock_scope_keeps_both_claims_and_contract(kind, mixed):
    payload = mock_payload(kind)
    if mixed:
        payload["pretest_targets"][1]["misconception_type"] = "M1"
    before = deepcopy(payload)
    result = asyncio.run(MockAIBackend().generate_tutoring_turn(payload))
    assert result["teaching_contract"]["addressed_claim_ids"] == ["primary", "secondary"]
    assert all(item["observed_claim"] in result["tutor_message"] for item in payload["pretest_targets"])
    validation = validate_teaching_contract(result, kind, payload, "Memory")
    assert validation["valid"], validation
    assert tutoring_material_length_metrics(result)["target_character_count"] == 800
    assert payload == before


@pytest.mark.parametrize("group,kind", [("control", "M1"), ("proposed", "unknown")])
def test_ignored_diagnostics_do_not_become_scoped_mock_targets(group, kind):
    payload = mock_payload(kind)
    payload["group_condition"] = group
    payload["pretest_targets"] = [None, "invalid", {}]
    result = asyncio.run(MockAIBackend().generate_tutoring_turn(payload))
    assert "Wrong primary claim" not in result["tutor_message"]
    if group == "control":
        assert "teaching_contract" not in result
    else:
        assert result["teaching_contract"]["addressed_claim_ids"] == []
