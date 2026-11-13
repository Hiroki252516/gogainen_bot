"""Exercise fixed question selection and historical snapshot behavior."""
import csv
import io
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from admin_client import AuthenticatedTestClient
from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID
from app.db.session import SessionLocal
from app.main import app
from app.models import Attempt, Base, Participant, Question, RuntimeSetting, TutorTurn
from app.services import experiment
from app.services.first_question_only import enabled
from app.services.hypothesis_metrics import group_metrics, metrics_export_rows, participant_metrics
from split_api_support import complete_presurvey, create_trial, new_research_code, ok, select_roles


def answer_page(client, pid, phase, questions, *, wrong=False):
    page_id = str(uuid4())
    answers = []
    for index, question in enumerate(questions):
        role = "M1" if wrong and index == 0 else None
        roles = [role, role, role] if question.get("selection_mode") == "multiple" else [role]
        answers.append({"question_id": question["question_id"], "selected_option_ids": select_roles(question, roles)})
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
            assert all(
                set(r) in (
                    {"question_number", "selected_option", "is_correct"},
                    {"question_number", "selected_option", "is_correct", "selected_options"},
                )
                for r in pending["results"]
            )
            ack = f"/api/participants/{pid}/question-review-acknowledgements"
            ok(client.post(ack, json={"phase": phase, "term_slug": slug}))
            ok(client.post(ack, json={"phase": phase, "term_slug": slug}))
        else:
            assert pending is None
    endpoint = "diagnose-pretest" if phase == "pretest" else f"score-{phase.replace('_', '-')}"
    result = ok(client.post(f"/api/participants/{pid}/{endpoint}", json={}))
    return questions, result


def test_new_registration_uses_fixed_defaults_and_pretest_perfect_exits_to_survey():
    client = AuthenticatedTestClient(app)
    previous_settings = None
    with SessionLocal() as db:
        row = db.get(RuntimeSetting, 1)
        if row is None:
            row = RuntimeSetting(id=1)
            db.add(row)
        previous_settings = (row.show_pretest_results, row.show_question_reviews, row.first_question_only)
        row.show_pretest_results = True
        row.show_question_reviews = False
        row.first_question_only = False
        db.commit()
    participant_id = None
    try:
        for endpoint in ("pretest-result-display", "question-review-display", "first-question-only", "learning-material-glossary-mode"):
            assert TestClient(app).get(f"/api/admin/{endpoint}").status_code == 404
            assert client.get(f"/api/admin/{endpoint}").status_code == 404
            assert client.put(f"/api/admin/{endpoint}", json={"enabled": False}).status_code == 404
        participant_id = ok(client.post("/api/registrations", json={
            "assignment_code": "A", "consent_checked": True, "research_code": new_research_code()
        }))["participant_id"]
        complete_presurvey(client, participant_id)
        with SessionLocal() as db:
            participant = db.get(Participant, participant_id)
            assert participant.show_pretest_results is False
            assert participant.show_retest_results is False
            assert participant.show_question_reviews is True
            assert participant.first_question_only is True
            assert participant.experiment_spec_version == CURRENT_EXPERIMENT_SPEC_VERSION == 55
            assert participant.protocol_id == CURRENT_PROTOCOL_ID == "experiment-plan-2026-11-13-presurvey-ai-proficiency-examples-v1"
            rows = experiment.question_payloads(db, participant_id, "pretest")
            assert len(rows) == 4
            assert {row["term_slug"] for row in rows} == {
                "transformer", "llm_training_stages", "multi_agent_four_topic", "memory_process_four_topic"
            }
        _, scored = answer_test(client, participant_id, "pretest", 4, reviews=True)
        assert scored["review_required"] is False
        assert scored["next_step"] == "survey"
        assert scored["next_url"] == "/survey"
        assert client.get(f"/api/experiment/{participant_id}/final-test").status_code == 409
        logs = ok(client.get(f"/api/admin/participants/{participant_id}/logs"))["participant"]
        assert logs["show_pretest_results"] is False
        assert logs["show_retest_results"] is False
        assert logs["show_question_reviews"] is True
        assert logs["first_question_only"] is True
        assert logs["learning_material_glossary_mode"] == "integrated_material"
        participant_rows = csv.DictReader(io.StringIO(client.get("/api/admin/export/participants.csv").text))
        exported = next(row for row in participant_rows if row["id"] == participant_id)
        assert exported["show_pretest_results"] == "False"
        assert exported["show_retest_results"] == "False"
        assert exported["show_question_reviews"] == "True"
        assert exported["first_question_only"] == "True"
        assert exported["learning_material_glossary_mode"] == "integrated_material"
    finally:
        if participant_id:
            ok(client.delete(f"/api/admin/participants/{participant_id}"))
        with SessionLocal() as db:
            row = db.get(RuntimeSetting, 1)
            if row and previous_settings is not None:
                row.show_pretest_results, row.show_question_reviews, row.first_question_only = previous_settings
                db.commit()


@pytest.mark.parametrize("first_only", [False, True])
@pytest.mark.parametrize("reviews", [False, True])
def test_registration_snapshot_pretest_perfect_exit_and_disabled_question_rejection(first_only, reviews):
    count = 3 if first_only else 6
    with create_trial(
        "A", "debug_fixed", first_question_only=first_only,
        show_pretest_results=False, show_retest_results=False, show_question_reviews=reviews,
    ) as (client, pid):
            with SessionLocal() as db:
                participant = db.get(Participant, pid)
                assert participant.first_question_only is first_only
                rows = experiment.question_payloads(db, pid, "pretest")
                assert len(rows) == count
                if first_only:
                    q1 = db.get(Question, rows[0]["question_id"])
                    q2 = db.query(Question).filter_by(term_id=q1.term_id, construct_key=q1.construct_key, variant_key="pretest_v1_q2").one()
                    q2id = q2.id
            if first_only:
                assert client.post("/api/attempts", json={"participant_id": pid, "phase": "pretest", "question_id": q2id, "selected_option_ids": []}).status_code == 409
            _, scored = answer_test(client, pid, "pretest", count, reviews=reviews)
            assert scored["next_step"] == "survey"
            assert scored["next_url"] == "/survey"
            assert client.get(f"/api/experiment/{pid}/final-test").status_code == 409
            with SessionLocal() as db:
                participant = db.get(Participant, pid)
                metric = participant_metrics(db, participant)
                assert metric["questions_per_test"] == count
                assert metric["first_question_only"] is first_only
                assert metric["route"] == "pretest_perfect_early_exit"
                assert metric["h1"]["value"] is None
                assert metric["h3"]["status"] == "not_applicable_pretest_mastery"
                assert "h5" not in metric and "h6" not in metric
                assert participant.current_step == "survey"
                assert db.query(Attempt).filter_by(participant_id=pid).count() == count
                assert experiment.participant_logs(db, pid)["participant"]["first_question_only"] is first_only


@pytest.mark.parametrize("first_only", [False, True])
def test_learning_snapshot_and_both_retest_rounds(first_only):
    count = 3 if first_only else 6
    with create_trial(
        "B", "randomized", first_question_only=first_only,
        show_pretest_results=False, show_retest_results=False,
    ) as (client, pid):
            questions, _ = answer_test(client, pid, "pretest", count, wrong=True)
            failed = questions[0]
            session = ok(client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": failed["term_slug"]}))
            turn = ok(client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}))
            practice = turn["practice_question"]
            assert practice["questions"] == [{"question_id": failed["question_id"], "body": failed["body"], "options": failed["options"]}]
            ok(client.post(f"/api/tutor-turns/{turn['turn_id']}/respond",
                           json={"selected_option_ids": select_roles(failed, [None])}))
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
                assert set(metric["h4"]) == {"status", "items", "viewed", "survey_present"}
                assert "value" not in metric["h4"] and "denominator" not in metric["h4"]
                assert metric["h3"]["attained"] is True
                assert metric["h3"]["first_mastery_round"] == 2
                assert "first_mastery_round" not in metric["h2"]
                assert "h5" not in metric and "h6" not in metric
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
        connection.execute(text("ALTER TABLE participants DROP COLUMN test_content_mode"))
        connection.execute(text("ALTER TABLE runtime_settings DROP COLUMN first_question_only"))
        connection.execute(text("ALTER TABLE runtime_settings DROP COLUMN test_content_mode"))
    database.init_db()
    database.init_db()
    for table in ("participants", "runtime_settings"):
        columns = {column["name"] for column in inspect(engine).get_columns(table)}
        assert "first_question_only" in columns
        assert "test_content_mode" in columns
    with Session(engine) as db:
        seed_database(db)
        participant = db.query(Participant).filter_by(display_code="Q1-MIGRATION-OLD").one()
        assert participant.first_question_only is None
        assert participant.test_content_mode is None
        assert participant.current_step == "finish"
        assert db.get(RuntimeSetting, 1).first_question_only is None
        assert db.get(RuntimeSetting, 1).test_content_mode is None
        assert db.get(RuntimeSetting, 1).show_question_reviews is False
        assert before == [(q.id, q.body, q.variant_key) for q in db.query(Question).order_by(Question.id)]
    engine.dispose()


def test_metric_strata_and_fixed_csv_headers_identify_each_condition():
    rows = []
    for first_only in (False, True):
        with create_trial(
            "A" if first_only else "B", "debug_fixed", first_question_only=first_only,
            show_pretest_results=False, show_retest_results=False,
        ) as (client, pid):
                count = 3 if first_only else 6
                answer_test(client, pid, "pretest", count)
                with SessionLocal() as db:
                    metric = participant_metrics(db, db.get(Participant, pid))
                    assert metric["route"] == "pretest_perfect_early_exit"
                    assert metric["h1"]["value"] is None
                    rows.append(metric)
    result = group_metrics(rows)
    assert result["groups"] == []
    assert len(result["strata"]) == 2
    for stratum in result["strata"]:
        assert sum(g["participant_count"] for g in stratum["groups"]) == 1
        assert stratum["differences_proposed_minus_control"]["h1"] is None
    import json
    from app.services.hypothesis_metrics import METRICS_CSV_COLUMNS
    for grouped in (False, True):
        records = metrics_export_rows(rows, grouped=grouped)
        assert {json.loads(r["details_json"])["first_question_only"] for r in records} == {False, True}
        assert all(set(r) <= set(METRICS_CSV_COLUMNS) for r in records)
        assert all(json.loads(r["details_json"])["questions_per_test"] in (3, 6) for r in records)
