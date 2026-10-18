from __future__ import annotations

import csv
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.experiment_spec import CURRENT_PROTOCOL_ID, can_resume
from app.main import app
from app.db import session as database
from app.db.session import SessionLocal
from app.models import Attempt, AuditEvent, Base, Participant, ParticipantSurvey, Question, Term, TutorSession, TutorTurn
from app.seed.seed_questions import seed_database
from app.services import experiment
from app.services.hypothesis_metrics import current_metrics, group_metrics, participant_metrics, write_metrics_csv
from app.services.research_protocol import MATERIAL_RATING_KEYS, SURVEY_VERSION, SurveyPayload, record_material_view, survey_context, validate_survey_for_participant

client = TestClient(app)
AT = datetime(2026, 10, 18, 1)


@pytest.fixture
def study(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'metrics.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_database(db)
        yield db
    engine.dispose()


def participant(db, code="T", group="proposed", protocol=CURRENT_PROTOCOL_ID):
    row = Participant(display_code=code, group_condition=group, protocol_id=protocol,
                      experiment_spec_version=3, consent_checked=True, current_step="learning")
    db.add(row)
    db.flush()
    return row


def test_round(db, p, number, types, *, phase=None, repeat=1):
    phase = phase or ("pretest" if number == 0 else "retest")
    terms = db.query(Term).filter(Term.slug.in_(["llm_knowledge", "multi_agent", "memory_process"])).order_by(Term.display_order).all()
    for term, kind in zip(terms, types):
        question = db.query(Question).filter_by(term_id=term.id, phase=phase).first()
        db.add(Attempt(participant_id=p.id, term_id=term.id, question_id=question.id, phase=phase,
                       test_round="test" if number == 0 else f"retest_{number}", attempt_index=repeat,
                       is_correct=None if kind == "unscored" else kind == "correct", misconception_type=kind if kind in {"M1", "M3", "unknown"} else None,
                       created_at=AT + timedelta(hours=number), updated_at=AT + timedelta(hours=number)))
    db.flush()


# This is a fixture builder, not a pytest case.
test_round.__test__ = False


def session(db, p, slug, index, wrong=0, *, displayed=True, answered=True, ended=True):
    term = db.query(Term).filter_by(slug=slug).one()
    row = TutorSession(participant_id=p.id, term_id=term.id, session_index=index, group_condition=p.group_condition,
                       started_at=AT + timedelta(minutes=index), ended_at=AT + timedelta(minutes=index + 1) if ended else None,
                       prefetch_state="none" if displayed else "ready")
    db.add(row)
    db.flush()
    for number in range(max(1, wrong)):
        db.add(TutorTurn(tutor_session_id=row.id, turn_index=number + 1, teaching_strategy="foundational_explanation",
                         tutor_message="教材", material_viewed_at=AT + timedelta(minutes=index) if displayed else None,
                         learner_response="回答" if answered else None,
                         grading_json={"is_sufficient": wrong == 0} if answered else None))
    db.flush()
    return row


def questionnaire(viewed=False):
    return {"survey_version": SURVEY_VERSION,
            "experiences": {"chat": True, "coding_assistance": False, "cli": False, "api": True},
            "general_ratings": {"ai_usage_frequency": 1, "self_rated_ai_knowledge": 10, "system_usability": 9, "system_clarity": 8},
            "material_ratings": {key: 7 for key in MATERIAL_RATING_KEYS} if viewed else None,
            "free_comment": "  特になし  "}


def test_six_metrics_use_first_round_and_nested_term_means(study):
    p = participant(study)
    test_round(study, p, 0, ["M1", "M3", "unknown"])
    test_round(study, p, 1, ["M1", "unknown", "correct"])
    test_round(study, p, 2, ["correct"] * 3)
    session(study, p, "llm_knowledge", 1, 3)
    session(study, p, "llm_knowledge", 2, 1)
    session(study, p, "memory_process", 1, 0)
    session(study, p, "multi_agent", 1, displayed=False, answered=False)
    study.add(ParticipantSurvey(participant_id=p.id, phase="posttest", survey_version=SURVEY_VERSION,
                               responses_json=questionnaire(True), free_comment="特になし"))
    study.flush()
    row = participant_metrics(study, p)
    assert row["h1"]["value"] == pytest.approx(100 / 3)
    assert row["h2"]["value"] == 3
    assert row["h2"]["first_mastery_round"] == 2
    assert row["h3"]["term_means"] == {"llm_knowledge": 2, "memory_process": 0}
    assert row["h3"]["value"] == 1
    assert row["h4"]["value"] == 0.5
    assert row["h4"]["denominator"] == 2
    assert row["h5"]["value"] == 7
    assert row["h6"]["attained"] is True
    assert row["rounds"][1]["gain_pt"] == 100


@pytest.mark.parametrize("types", [["correct"], ["correct", "correct", "unscored"]])
def test_incomplete_or_unscored_tests_are_not_mastery_or_zero_missing(study, types):
    p = participant(study)
    test_round(study, p, 0, ["M1"] * 3)
    test_round(study, p, 1, types)
    session(study, p, "llm_knowledge", 1, answered=False)
    row = participant_metrics(study, p)
    assert row["h1"]["value"] is None
    assert row["h4"]["value"] is None
    assert row["h2"]["value"] is None
    assert row["h2"]["observed_session_count"] == 1
    assert row["h3"]["value"] is None
    assert row["h5"]["status"] == "missing_survey"
    assert row["h6"]["attained"] is False


def test_initial_perfect_final_test_route_counts_zero_learning(study):
    p = participant(study)
    test_round(study, p, 0, ["correct"] * 3)
    test_round(study, p, 1, ["correct"] * 3, phase="final_test")
    row = participant_metrics(study, p)
    assert row["route"] == "initial_perfect_final_test"
    assert row["h1"]["value"] == 0
    assert row["h2"]["value"] == 0
    assert row["h2"]["attained_without_learning"]
    assert row["h4"]["value"] is None
    assert row["h4"]["status"].startswith("not_applicable")
    assert row["h5"]["items"] is None
    assert row["h6"]["value"] == 1


def test_mastery_does_not_depend_on_survey_completion_and_is_first_not_latest(study):
    p = participant(study)
    p.completion_reason = "give_up"
    test_round(study, p, 0, ["M3"] * 3)
    test_round(study, p, 1, ["correct"] * 3)
    test_round(study, p, 2, ["M3"] * 3)
    row = participant_metrics(study, p)
    assert row["h6"]["value"] == 1
    assert row["h2"]["first_mastery_round"] == 1


def test_group_weights_missing_censoring_and_export_match(study, tmp_path):
    a = participant(study, "A")
    b = participant(study, "B")
    c = participant(study, "C", "control")
    participant(study, "LEGACY", protocol=None)
    test_round(study, a, 0, ["M1", "correct", "correct"])
    test_round(study, a, 1, ["M1", "correct", "correct"])
    test_round(study, b, 0, ["M1"] * 3)
    test_round(study, b, 1, ["correct"] * 3)
    rows = current_metrics(study)
    assert len(rows) == 3
    result = group_metrics(rows)
    proposed = next(g for g in result["groups"] if g["group_condition"] == "proposed")
    assert proposed["h4"]["mean"] == 0.5
    assert proposed["h4"]["pooled_rate"] == 0.25
    assert proposed["h6"]["rate"] == 0.5
    assert proposed["h2"]["n"] == 1
    assert proposed["h2"]["not_attained_count"] == 1
    control = next(g for g in result["groups"] if g["group_condition"] == "control")
    assert control["h1"]["mean"] is None
    assert control["h1"]["missing_count"] == 1
    assert control["h6"]["rate"] == 0
    for grouped in (False, True):
        path = write_metrics_csv(tmp_path / f"{grouped}.csv", rows, grouped=grouped)
        exported = list(csv.DictReader(path.open(encoding="utf-8-sig")))
        assert exported
        assert all(r["protocol_id"] == CURRENT_PROTOCOL_ID for r in exported)
        assert "LEGACY" not in path.read_text(encoding="utf-8-sig")


def test_rounds_remain_distinct_after_variant_five_is_reused(study):
    p = participant(study)
    test_round(study, p, 0, ["M1"] * 3)
    test_round(study, p, 5, ["M1"] * 3)
    test_round(study, p, 5, ["correct"] * 3, repeat=2)
    row = participant_metrics(study, p)
    assert [r["round"] for r in row["rounds"]] == [5, 6]
    assert row["h1"]["value"] is None
    assert row["h2"]["first_mastery_round"] == 6


@pytest.mark.parametrize("field,value", [("ai_usage_frequency", 0), ("ai_usage_frequency", 11), ("system_usability", True), ("system_clarity", 5.5), ("self_rated_ai_knowledge", "5")])
def test_rating_validation_is_strict_and_bounded(field, value):
    payload = questionnaire()
    payload["general_ratings"][field] = value
    with pytest.raises(ValidationError):
        SurveyPayload.model_validate(payload)


def test_required_boolean_comment_and_material_fields():
    assert SurveyPayload.model_validate(questionnaire()).free_comment == "特になし"
    assert SurveyPayload.model_validate(questionnaire()).material_ratings is None
    for mutate in (lambda p: p.pop("experiences"), lambda p: p.update(free_comment="  "),
                   lambda p: p["experiences"].update(chat="yes"), lambda p: p.update(material_ratings={"clarity": 7})):
        payload = questionnaire()
        mutate(payload)
        with pytest.raises(ValidationError):
            SurveyPayload.model_validate(payload)


def test_display_is_idempotent_and_controls_survey_eligibility(study):
    p = participant(study)
    row = session(study, p, "memory_process", 1, displayed=False, answered=False, ended=False)
    turn = study.query(TutorTurn).filter_by(tutor_session_id=row.id).one()
    assert not survey_context(study, p)["has_viewed_material"]
    assert validate_survey_for_participant(study, p, questionnaire())["material_ratings"] is None
    with pytest.raises(HTTPException):
        record_material_view(study, turn.id)
    row.prefetch_state = "consumed"
    study.commit()
    first = record_material_view(study, turn.id)
    second = record_material_view(study, turn.id)
    assert first == second
    assert study.query(AuditEvent).filter_by(action="material_view", entity_id=p.id).count() == 1
    assert survey_context(study, p)["material_ratings_required"]
    with pytest.raises(HTTPException):
        validate_survey_for_participant(study, p, questionnaire())
    assert validate_survey_for_participant(study, p, questionnaire(True))["material_rating_status"] == "answered"


def test_old_v3_new_columns_and_startup_preserve_all_existing_values(study, monkeypatch):
    p = participant(study, protocol=None)
    p.current_step = "finish"
    p.completion_reason = None
    p.completed_at = AT
    study.commit()
    before = dict(study.execute(text("SELECT * FROM participants WHERE id=:id"), {"id": p.id}).mappings().one())
    assert not can_resume(p)
    monkeypatch.setattr(database, "engine", study.get_bind())
    database.init_db()
    after = dict(study.execute(text("SELECT * FROM participants WHERE id=:id"), {"id": p.id}).mappings().one())
    assert before == after
    with pytest.raises(HTTPException):
        experiment.delete_participant(study, p.id)
    assert not current_metrics(study)


def test_additive_migration_does_not_relabel_or_convert_legacy_rows(study, monkeypatch):
    p = participant(study, protocol=None)
    study.add(ParticipantSurvey(participant_id=p.id, phase="posttest", usability_rating=5, free_comment="旧回答"))
    study.commit()
    original = dict(study.execute(text("SELECT * FROM participants WHERE id=:id"), {"id": p.id}).mappings().one())
    with study.get_bind().begin() as connection:
        for table, column in (("participants", "protocol_id"), ("participant_surveys", "survey_version"),
                              ("participant_surveys", "responses_json"), ("tutor_turns", "material_viewed_at"),
                              ("evaluation_summaries", "hypothesis_metrics_json")):
            connection.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
    monkeypatch.setattr(database, "engine", study.get_bind())
    database.init_db()
    database.init_db()
    study.expire_all()
    after = dict(study.execute(text("SELECT * FROM participants WHERE id=:id"), {"id": p.id}).mappings().one())
    assert original == after
    survey = study.query(ParticipantSurvey).filter_by(participant_id=p.id).one()
    assert (survey.usability_rating, survey.free_comment, survey.responses_json, survey.survey_version) == (5, "旧回答", None, None)
    assert not can_resume(study.get(Participant, p.id))


def test_new_api_survey_context_persistence_and_legacy_protection():
    created = client.post("/api/participants", json={"assignment_code": "A", "consent_checked": True})
    assert created.status_code == 200
    pid = created.json()["participant_id"]
    assert client.get(f"/api/participants/{pid}/survey").json()["material_ratings_required"] is False
    with SessionLocal() as db:
        p = db.get(Participant, pid)
        assert p.protocol_id == CURRENT_PROTOCOL_ID
        p.current_step = "survey"
        db.commit()
    invalid = questionnaire(True)
    assert client.post(f"/api/participants/{pid}/survey", json=invalid).status_code == 422
    saved = client.post(f"/api/participants/{pid}/survey", json=questionnaire(), headers={"Idempotency-Key": f"survey-{pid}"})
    assert saved.status_code == 200, saved.text
    replay = client.post(f"/api/participants/{pid}/survey", json=questionnaire(), headers={"Idempotency-Key": f"survey-{pid}"})
    assert replay.json() == saved.json()
    logs = client.get(f"/api/admin/participants/{pid}/logs").json()
    assert logs["surveys"][0]["survey_version"] == SURVEY_VERSION
    assert logs["surveys"][0]["responses"]["material_rating_status"] == "not_applicable_not_viewed"
    assert logs["surveys"][0]["ai_experience_level"] is None
    csv_response = client.get(f"/api/admin/participants/{pid}/logs.csv")
    assert next(csv.reader(csv_response.text.splitlines())) == experiment.LOG_CSV_COLUMNS
    assert CURRENT_PROTOCOL_ID in csv_response.text
    for name in ("hypothesis_metrics", "hypothesis_group_summary"):
        assert client.get(f"/api/admin/export/{name}.csv").status_code == 200
