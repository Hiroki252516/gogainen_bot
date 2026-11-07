from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from admin_client import AuthenticatedTestClient
from app import main as main_module
from app.db.session import SessionLocal
from app.models import Attempt, Base, Participant, Question, QuestionOption, Term, TutorSession, TutorTurn
from app.services import experiment
from app.services.hypothesis_metrics import participant_metrics
from app.services.split_assessment import (
    CORRECTION_DRAFTS,
    generation_scope,
    latest_failed_attempts,
    parse_split_variant,
    split_item_keys,
)
from split_api_support import acknowledge_all_question_reviews, complete_presurvey


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def learning_turn(monkeypatch):
    monkeypatch.setattr(main_module, "schedule_prefetch", lambda *args: None)
    monkeypatch.setattr(main_module.tutor_prefetch_registry, "prepare", lambda *args: None)
    client = AuthenticatedTestClient(main_module.app)
    ok(client.put("/api/admin/option-order", json={"mode": "randomized"}))
    pid = ok(client.post("/api/registrations", json={"assignment_code": "B", "consent_checked": True, "student_number": "GUARD-SYNTHETIC"}))["participant_id"]
    complete_presurvey(client, pid)
    questions = ok(client.get(f"/api/experiment/{pid}/pretest"))["questions"]
    for index, question in enumerate(questions):
        with SessionLocal() as db:
            option = db.query(QuestionOption).filter_by(question_id=question["question_id"], misconception_type="M1" if index == 0 else None).first()
            option_id = option.id
        ok(client.post("/api/attempts", json={"participant_id": pid, "question_id": question["question_id"], "selected_option_ids": [option_id]}))
    acknowledge_all_question_reviews(client, pid, "pretest")
    ok(client.post(f"/api/participants/{pid}/diagnose-pretest", json={}))
    session = ok(client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "llm_knowledge"}))
    turn = ok(client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}))
    return client, pid, questions, session["tutor_session_id"], turn


@pytest.mark.parametrize("value", [None, "", 1, [], {}, "pretest_v1", "legacy_q1", "pretest_v2_q1", "retest_v3_q1", "retest_v1_q0", "retest_v1_q3", "pretest_v1_q01", "pretest_v1_q1\n"])
def test_invalid_variant_is_rejected(value):
    with pytest.raises(HTTPException) as error:
        parse_split_variant(value)
    assert error.value.status_code == 503
    assert error.value.detail["error_code"] == "split_question_unavailable"


@pytest.mark.parametrize("round_key", ["pretest_v1", "retest_v1", "retest_v2"])
@pytest.mark.parametrize("number", [1, 2])
def test_valid_variants(round_key, number):
    assert parse_split_variant(f"{round_key}_q{number}") == (round_key, number)


@pytest.mark.parametrize("damage", ["practice_missing", "practice_list", "missing", "none", "empty", "list", "options_missing", "options_empty", "option_none", "option_label", "bad_role", "groups_empty", "group_none", "duplicate_option", "changed_body", "public_options_missing", "stage_meta", "variant_index"])
def test_damaged_snapshot_stops_before_grading_or_ai(learning_turn, monkeypatch, damage):
    client, pid, _, session_id, turn = learning_turn
    with SessionLocal() as db:
        saved = db.get(TutorTurn, turn["turn_id"])
        original = deepcopy(saved.practice_question_json)
        broken = deepcopy(original)
        if damage == "practice_missing":
            broken = None
        elif damage == "practice_list":
            broken = [original]
        elif damage == "missing":
            broken.pop("source_spec")
        elif damage in {"none", "empty", "list"}:
            broken["source_spec"] = {"none": None, "empty": {}, "list": []}[damage]
        elif damage == "options_missing":
            broken["source_spec"].pop("options")
        elif damage == "options_empty":
            broken["source_spec"]["options"] = []
        elif damage == "option_none":
            broken["source_spec"]["options"][0] = None
        elif damage == "option_label":
            broken["source_spec"]["options"][0].pop("label")
        elif damage == "bad_role":
            broken["source_spec"]["options"][0]["misconception_type"] = {}
        elif damage == "groups_empty":
            broken["source_spec"]["questions"] = []
        elif damage == "group_none":
            broken["source_spec"]["questions"][0] = None
        elif damage == "duplicate_option":
            broken["source_spec"]["options"][1] = deepcopy(broken["source_spec"]["options"][0])
        elif damage == "changed_body":
            broken["source_spec"]["options"][0]["body"] = "different"
        elif damage == "public_options_missing":
            broken.pop("options")
        elif damage == "stage_meta":
            broken["stage_meta"] = []
        elif damage == "variant_index":
            broken["learning_variant_index"] = "invalid"
        saved.practice_question_json = broken
        db.commit()
        before = (saved.learner_response, saved.grading_json, saved.ai_feedback)

    async def forbidden_ai_call(*args, **kwargs):
        pytest.fail("AI must not run when the saved question is invalid")

    monkeypatch.setattr(experiment, "_ai_call", forbidden_ai_call)
    selected = [q["options"][0]["option_id"] for q in turn["practice_question"]["questions"]]
    response = client.post(f"/api/tutor-turns/{turn['turn_id']}/respond", json={"selected_option_ids": selected}, headers={"Idempotency-Key": "damaged-snapshot"})
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["error_code"] == "split_confirmation_snapshot_unavailable"
    with SessionLocal() as db:
        saved = db.get(TutorTurn, turn["turn_id"])
        assert (saved.learner_response, saved.grading_json, saved.ai_feedback) == before
        assert saved.practice_question_json == broken
        assert db.get(TutorSession, session_id).ended_at is None
        assert db.get(Participant, pid).current_step == "learning_targets"


def test_metrics_ignore_unrelated_bad_variants_and_prefetch_questions(learning_turn):
    _, pid, questions, _, _ = learning_turn
    with SessionLocal() as db:
        source = db.get(Question, questions[0]["question_id"])
        unrelated = Question(term_id=source.term_id, phase="pretest", question_type="legacy", body="historical", construct_key="unrelated-history", variant_key="legacy_without_q")
        db.add(unrelated)
        db.flush()
        statements = []

        def capture(connection, cursor, statement, parameters, context, many):
            if statement.lstrip().upper().startswith("SELECT") and "FROM questions" in statement:
                statements.append(statement)

        connection = db.connection()
        event.listen(connection, "before_cursor_execute", capture)
        try:
            participant = db.get(Participant, pid)
            metrics = participant_metrics(db, participant)
            assert metrics["h1"]["pretest_score"] == 2 / 3
            assert len(statements) == 1
            assert "questions.id IN" in statements[0]
            statements.clear()
            experiment.recalculate_evaluation(db, pid)
            assert len(statements) == 2
        finally:
            event.remove(connection, "before_cursor_execute", capture)
            # recalculate_evaluation commits; remove the synthetic unrelated row.
            db.delete(unrelated)
            db.commit()


@pytest.mark.parametrize("variant", [None, "legacy", "pretest_v1_q3"])
def test_referenced_bad_variants_are_not_silently_skipped(learning_turn, variant):
    _, pid, questions, _, _ = learning_turn
    with SessionLocal() as db:
        question = db.get(Question, questions[0]["question_id"])
        question.variant_key = variant
        participant = db.get(Participant, pid)
        with pytest.raises(HTTPException) as error:
            participant_metrics(db, participant)
        assert error.value.status_code == 503
        with pytest.raises(HTTPException):
            latest_failed_attempts(db, participant, question.term_id)
        # No flush/commit of the intentionally malformed value.
        db.rollback()



@pytest.mark.parametrize("phase,round_key,variant", [
    ("final_test", "retest_1", "retest_v1"),
    ("retest", "retest_1", "retest_v1"),
    ("retest", "retest_2", "retest_v2"),
])
@pytest.mark.parametrize("clock_reversed", [False, True], ids=["same-timestamp", "clock-reversed"])
def test_latest_failed_attempts_uses_saved_round_before_timestamps(phase, round_key, variant, clock_reversed):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            participant = Participant(display_code="ROUND-ORDER", group_condition="control")
            term = Term(slug="llm_knowledge", label="LLM", display_order=1)
            db.add_all([participant, term])
            db.flush()
            at = datetime(2026, 11, 3, 1)
            previous = ("pretest", "test", "pretest_v1") if round_key == "retest_1" else ("retest", "retest_1", "retest_v1")
            batches = [
                (*previous, at, "ffffffff-ffff-ffff-ffff-", phase == "final_test"),
                (phase, round_key, variant, at - timedelta(hours=1) if clock_reversed else at, "00000000-0000-0000-0000-", False),
            ]
            latest_ids = []
            for batch_phase, saved_round, bank_variant, created, prefix, all_correct in batches:
                for number in (1, 2):
                    question = Question(term_id=term.id, phase="pretest" if batch_phase == "pretest" else "retest",
                                        question_type="split_single", body=f"{bank_variant}-q{number}",
                                        expected_answer="A", construct_key=f"round-order-{bank_variant}",
                                        variant_key=f"{bank_variant}_q{number}")
                    db.add(question)
                    db.flush()
                    is_latest = saved_round == round_key
                    correct = all_correct or number == (1 if is_latest else 2)
                    attempt = Attempt(id=f"{prefix}{number:012d}", participant_id=participant.id, term_id=term.id,
                                      question_id=question.id, phase=batch_phase, test_round=saved_round,
                                      is_correct=correct, misconception_type=None if correct else "M3",
                                      created_at=created, updated_at=created)
                    db.add(attempt)
                    if is_latest and not correct:
                        latest_ids.append(attempt.id)
            db.commit()
            # Older rows have later timestamps or larger IDs, but cannot replace the latest scored round.
            assert [row.id for row in latest_failed_attempts(db, participant, term.id)] == latest_ids
    finally:
        engine.dispose()


def test_missing_question_is_rejected_instead_of_using_a_default():
    class EmptyDB:
        def query(self, model):
            return self

        def filter(self, *args):
            return self

        def all(self):
            return []

    attempt = SimpleNamespace(question_id="missing", term_id="term", phase="pretest")
    with pytest.raises(HTTPException) as error:
        split_item_keys(EmptyDB(), [attempt])
    assert error.value.detail["error_code"] == "split_question_unavailable"


def test_missing_correction_is_an_explicit_failure(learning_turn, monkeypatch):
    _, pid, questions, _, _ = learning_turn
    monkeypatch.delitem(CORRECTION_DRAFTS, ("llm_knowledge", 1))
    with SessionLocal() as db:
        question = db.get(Question, questions[0]["question_id"])
        participant = db.get(Participant, pid)
        term = experiment._term_map(db)[question.term_id]
        with pytest.raises(HTTPException) as error:
            generation_scope(db, participant, term)
        assert error.value.detail["error_code"] == "split_correction_unavailable"
