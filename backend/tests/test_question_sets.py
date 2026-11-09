from __future__ import annotations

import pytest
from collections import Counter
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from admin_client import AuthenticatedTestClient
from app.core.question_sets import (
    ASSESSMENT_BANK_VERSIONS,
    ASSESSMENT_MODE_BANK_VERSIONS,
    HISTORICAL_ASSESSMENT_BANK_VERSIONS,
    LEARNING_CONTENT_VERSIONS,
    STANDARD,
    assessment_bank_for_participant,
)
from app.db.session import get_db
from app.main import app
from app.models import Attempt, Base, Participant, Question, QuestionOption, Term
from app.seed.content_loader import ACTIVE_TERM_SLUGS, assessment_question_spec, load_content, load_learning_content
from app.seed.seed_questions import seed_database
from app.services.hypothesis_metrics import group_metrics, metrics_export_rows
from app.services.split_assessment import learning_spec, split_bank
from split_api_support import complete_presurvey


@pytest.fixture
def isolated(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'question-modes.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    with factory() as db:
        seed_database(db)

    def dependency():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = dependency
    try:
        yield AuthenticatedTestClient(app), factory, engine
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def test_mode_banks_are_separate_and_have_expected_question_roles(isolated):
    _client, factory, engine = isolated
    assert ASSESSMENT_BANK_VERSIONS == {STANDARD: "split-actions-v5"}
    assert ASSESSMENT_MODE_BANK_VERSIONS == {
        "application": "split-actions-v5",
        "basic_understanding": "split-actions-basic-v1",
    }
    assert LEARNING_CONTENT_VERSIONS == {STANDARD: 15}
    assert all(set(banks) == {STANDARD} for banks in HISTORICAL_ASSESSMENT_BANK_VERSIONS.values())
    assert len(load_content()["terms"]) == len(ACTIVE_TERM_SLUGS)
    assert len(load_learning_content()["terms"]) == len(ACTIVE_TERM_SLUGS)
    for slug in ACTIVE_TERM_SLUGS:
        assert assessment_question_spec(slug, "pretest")["body"]
    basic = split_bank("split-actions-basic-v1")
    assert set(basic) == {"pretest_v1", "retest_v1", "retest_v2"}
    for round_key, terms in basic.items():
        assert set(terms) == set(ACTIVE_TERM_SLUGS)
        for section in terms.values():
            assert section["scenario"] == ""
            assert section["presentation"] == "standalone"
            assert [question["number"] for question in section["questions"]] == [1]
            for question in section["questions"]:
                assert Counter(choice["role"] for choice in question["choices"]) == Counter(
                    {"correct": 1, "M1": 2, "M3": 2, "unknown": 1}
                )
                assert len({choice["body"] for choice in question["choices"]}) == 6

    with factory() as db:
        assert db.query(Question).count() == 27
        assert db.query(QuestionOption).count() == 162
        for mode, bank in ASSESSMENT_MODE_BANK_VERSIONS.items():
            questions = db.query(Question).filter(Question.construct_key.contains(bank)).all()
            expected_questions = 18 if mode == "application" else 9
            assert len(questions) == expected_questions
            assert all(question.construct_key.endswith(bank) for question in questions)
            for question in questions:
                choices = db.query(QuestionOption).filter_by(question_id=question.id).all()
                assert Counter(
                    "correct" if choice.is_correct else choice.misconception_type for choice in choices
                ) == Counter({"correct": 1, "M1": 2, "M3": 2, "unknown": 1})
    assert "test_content_mode" in {column["name"] for column in inspect(engine).get_columns("participants")}
    assert "test_content_mode" in {column["name"] for column in inspect(engine).get_columns("runtime_settings")}


def test_old_participant_without_mode_keeps_application_bank():
    class ParticipantSnapshot:
        experiment_spec_version = 42
        test_content_mode = None

    assert assessment_bank_for_participant(ParticipantSnapshot()) == "split-actions-v5"


def test_question_set_admin_api_is_removed_and_legacy_aggregate_filters_reject(isolated):
    client, _factory, _engine = isolated
    assert client.get("/api/admin/question-set").status_code == 404
    assert client.put("/api/admin/question-set", json={"mode": "standard"}).status_code == 404
    for path in (
        "/api/admin/evaluation-summary?question_set_mode=easy",
        "/api/admin/logs/overview?question_set_mode=easy",
        "/api/admin/logs/overview.csv?question_set_mode=easy",
        "/api/admin/logs/overview_excel.csv?question_set_mode=easy",
        "/api/admin/logs/overview.xlsx?question_set_mode=easy",
        "/api/admin/export/hypothesis_metrics.csv?question_set_mode=easy",
        "/api/admin/export/hypothesis_group_summary.xlsx?question_set_mode=easy",
    ):
        assert client.get(path).status_code == 422


def test_mode_setting_is_authenticated_and_snapshotted_for_new_participants(isolated):
    client, factory, _engine = isolated
    unauthenticated = TestClient(app)
    assert unauthenticated.get("/api/admin/test-content-mode").status_code == 401

    current = client.get("/api/admin/test-content-mode")
    assert current.status_code == 200
    assert current.json() == {
        "mode": "application",
        "label": "現行版（場面応用）",
        "applies_to": "new_participants_only",
    }
    assert client.put("/api/admin/test-content-mode", json={"mode": "invalid"}).status_code == 422
    assert client.put("/api/admin/test-content-mode", json={"mode": "application", "extra": True}).status_code == 422

    created_ids = []

    def create_participant(student_number: str) -> str:
        response = client.post("/api/participants", json={
            "assignment_code": "A", "consent_checked": True, "student_number": student_number,
        })
        assert response.status_code == 200, response.text
        participant_id = response.json()["participant_id"]
        created_ids.append(participant_id)
        complete_presurvey(client, participant_id)
        return participant_id

    try:
        saved = client.put("/api/admin/test-content-mode", json={"mode": "basic_understanding"})
        assert saved.status_code == 200
        assert saved.json()["mode"] == "basic_understanding"
        basic_id = create_participant("BASIC-MODE-SNAPSHOT-TEST")
        with factory() as db:
            db.get(Participant, basic_id).first_question_only = False
            db.commit()
        basic_questions = client.get(f"/api/experiment/{basic_id}/pretest").json()["questions"]
        assert len(basic_questions) == 3
        assert all(len(question["options"]) == 6 for question in basic_questions)
        assert "RAGとモデルの重み" in basic_questions[0]["body"]

        saved = client.put("/api/admin/test-content-mode", json={"mode": "application"})
        assert saved.status_code == 200
        application_id = create_participant("APPLICATION-MODE-SNAPSHOT-TEST")
        application_questions = client.get(f"/api/experiment/{application_id}/pretest").json()["questions"]
        assert len(application_questions) == 3
        assert "最新の取扱説明書を参照する方法" in application_questions[0]["body"]

        # Changing the runtime setting does not change the saved participant bank.
        assert client.get(f"/api/experiment/{basic_id}/pretest").json()["questions"] == basic_questions
        with factory() as db:
            basic_participant = db.get(Participant, basic_id)
            application_participant = db.get(Participant, application_id)
            assert basic_participant.test_content_mode == "basic_understanding"
            assert application_participant.test_content_mode == "application"
            assert basic_participant.learning_content_version == 15
            assert not hasattr(basic_participant, "question_set_mode")
        participants = client.get("/api/admin/participants").json()["participants"]
        by_id = {row["participant_id"]: row for row in participants}
        assert by_id[basic_id]["test_content_mode_label"] == "基礎理解版"
        assert by_id[application_id]["test_content_mode_label"] == "現行版（場面応用）"
    finally:
        for participant_id in created_ids:
            response = client.delete(f"/api/admin/participants/{participant_id}")
            assert response.status_code == 200, response.text


def test_hypothesis_metrics_are_partitioned_by_test_content_mode():
    from app.services.research_protocol import MATERIAL_RATING_KEYS

    rows = []
    for mode, offset in (("application", 0.1), ("basic_understanding", 0.8)):
        for group in ("control", "proposed"):
            rows.append({
                "test_content_mode": mode,
                "first_question_only": True,
                "group_condition": group,
                "route": "learning_retest",
                "completion_reason": "completed",
                "has_viewed_material": True,
                "rounds": [],
                "h1": {"value": offset, "status": "observed"},
                "h2": {"value": 1, "censoring_reason": None, "observed_session_count": 1, "attained_without_learning": False},
                "h3": {"value": offset, "status": "observed"},
                "h4": {"value": offset, "numerator": 1, "denominator": 2, "status": "observed"},
                "h5": {"value": offset, "items": {key: 5 for key in MATERIAL_RATING_KEYS}, "status": "observed"},
                "h6": {"value": 1, "attained": True},
            })
    grouped = group_metrics(rows)
    assert {stratum["test_content_mode"] for stratum in grouped["strata"]} == {
        "application", "basic_understanding",
    }
    assert all(len(stratum["groups"]) == 2 for stratum in grouped["strata"])
    exported = metrics_export_rows(rows, grouped=True)
    assert {row["test_content_mode"] for row in exported} == {"application", "basic_understanding"}


def test_basic_mode_routes_each_round_and_reuses_failed_question_snapshot(isolated):
    client, factory, _engine = isolated
    assert client.put("/api/admin/test-content-mode", json={"mode": "basic_understanding"}).status_code == 200
    created = client.post("/api/participants", json={
        "assignment_code": "A", "consent_checked": True, "student_number": "BASIC-ROUND-SNAPSHOT-TEST",
    })
    assert created.status_code == 200, created.text
    participant_id = created.json()["participant_id"]
    try:
        complete_presurvey(client, participant_id)
        pretest = client.get(f"/api/experiment/{participant_id}/pretest").json()["questions"]
        assert "設問1：RAGとモデルの重み" in pretest[0]["body"]

        # Save one selected distractor, then verify learning uses the exact attempt snapshot.
        question = pretest[0]
        with factory() as db:
            wrong_option = next(
                option for option in db.query(QuestionOption).filter_by(question_id=question["question_id"]).all()
                if not option.is_correct and option.misconception_type == "M1"
            )
        displayed_wrong = next(option for option in question["options"] if option["option_id"] == wrong_option.id)
        saved = client.post("/api/attempts", json={
            "participant_id": participant_id,
            "question_id": question["question_id"],
            "phase": "pretest",
            "selected_option_ids": [wrong_option.id],
        })
        assert saved.status_code == 200, saved.text
        with factory() as db:
            attempt = db.query(Attempt).filter_by(participant_id=participant_id, question_id=question["question_id"]).one()
            attempt.is_correct = False
            attempt.misconception_type = "M1"
            db.commit()
            participant = db.get(Participant, participant_id)
            term = db.query(Term).filter_by(slug="llm_knowledge").one()
            confirmation = learning_spec(db, participant, term)
            assert len(confirmation["questions"]) == 1
            assert confirmation["questions"][0]["question_id"] == question["question_id"]
            assert confirmation["questions"][0]["body"] == attempt.question_body_snapshot
            assert confirmation["questions"][0]["options"] == attempt.option_order_snapshot
            assert confirmation["questions"][0]["options"][1]["body"] == displayed_wrong["body"]

        with factory() as db:
            participant = db.get(Participant, participant_id)
            participant.current_step = "final_test"
            db.commit()
        final_test = client.get(f"/api/experiment/{participant_id}/final-test").json()["questions"]
        assert "設問1：RAGとモデルの重みの関係" in final_test[0]["body"]

        with factory() as db:
            participant = db.get(Participant, participant_id)
            participant.current_step = "retest"
            participant.retest_cycles_completed = 0
            db.commit()
        retest_one = client.get(f"/api/experiment/{participant_id}/retest").json()["questions"]
        assert [q["question_id"] for q in retest_one] == [q["question_id"] for q in final_test]
        assert "設問1：RAGとモデルの重みの関係" in retest_one[0]["body"]

        with factory() as db:
            participant = db.get(Participant, participant_id)
            participant.retest_cycles_completed = 1
            db.commit()
        retest_two = client.get(f"/api/experiment/{participant_id}/retest").json()["questions"]
        assert "設問1：RAGとモデルの重みの働き" in retest_two[0]["body"]
    finally:
        response = client.delete(f"/api/admin/participants/{participant_id}")
        assert response.status_code == 200, response.text
