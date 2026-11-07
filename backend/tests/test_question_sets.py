from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from admin_client import AuthenticatedTestClient
from app.core.question_sets import (
    ASSESSMENT_BANK_VERSIONS,
    HISTORICAL_ASSESSMENT_BANK_VERSIONS,
    LEARNING_CONTENT_VERSIONS,
    STANDARD,
)
from app.db.session import get_db
from app.main import app
from app.models import Base, Participant, Question, QuestionOption
from app.seed.content_loader import ACTIVE_TERM_SLUGS, assessment_question_spec, load_content, load_learning_content
from app.seed.seed_questions import seed_database
from split_api_support import complete_presurvey


@pytest.fixture
def isolated(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'standard-only.db'}")
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


def test_only_standard_bank_is_available_and_history_is_standard_only():
    assert ASSESSMENT_BANK_VERSIONS == {STANDARD: "split-actions-v5"}
    assert LEARNING_CONTENT_VERSIONS == {STANDARD: 15}
    assert all(set(banks) == {STANDARD} for banks in HISTORICAL_ASSESSMENT_BANK_VERSIONS.values())
    assert len(load_content()["terms"]) == len(ACTIVE_TERM_SLUGS)
    assert len(load_learning_content()["terms"]) == len(ACTIVE_TERM_SLUGS)
    for slug in ACTIVE_TERM_SLUGS:
        assert assessment_question_spec(slug, "pretest")["body"]


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


def test_new_participant_has_standard_content_and_no_mode_fields(isolated):
    client, factory, engine = isolated
    response = client.post("/api/participants", json={
        "assignment_code": "A", "consent_checked": True, "student_number": "STANDARD-ONLY-TEST",
    })
    assert response.status_code == 200, response.text
    participant_id = response.json()["participant_id"]
    complete_presurvey(client, participant_id)
    questions = client.get(f"/api/experiment/{participant_id}/pretest").json()["questions"]
    assert len(questions) == 3
    assert all(len(question["options"]) == 6 for question in questions)
    with factory() as db:
        participant = db.get(Participant, participant_id)
        assert participant.learning_content_version == 15
        assert not hasattr(participant, "question_set_mode")
        assert db.query(Question).filter(Question.construct_key.contains("easy")).count() == 0
        assert db.query(QuestionOption).count() == 108
    assert "question_set_mode" not in {column["name"] for column in inspect(engine).get_columns("participants")}
    assert "question_set_mode" not in {column["name"] for column in inspect(engine).get_columns("runtime_settings")}
