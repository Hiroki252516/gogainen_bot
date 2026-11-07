"""Exercise the fixed V6 Q1 registration snapshot through saved test flows."""
from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from admin_client import AuthenticatedTestClient
from app.db.session import SessionLocal
from app.main import app
from app.models import Attempt, Base, Participant, Question, RuntimeSetting, TutorTurn
from app.services import experiment
from app.services.first_question_only import current_setting, enabled, save_setting
from app.services.hypothesis_metrics import group_metrics, metrics_export_rows, participant_metrics
from split_api_support import create_trial, ok, select_roles

ENDPOINT = "/api/admin/first-question-only"


@contextmanager
def condition(first_only, reviews=True):
    client = AuthenticatedTestClient(app)
    previous = ok(client.get(ENDPOINT))["enabled"]
    previous_reviews = ok(client.get("/api/admin/question-review-display"))["enabled"]
    ok(client.put(ENDPOINT, json={"enabled": first_only}))
    ok(client.put("/api/admin/question-review-display", json={"enabled": reviews}))
    try:
        yield client
    finally:
        ok(client.put(ENDPOINT, json={"enabled": previous}))
        ok(client.put("/api/admin/question-review-display", json={"enabled": previous_reviews}))


def answer_page(client, pid, phase, questions, *, wrong=False):
    page_id = str(uuid4())
    answers = [{"question_id": q["question_id"], "selected_option_ids": select_roles(q, ["M1" if wrong and index == 0 else None])}
               for index, q in enumerate(questions)]
    payload = {"participant_id": pid, "phase": phase, "term_slug": questions[0]["term_slug"],
               "test_round": questions[0]["test_round"], "page_id": page_id, "answers": answers,
               "question_shown_at": "2026-11-03T00:00:00Z", "answered_at": "2026-11-03T00:00:10Z",
               "elapsed_time_sec": 10}
    headers = {"Idempotency-Key": page_id}
    response = ok(client.post("/api/attempts/term-page", json=payload, headers=headers))
    assert response["saved_question_count"] == len(questions)
    assert ok(client.post("/api/attempts/term-page", json=payload, headers=headers)) == response


def answer_test(client, pid, phase, count, *, wrong=False, reviews=True):
    path = f"/api/experiment/{pid}/{phase.replace('_', '-')}"
    data = ok(client.get(path))
    questions = data["questions"]
    assert len(questions) == count
    assert data["test_page_mode"] == "per_term"
    for index, slug in enumerate(dict.fromkeys(q["term_slug"] for q in questions)):
        page = [q for q in questions if q["term_slug"] == slug]
        answer_page(client, pid, phase, page, wrong=wrong and index == 0)
        pending = ok(client.get(path))["pending_question_review"]
        if reviews:
            assert pending["term_slug"] == slug
            assert len(pending["results"]) == count // 3
            assert [r["question_number"] for r in pending["results"]] == list(range(1, count // 3 + 1))
            assert all(set(r) == {"question_number", "selected_option", "is_correct"} for r in pending["results"])
            ack = f"/api/participants/{pid}/question-review-acknowledgements"
            ok(client.post(ack, json={"phase": phase, "term_slug": slug}))
            ok(client.post(ack, json={"phase": phase, "term_slug": slug}))
        else:
            assert pending is None
    endpoint = "diagnose-pretest" if phase == "pretest" else f"score-{phase.replace('_', '-')}"
    result = ok(client.post(f"/api/participants/{pid}/{endpoint}", json={}))
    return questions, result


def test_setting_defaults_on_is_strict_and_requires_admin(tmp_path):
    unauthorized = TestClient(app)
    assert unauthorized.get(ENDPOINT).status_code == 401
    assert unauthorized.put(ENDPOINT, json={"enabled": True}).status_code == 401
    with condition(True) as client:
        assert client.get(ENDPOINT).headers["cache-control"] == "no-store"
        for value in (1, "true", None):
            assert client.put(ENDPOINT, json={"enabled": value}).status_code == 422
        assert client.put(ENDPOINT, json={"enabled": True, "extra": True}).status_code == 422
        assert client.put(ENDPOINT, json={"enabled": False}).status_code == 409
    engine = create_engine(f"sqlite:///{tmp_path / 'setting.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        assert current_setting(db) is True
        db.add(RuntimeSetting(id=1))
        db.commit()
        assert current_setting(db) is True
        legacy = Participant(display_code="Q1-NULL", group_condition="control")
        db.add(legacy)
        db.commit()
        assert enabled(legacy) is False
        save_setting(db, True)
        assert legacy.first_question_only is None
    with Session(engine) as db:
        assert current_setting(db) is True
        with pytest.raises(HTTPException) as error:
            save_setting(db, False)
        assert error.value.status_code == 409
        assert current_setting(db) is True
    engine.dispose()


@pytest.mark.parametrize("reviews", [False, True])
def test_registration_snapshot_final_test_and_v6_only_has_question_one(reviews):
    count = 3
    with condition(True, reviews):
        with create_trial("A", "debug_fixed") as (client, pid):
            assert client.put(ENDPOINT, json={"enabled": False}).status_code == 409
            with SessionLocal() as db:
                participant = db.get(Participant, pid)
                assert participant.first_question_only is True
                rows = experiment.question_payloads(db, pid, "pretest")
                assert len(rows) == count
                assert all(db.get(Question, row["question_id"]).variant_key.endswith("_q1") for row in rows)
                q23 = [f"{round_key}_q{number}" for round_key in ("pretest_v1", "retest_v1", "retest_v2") for number in (2, 3)]
                assert db.query(Question).filter(Question.construct_key.like("%split-actions-v6"), Question.variant_key.in_(q23)).count() == 0
            answer_test(client, pid, "pretest", count, reviews=reviews)
            answer_test(client, pid, "final_test", count, reviews=reviews)
            with SessionLocal() as db:
                participant = db.get(Participant, pid)
                metric = participant_metrics(db, participant)
                assert metric["questions_per_test"] == count
                assert metric["first_question_only"] is True
                assert metric["h1"]["value"] == 0
                assert metric["h6"]["attained"] is True
                assert participant.current_step == "survey"
                assert db.query(Attempt).filter_by(participant_id=pid).count() == count * 2
                assert experiment.participant_logs(db, pid)["participant"]["first_question_only"] is True


def test_learning_snapshot_and_both_retest_rounds():
    count = 3
    with condition(True):
        with create_trial("B", "randomized") as (client, pid):
            questions, _ = answer_test(client, pid, "pretest", count, wrong=True)
            failed = questions[0]
            session = ok(client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": failed["term_slug"]}))
            turn = ok(client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}))
            practice = turn["practice_question"]
            assert practice["questions"] == [{"question_id": failed["question_id"], "body": failed["body"], "options": failed["options"]}]
            ok(client.post(f"/api/tutor-turns/{turn['turn_id']}/respond", json={"selected_option_ids": select_roles(failed, [None])}))
            with SessionLocal() as db:
                saved = db.get(TutorTurn, turn["turn_id"])
                assert len(saved.grading_json["question_results"]) == 1
            answer_test(client, pid, "retest", count, wrong=True)
            ok(client.post(f"/api/participants/{pid}/give-up-learning", json={}))
            questions, _ = answer_test(client, pid, "retest", count)
            assert {q["test_round"] for q in questions} == {"retest_2"}
            with SessionLocal() as db:
                metric = participant_metrics(db, db.get(Participant, pid))
                assert metric["h1"]["value"] == 0
                assert metric["h1"]["pretest_score"] == pytest.approx((count - 1) / count)
                assert metric["rounds"][-1]["gain_pt"] == pytest.approx(100 / count)
                assert metric["h4"]["denominator"] == 1
                assert metric["h4"]["value"] == 1
                assert metric["h6"]["attained"] is True
                assert metric["h2"]["first_mastery_round"] == 2
                assert len(metric["rounds"]) == 2
                assert all(r["complete"] for r in metric["rounds"])
                logs = experiment.participant_logs(db, pid)
                assert all(r["question_count"] == count and r["scoring_unit"] == "subquestion" for r in logs["latest_evaluation_summary"]["score_timeline"]["rounds"])


def test_additive_migration_keeps_legacy_rows_null_and_seeded_content(tmp_path, monkeypatch):
    from sqlalchemy import inspect, text
    from app.db import session as database
    from app.seed.seed_questions import seed_database

    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    monkeypatch.setattr(database, "engine", engine)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_database(db)
        db.add(Participant(display_code="Q1-MIGRATION-OLD", group_condition="control", current_step="finish"))
        db.add(RuntimeSetting(id=1, show_question_reviews=False))
        db.commit()
        before = [(q.id, q.body, q.variant_key) for q in db.query(Question).order_by(Question.id)]
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE participants DROP COLUMN first_question_only"))
        connection.execute(text("ALTER TABLE runtime_settings DROP COLUMN first_question_only"))
    database.init_db()
    database.init_db()
    for table in ("participants", "runtime_settings"):
        assert "first_question_only" in {column["name"] for column in inspect(engine).get_columns(table)}
    with Session(engine) as db:
        seed_database(db)
        participant = db.query(Participant).filter_by(display_code="Q1-MIGRATION-OLD").one()
        assert participant.first_question_only is None
        assert participant.current_step == "finish"
        assert db.get(RuntimeSetting, 1).first_question_only is None
        assert db.get(RuntimeSetting, 1).show_question_reviews is False
        assert before == [(q.id, q.body, q.variant_key) for q in db.query(Question).order_by(Question.id)]
    engine.dispose()


def test_fixed_q1_stratum_and_csv_headers_identify_the_condition():
    rows = []
    for assignment in ("A", "B"):
        with condition(True):
            with create_trial(assignment, "debug_fixed") as (client, pid):
                answer_test(client, pid, "pretest", 3)
                answer_test(client, pid, "final_test", 3)
                with SessionLocal() as db:
                    rows.append(participant_metrics(db, db.get(Participant, pid)))
    result = group_metrics(rows)
    assert len(result["groups"]) == 2
    assert not result.get("strata")
    import json
    from app.services.hypothesis_metrics import METRICS_CSV_COLUMNS
    for grouped in (False, True):
        records = metrics_export_rows(rows, grouped=grouped)
        assert {json.loads(r["details_json"])["first_question_only"] for r in records} == {True}
        assert all(set(r) <= set(METRICS_CSV_COLUMNS) for r in records)
        assert all(json.loads(r["details_json"])["questions_per_test"] == 3 for r in records)
