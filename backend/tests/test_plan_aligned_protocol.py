from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from admin_client import AuthenticatedTestClient as TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID, can_resume
from app.core.question_sets import ASSESSMENT_MODE_BANK_VERSIONS, LEARNING_CONTENT_VERSIONS, STANDARD
from app.main import app
from app.db import session as database
from app.db.session import SessionLocal
from app.models import Attempt, AuditEvent, Base, EvaluationSummary, Participant, ParticipantSurvey, Question, Term, TutorSession, TutorTurn
from app.seed.seed_questions import seed_database
from app.services import experiment
from split_api_support import new_research_code
from app.services.hypothesis_metrics import (
    H5_COMPOSITE_KEYS,
    current_metrics,
    group_metrics,
    participant_metrics,
    write_metrics_csv,
)
from app.services.hypothesis_metrics import METRICS_VERSION
from app.services.research_protocol import (
    FOUR_TOPIC_PRESURVEY_TERM_ITEMS,
    FOUR_TOPIC_PRESURVEY_V2_TERM_ITEMS,
    MATERIAL_RATING_KEYS,
    PRESURVEY_TERM_ITEMS,
    PRESURVEY_VERSION,
    SURVEY_VERSION,
    FourTopicPresurveyPayload,
    FourTopicPresurveyPayloadV2,
    PresurveyPayload,
    SurveyPayload,
    record_material_view,
    survey_context,
    validate_survey_for_participant,
)

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
                      experiment_spec_version=CURRENT_EXPERIMENT_SPEC_VERSION, learning_content_version=LEARNING_CONTENT_VERSIONS[STANDARD], test_content_mode="application", consent_checked=True, current_step="learning")
    db.add(row)
    db.flush()
    return row


def test_round(db, p, number, types, *, phase=None, repeat=1):
    phase = phase or ("pretest" if number == 0 else "retest")
    terms = db.query(Term).filter(Term.slug.in_(["llm_knowledge", "multi_agent", "memory_process"])).order_by(Term.display_order).all()
    for term, kind in zip(terms, types):
        source_phase = "pretest" if phase == "pretest" else "retest"
        prefix = "pretest_v1" if number == 0 else f"retest_v{min(number, 2)}"
        for item in (1, 2):
            question = db.query(Question).filter_by(term_id=term.id, phase=source_phase, variant_key=f"{prefix}_q{item}").filter(
                Question.construct_key.endswith(ASSESSMENT_MODE_BANK_VERSIONS["application"])
            ).one()
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
            "general_ratings": {"system_usability": 4, "system_clarity": 5},
            "material_ratings": {key: 4 for key in MATERIAL_RATING_KEYS} if viewed else None,
            "free_comment": "  特になし  "}


def baseline_questionnaire(survey_version=PRESURVEY_VERSION, term_keys=None):
    term_keys = term_keys or [item["key"] for item in PRESURVEY_TERM_ITEMS]
    exposure = {
        key: ("experienced" if index % 3 == 0 else "not_experienced" if index % 3 == 1 else "cannot_recall")
        for index, key in enumerate(term_keys)
    }
    return {
        "survey_version": survey_version,
        "prior_term_exposure": exposure,
        "prior_term_understanding": {
            key: ("moderately" if exposure[key] == "experienced" else None)
            for key in term_keys
        },
        "general_ratings": {
            "ai_usage_frequency_30d": "9_20_days",
            "ai_proficiency": {
                "goal_aligned_output": 4,
                "revise_instructions": 2,
                "verify_with_sources": "not_applicable",
            },
        },
    }


def test_spec_36_boolean_presurvey_record_remains_unchanged_and_read_only(study):
    old = Participant(
        display_code="OLD-PRESURVEY",
        group_condition="control",
        protocol_id="experiment-plan-2026-11-04-presurvey-baseline-v1",
        experiment_spec_version=36,
        learning_content_version=LEARNING_CONTENT_VERSIONS[STANDARD],
        consent_checked=True,
        current_step="pretest",
    )
    study.add(old)
    study.flush()
    old_responses = {"prior_term_knowledge": {
        "pretraining": True, "fine_tuning": False, "rag": True,
        "prompt_engineering": False, "multi_agent": True, "memory_process": False,
    }}
    survey = ParticipantSurvey(
        participant_id=old.id,
        phase="presurvey",
        survey_version="presurvey-baseline-v1",
        responses_json=old_responses,
    )
    study.add(survey)
    study.flush()

    assert can_resume(old) is False
    assert study.get(ParticipantSurvey, survey.id).responses_json == old_responses


def test_spec_49_posttest_answer_remains_read_only_without_migration(study):
    old = Participant(
        display_code="OLD-POSTTEST-49",
        group_condition="control",
        protocol_id="experiment-plan-2026-11-10-posttest-five-point-evaluation-v1",
        experiment_spec_version=49,
        learning_content_version=LEARNING_CONTENT_VERSIONS[STANDARD],
        consent_checked=True,
        current_step="finish",
    )
    study.add(old)
    study.flush()
    responses = questionnaire(viewed=True)
    responses["survey_version"] = "posttest-5point-v1"
    survey = ParticipantSurvey(
        participant_id=old.id,
        phase="posttest",
        survey_version="posttest-5point-v1",
        responses_json=responses,
    )
    study.add(survey)
    study.commit()

    assert can_resume(old) is False
    study.refresh(survey)
    assert survey.survey_version == "posttest-5point-v1"
    assert survey.responses_json == responses


def test_spec_50_posttest_v2_answer_remains_read_only_without_migration(study):
    old = Participant(
        display_code="OLD-POSTTEST-50",
        group_condition="control",
        protocol_id="experiment-plan-2026-11-11-posttest-material-amount-wording-v1",
        experiment_spec_version=50,
        learning_content_version=LEARNING_CONTENT_VERSIONS[STANDARD],
        consent_checked=True,
        current_step="finish",
    )
    study.add(old)
    study.flush()
    responses = questionnaire(viewed=True)
    responses["survey_version"] = "posttest-5point-v2"
    responses["material_ratings"]["amount_appropriateness"] = 3
    survey = ParticipantSurvey(
        participant_id=old.id,
        phase="posttest",
        survey_version="posttest-5point-v2",
        responses_json=responses,
    )
    study.add(survey)
    study.commit()

    assert can_resume(old) is False
    study.refresh(survey)
    assert survey.survey_version == "posttest-5point-v2"
    assert survey.responses_json == responses


def test_six_metrics_use_first_round_and_nested_term_means(study):
    p = participant(study)
    test_round(study, p, 0, ["M1", "M3", "unknown"])
    test_round(study, p, 1, ["M1", "unknown", "correct"])
    test_round(study, p, 2, ["correct"] * 3)
    session(study, p, "llm_knowledge", 1, 3)
    session(study, p, "llm_knowledge", 2, 1)
    session(study, p, "memory_process", 1, 0)
    session(study, p, "multi_agent", 1, displayed=False, answered=False)
    study.add(ParticipantSurvey(participant_id=p.id, phase="presurvey", survey_version=PRESURVEY_VERSION,
                               responses_json={"material_ratings": {key: 1 for key in MATERIAL_RATING_KEYS}}))
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
    assert row["h4"]["denominator"] == 4
    assert row["h5"]["value"] == 4
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


def test_pretest_perfect_early_exit_is_not_applicable_to_h1_h2_h6(study, tmp_path):
    p = participant(study)
    test_round(study, p, 0, ["correct"] * 3)
    p.current_step = "survey"
    row = participant_metrics(study, p)
    assert row["route"] == "pretest_perfect_early_exit"
    assert row["pretest_perfect_early_exit"] is True
    assert row["h1"]["value"] is None
    assert row["h1"]["status"] == "not_applicable_pretest_mastery"
    assert row["h2"]["value"] is None
    assert row["h2"]["status"] == "not_applicable_pretest_mastery"
    assert row["h4"]["value"] is None
    assert row["h4"]["status"].startswith("not_applicable")
    assert row["h5"]["items"] is None
    assert row["h6"]["value"] is None
    assert row["h6"]["status"] == "not_applicable_pretest_mastery"

    grouped = group_metrics([row])
    proposed = grouped["groups"][1]
    assert proposed["participant_count"] == 1
    assert proposed["pretest_perfect_early_exit_count"] == 1
    for key in ("h1", "h2", "h6"):
        assert proposed[key]["eligible_count"] == 0
        assert proposed[key]["not_applicable_count"] == 1
        assert proposed[key]["missing_count"] == 0
    assert proposed["h6"]["denominator"] == 0
    assert proposed["h6"]["numerator"] == 0
    assert grouped["routes"]["pretest_perfect_early_exit"][1]["participant_count"] == 1
    exported = write_metrics_csv(tmp_path / "early-exit.csv", [row], grouped=True)
    records = list(csv.DictReader(exported.open(encoding="utf-8-sig")))
    h6 = next(record for record in records if record["metric"] == "h6" and record["group_condition"] == "proposed")
    assert h6["eligible_count"] == "0"
    assert h6["not_applicable_count"] == "1"
    assert json.loads(h6["details_json"])["denominator"] == 0
    assert proposed["rounds"] == []

    learner = participant(study, "LEARNER")
    test_round(study, learner, 0, ["M1"] * 3)
    test_round(study, learner, 1, ["M1"] * 3)
    mixed_group = group_metrics([row, participant_metrics(study, learner)])
    retest_one = mixed_group["groups"][1]["rounds"][0]
    assert retest_one["gain"]["eligible_count"] == 1
    assert retest_one["gain"]["not_applicable_count"] == 1
    assert retest_one["gain"]["missing_count"] == 0
    assert retest_one["recurrence"]["eligible_count"] == 1
    assert retest_one["recurrence"]["not_applicable_count"] == 1
    assert retest_one["recurrence"]["missing_count"] == 0


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


def test_h2_distinguishes_nonattainer_outcomes_without_changing_h6(study, tmp_path):
    for index, reason in enumerate(("give_up", None, "completed", "other")):
        p = participant(study, f"NOT-{index}")
        p.completion_reason = reason
        if reason == "completed":
            p.completed_at = AT
            p.current_step = "finish"
        for number in range(index):
            session(study, p, "llm_knowledge", number + 1, answered=False)
    for index, reason in enumerate(("completed", "give_up")):
        p = participant(study, f"ATTAINED-{index}")
        p.completion_reason = reason
        test_round(study, p, 0, ["M1"] * 3)
        test_round(study, p, 1, ["correct"] * 3, phase="final_test")
    rows = current_metrics(study)
    by_code = {row["display_code"]: row for row in rows}
    assert [by_code[f"NOT-{i}"]["h2"]["censoring_reason"] for i in range(4)] == ["give_up", "in_progress", "completed_without_mastery", "other"]
    assert all(by_code[f"ATTAINED-{i}"]["h2"]["censoring_reason"] is None for i in range(2))
    result = group_metrics(rows)["groups"][1]
    assert result["h2"]["n"] == 2
    assert result["h2"]["mean"] == 0
    assert result["h2"]["missing_count"] == 4
    assert result["h2"]["censored_count"] == 4
    assert result["h2"]["not_attained_count"] == 4
    assert result["h2"]["observed_nonattainer_sessions"]["mean"] == 1.5
    for reason, count in zip(("give_up", "in_progress", "completed_without_mastery", "other"), range(4)):
        assert result["h2"]["censoring_breakdown"][reason]["n"] == 1
        assert result["h2"]["censoring_breakdown"][reason]["mean"] == count
    assert result["h6"]["denominator"] == 6
    assert result["h6"]["numerator"] == 2
    assert result["h6"]["rate"] == pytest.approx(1 / 3)
    exported = write_metrics_csv(tmp_path / "h2.csv", rows, grouped=True)
    records = list(csv.DictReader(exported.open(encoding="utf-8-sig")))
    h2 = next(r for r in records if r["metric"] == "h2" and r["group_condition"] == "proposed")
    assert h2["missing_count"] == "4"
    assert json.loads(h2["details_json"])["censoring_breakdown"] == result["h2"]["censoring_breakdown"]


@pytest.mark.parametrize("grouped", [False, True])
def test_metrics_csv_creates_missing_parent_directories(study, tmp_path, grouped):
    participant(study)
    path = tmp_path / "not-created" / "nested" / "metrics.csv"
    assert not path.parent.exists()
    assert write_metrics_csv(path, current_metrics(study), grouped=grouped) == path
    assert list(csv.DictReader(path.open(encoding="utf-8-sig")))


def test_material_view_without_an_answer_refreshes_evaluation_cache(study):
    p = participant(study)
    test_round(study, p, 0, ["M1"] * 3)
    row = session(study, p, "llm_knowledge", 1, displayed=False, answered=False, ended=False)
    row.prefetch_state = "consumed"
    study.commit()
    cached = experiment._ensure_evaluation_summary(study, p)
    assert cached.hypothesis_metrics_json["has_viewed_material"] is False
    assert experiment._ensure_evaluation_summary(study, p).id == cached.id
    turn = study.query(TutorTurn).filter_by(tutor_session_id=row.id).one()
    record_material_view(study, turn.id)
    assert turn.learner_response is None
    assert experiment._latest_evaluation_source_at(study, p) > cached.created_at
    refreshed = experiment._ensure_evaluation_summary(study, p)
    assert refreshed.id != cached.id
    assert refreshed.hypothesis_metrics_json["has_viewed_material"] is True
    assert refreshed.hypothesis_metrics_json["h2"]["observed_session_count"] == 1
    assert refreshed.hypothesis_metrics_json["h5"]["status"] == "missing_survey"
    record_material_view(study, turn.id)
    assert experiment._ensure_evaluation_summary(study, p).id == refreshed.id


def test_evaluation_cache_refreshes_only_current_protocol_on_metrics_version_change(study):
    for code, protocol in (("CURRENT", CURRENT_PROTOCOL_ID), ("LEGACY", None)):
        p = participant(study, code, protocol=protocol)
        test_round(study, p, 0, ["M1"] * 3)
        study.commit()
        cached = EvaluationSummary(participant_id=p.id, group_condition=p.group_condition,
                                   hypothesis_metrics_json={"metrics_version": "six-hypotheses-v1"})
        study.add(cached)
        study.commit()
        refreshed = experiment._ensure_evaluation_summary(study, p)
        assert (refreshed.id != cached.id) is (protocol == CURRENT_PROTOCOL_ID)
        if protocol == CURRENT_PROTOCOL_ID:
            assert refreshed.hypothesis_metrics_json["metrics_version"] == METRICS_VERSION


def test_rounds_remain_distinct_after_variant_five_is_reused(study):
    p = participant(study)
    test_round(study, p, 0, ["M1"] * 3)
    test_round(study, p, 5, ["M1"] * 3)
    test_round(study, p, 5, ["correct"] * 3, repeat=2)
    row = participant_metrics(study, p)
    assert [r["round"] for r in row["rounds"]] == [5, 6]
    assert row["h1"]["value"] is None
    assert row["h2"]["first_mastery_round"] == 6


@pytest.mark.parametrize("field,value", [("system_usability", 0), ("system_usability", 6), ("system_usability", True), ("system_clarity", 3.5), ("system_clarity", "4")])
def test_rating_validation_is_strict_and_bounded(field, value):
    payload = questionnaire()
    payload["general_ratings"][field] = value
    with pytest.raises(ValidationError):
        SurveyPayload.model_validate(payload)


def test_required_knowledge_and_material_fields():
    assert SurveyPayload.model_validate(questionnaire()).free_comment == "特になし"
    assert SurveyPayload.model_validate(questionnaire()).material_ratings is None
    for mutate in (lambda p: p.pop("general_ratings"),
                   lambda p: p.update(material_ratings={"clarity": 7})):
        payload = questionnaire()
        mutate(payload)
        with pytest.raises(ValidationError):
            SurveyPayload.model_validate(payload)
    for mutate in (lambda p: p.pop("prior_term_exposure"),
                   lambda p: p["prior_term_exposure"].update(pretraining="yes"),
                   lambda p: p["general_ratings"].pop("ai_usage_frequency_30d")):
        payload = baseline_questionnaire()
        mutate(payload)
        with pytest.raises(ValidationError):
            PresurveyPayload.model_validate(payload)


@pytest.mark.parametrize("section,keys", [
    ("general_ratings", ("system_usability", "system_clarity")),
    ("material_ratings", MATERIAL_RATING_KEYS),
])
def test_every_displayed_survey_item_requires_an_explicit_answer(section, keys):
    for key in keys:
        payload = questionnaire(True)
        payload[section].pop(key)
        with pytest.raises(ValidationError):
            SurveyPayload.model_validate(payload)
    payload = questionnaire(True)


@pytest.mark.parametrize("section,keys", [
    ("prior_term_exposure", ("pretraining", "fine_tuning", "rag", "prompt_engineering", "multi_agent", "memory_process")),
    ("prior_term_understanding", ("pretraining", "fine_tuning", "rag", "prompt_engineering", "multi_agent", "memory_process")),
    ("ai_proficiency", ("goal_aligned_output", "revise_instructions", "verify_with_sources")),
])
def test_every_displayed_presurvey_item_requires_an_explicit_answer(section, keys):
    for key in keys:
        payload = baseline_questionnaire()
        target = payload["general_ratings"][section] if section == "ai_proficiency" else payload[section]
        target.pop(key)
        with pytest.raises(ValidationError):
            PresurveyPayload.model_validate(payload)


def test_presurvey_exposure_conditioned_understanding_and_scales_are_strict():
    payload = baseline_questionnaire()
    assert PresurveyPayload.model_validate(payload)

    for exposure in ("not_experienced", "cannot_recall"):
        invalid = baseline_questionnaire()
        invalid["prior_term_exposure"]["pretraining"] = exposure
        invalid["prior_term_understanding"]["pretraining"] = "moderately"
        with pytest.raises(ValidationError):
            PresurveyPayload.model_validate(invalid)
        invalid["prior_term_understanding"]["pretraining"] = None
        assert PresurveyPayload.model_validate(invalid)

    invalid = baseline_questionnaire()
    invalid["prior_term_understanding"]["pretraining"] = None
    with pytest.raises(ValidationError):
        PresurveyPayload.model_validate(invalid)

    for exposure in ("experienced", "not_experienced", "cannot_recall"):
        invalid = baseline_questionnaire()
        invalid["prior_term_exposure"]["pretraining"] = exposure
        invalid["prior_term_understanding"]["pretraining"] = "unknown"
        with pytest.raises(ValidationError):
            PresurveyPayload.model_validate(invalid)

    invalid = baseline_questionnaire()
    invalid["prior_term_exposure"]["unexpected"] = "experienced"
    with pytest.raises(ValidationError):
        PresurveyPayload.model_validate(invalid)
    invalid = baseline_questionnaire()
    invalid["general_ratings"]["ai_usage_frequency_30d"] = 31
    with pytest.raises(ValidationError):
        PresurveyPayload.model_validate(invalid)
    invalid = baseline_questionnaire()
    invalid["general_ratings"]["ai_proficiency"]["goal_aligned_output"] = 6
    with pytest.raises(ValidationError):
        PresurveyPayload.model_validate(invalid)


def test_four_topic_presurvey_has_six_separate_terms_and_same_branch_validation():
    keys = [item["key"] for item in FOUR_TOPIC_PRESURVEY_TERM_ITEMS]
    assert keys == ["transformer", "pretraining", "fine_tuning", "human_feedback_post_training", "multi_agent", "memory_process"]
    payload = baseline_questionnaire("presurvey-four-topic-baseline-v3", keys)
    parsed = FourTopicPresurveyPayload.model_validate(payload)
    assert set(parsed.prior_term_exposure.model_dump()) == set(keys)
    payload["prior_term_exposure"]["transformer"] = "cannot_recall"
    with pytest.raises(ValidationError):
        FourTopicPresurveyPayload.model_validate(payload)


def test_four_topic_presurvey_v2_schema_remains_available_for_historical_records():
    old_keys = [item["key"] for item in FOUR_TOPIC_PRESURVEY_V2_TERM_ITEMS]
    payload = baseline_questionnaire("presurvey-four-topic-baseline-v2", old_keys)
    parsed = FourTopicPresurveyPayloadV2.model_validate(payload)
    assert set(parsed.prior_term_exposure.model_dump()) == set(old_keys)
    assert "instruction_tuning" in parsed.prior_term_exposure.model_dump()
    with pytest.raises(ValidationError):
        FourTopicPresurveyPayload.model_validate(payload)


@pytest.mark.parametrize("comment", [None, "", "   ", "  感想  "])
def test_free_comment_is_optional_and_trimmed(comment):
    payload = questionnaire()
    payload["free_comment"] = comment
    assert SurveyPayload.model_validate(payload).free_comment == (comment.strip() if comment is not None else None)
    payload.pop("free_comment")
    assert SurveyPayload.model_validate(payload).free_comment is None


def test_old_questionnaire_cannot_be_written_as_the_new_version():
    payload = questionnaire()
    payload["survey_version"] = "posttest-10point-v1"
    with pytest.raises(ValidationError):
        SurveyPayload.model_validate(payload)
    payload = questionnaire()
    payload["survey_version"] = "posttest-5point-v1"
    with pytest.raises(ValidationError):
        SurveyPayload.model_validate(payload)
    payload = questionnaire()
    payload["survey_version"] = "posttest-5point-v2"
    with pytest.raises(ValidationError):
        SurveyPayload.model_validate(payload)
    payload = questionnaire()
    payload["experiences"] = {"chat": True, "coding_assistance": False, "cli": False, "api": False}
    with pytest.raises(ValidationError):
        SurveyPayload.model_validate(payload)


@pytest.mark.parametrize("version", ["posttest-10point-v1", "posttest-10point-v2", "posttest-10point-v3", "posttest-5point-v1", "posttest-5point-v2", SURVEY_VERSION])
def test_h5_uses_only_current_survey_version_without_rewriting_history(study, version):
    p = participant(study)
    session(study, p, "llm_knowledge", 1)
    responses = questionnaire(True)
    responses["survey_version"] = version
    if version == "posttest-10point-v1":
        responses["experiences"] = {"chat": True, "coding_assistance": False, "cli": False, "api": False}
        ratings = responses["general_ratings"]
        ratings["self_rated_ai_knowledge"] = 5
    elif version == "posttest-10point-v2":
        responses["prior_term_knowledge"] = {"pretraining": True, "fine_tuning": False, "rag": False, "prompt_engineering": True, "multi_agent": False, "memory_process": True}
        responses["general_ratings"] = {
            **baseline_questionnaire()["general_ratings"],
            "system_usability": 9,
            "system_clarity": 8,
        }
    original = json.loads(json.dumps(responses))
    survey = ParticipantSurvey(participant_id=p.id, phase="posttest", survey_version=version,
                               responses_json=responses, free_comment=None)
    study.add(survey)
    study.commit()
    metrics = participant_metrics(study, p)["h5"]
    assert metrics["value"] == (4 if version == SURVEY_VERSION else None)
    assert metrics["status"] == ("observed" if version == SURVEY_VERSION else "missing_survey")
    study.refresh(survey)
    assert survey.responses_json == original
    assert survey.survey_version == version


def test_h5_excludes_not_applicable_and_reports_centered_scales_as_distributions(study, tmp_path):
    p = participant(study)
    session(study, p, "llm_knowledge", 1)
    responses = questionnaire(True)
    responses["material_ratings"] = {
        "clarity": 2,
        "readability": "not_applicable",
        "japanese_clarity": 4,
        "difficulty_appropriateness": 5,
        "learning_usefulness": 3,
        "amount_appropriateness": "not_applicable",
    }
    study.add(ParticipantSurvey(participant_id=p.id, phase="posttest", survey_version=SURVEY_VERSION,
                                responses_json=responses))
    study.flush()
    row = participant_metrics(study, p)
    assert row["h5"]["value"] == pytest.approx(3)
    assert row["h5"]["valid_item_count"] == 3
    assert row["h5"]["not_evaluable_item_count"] == 1

    groups = group_metrics([row])["groups"][1]["h5"]
    assert groups["items"]["difficulty_appropriateness"]["mean"] is None
    assert groups["items"]["difficulty_appropriateness"]["distribution"]["5"] == 1
    assert groups["items"]["amount_appropriateness"]["distribution"]["not_applicable"] == 1
    exported = write_metrics_csv(tmp_path / "survey-metrics.csv", [row], grouped=True)
    records = list(csv.DictReader(exported.open(encoding="utf-8-sig")))
    difficulty = next(record for record in records if record["metric"] == "h5.difficulty_appropriateness" and record["group_condition"] == "proposed")
    assert difficulty["mean"] == ""
    assert json.loads(difficulty["details_json"])["distribution"]["5"] == 1


def test_h5_all_core_items_not_evaluable_is_not_applicable(study):
    p = participant(study)
    session(study, p, "llm_knowledge", 1)
    responses = questionnaire(True)
    for key in ("clarity", "readability", "japanese_clarity", "learning_usefulness"):
        responses["material_ratings"][key] = "not_applicable"
    study.add(ParticipantSurvey(participant_id=p.id, phase="posttest", survey_version=SURVEY_VERSION,
                                responses_json=responses))
    study.flush()
    metric = participant_metrics(study, p)["h5"]
    assert metric["value"] is None
    assert metric["status"] == "not_applicable_no_evaluable_ratings"
    assert metric["not_evaluable_item_count"] == 4


def test_h5_group_counts_separate_eligible_missing_not_viewed_and_not_evaluable(study, tmp_path):
    observed = participant(study, "OBSERVED")
    session(study, observed, "llm_knowledge", 1)
    study.add(ParticipantSurvey(participant_id=observed.id, phase="posttest", survey_version=SURVEY_VERSION,
                                responses_json=questionnaire(True)))

    missing = participant(study, "MISSING")
    session(study, missing, "llm_knowledge", 1)

    not_evaluable = participant(study, "NOT-EVALUABLE")
    session(study, not_evaluable, "llm_knowledge", 1)
    responses = questionnaire(True)
    for key in H5_COMPOSITE_KEYS:
        responses["material_ratings"][key] = "not_applicable"
    study.add(ParticipantSurvey(participant_id=not_evaluable.id, phase="posttest", survey_version=SURVEY_VERSION,
                                responses_json=responses))

    not_viewed = participant(study, "NOT-VIEWED")
    session(study, not_viewed, "llm_knowledge", 1, displayed=False)
    study.flush()

    rows = [participant_metrics(study, p) for p in (observed, missing, not_evaluable, not_viewed)]
    group = group_metrics(rows)["groups"][1]
    grouped = group["h5"]
    assert group["participant_count"] == 4
    assert grouped["viewed_count"] == 3
    assert grouped["eligible_count"] == 2
    assert grouped["valid_response_count"] == grouped["n"] == 1
    assert grouped["missing_count"] == 1
    assert grouped["not_applicable_count"] == 2
    assert grouped["not_evaluable_count"] == 1
    assert grouped["not_viewed_count"] == 1

    exported = write_metrics_csv(tmp_path / "h5-denominators.csv", rows, grouped=True)
    records = list(csv.DictReader(exported.open(encoding="utf-8-sig")))
    summary = next(record for record in records if record["metric"] == "h5" and record["group_condition"] == "proposed")
    assert summary["eligible_count"] == "2"
    assert summary["missing_count"] == "1"
    details = json.loads(summary["details_json"])
    assert details["valid_response_count"] == 1
    assert details["not_evaluable_count"] == 1
    assert details["not_viewed_count"] == 1


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
        for table, column in (("participants", "protocol_id"), ("participants", "consent_document_version"),
                              ("participants", "consented_at"), ("participant_surveys", "survey_version"),
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
    created = client.post("/api/participants", json={"assignment_code": "A", "consent_checked": True, "research_code": new_research_code()})
    assert created.status_code == 200
    pid = created.json()["participant_id"]
    assert created.json()["current_step"] == "presurvey"
    assert client.get(f"/api/participants/{pid}/current-step").json()["next_url"] == "/presurvey"
    assert client.get(f"/api/experiment/{pid}/pretest").status_code == 409
    presurvey_context = client.get(f"/api/participants/{pid}/presurvey").json()
    assert presurvey_context["survey_version"] in {PRESURVEY_VERSION, "presurvey-four-topic-baseline-v3"}
    assert len(presurvey_context["term_items"]) == 6
    baseline = baseline_questionnaire(
        presurvey_context["survey_version"],
        [item["key"] for item in presurvey_context["term_items"]],
    )
    invalid_baseline = json.loads(json.dumps(baseline))
    invalid_baseline["prior_term_exposure"].pop("rag" if "rag" in invalid_baseline["prior_term_exposure"] else "transformer")
    assert client.post(f"/api/participants/{pid}/presurvey", json=invalid_baseline).status_code == 422
    saved_baseline = client.post(f"/api/participants/{pid}/presurvey", json=baseline, headers={"Idempotency-Key": f"presurvey-{pid}"})
    assert saved_baseline.status_code == 200, saved_baseline.text
    assert saved_baseline.json()["next_url"] == "/pretest"
    assert client.get(f"/api/participants/{pid}/current-step").json()["step"] == "pretest"
    assert client.post(f"/api/participants/{pid}/presurvey", json=baseline, headers={"Idempotency-Key": f"presurvey-{pid}"}).json() == saved_baseline.json()
    changed_baseline = json.loads(json.dumps(baseline))
    changed_baseline["general_ratings"]["ai_usage_frequency_30d"] = "21_30_days"
    assert client.post(f"/api/participants/{pid}/presurvey", json=changed_baseline).status_code == 409
    assert client.get(f"/api/participants/{pid}/survey").json()["material_ratings_required"] is False
    assert client.get(f"/api/participants/{pid}/survey").json()["survey_version"] == "posttest-5point-v3"
    with SessionLocal() as db:
        p = db.get(Participant, pid)
        assert p.protocol_id == CURRENT_PROTOCOL_ID
        p.current_step = "survey"
        db.commit()
    invalid = questionnaire(True)
    assert client.post(f"/api/participants/{pid}/survey", json=invalid).status_code == 422
    old_version_payload = questionnaire()
    old_version_payload["survey_version"] = "posttest-5point-v2"
    assert client.post(f"/api/participants/{pid}/survey", json=old_version_payload).status_code == 422
    payload = questionnaire()
    payload.pop("free_comment")
    saved = client.post(f"/api/participants/{pid}/survey", json=payload, headers={"Idempotency-Key": f"survey-{pid}"})
    assert saved.status_code == 200, saved.text
    replay = client.post(f"/api/participants/{pid}/survey", json=payload, headers={"Idempotency-Key": f"survey-{pid}"})
    assert replay.json() == saved.json()
    logs = client.get(f"/api/admin/participants/{pid}/logs").json()
    assert [(row["phase"], row["survey_version"]) for row in logs["surveys"]] == [("presurvey", presurvey_context["survey_version"]), ("posttest", SURVEY_VERSION)]
    baseline_log, posttest_log = logs["surveys"]
    assert baseline_log["responses"]["prior_term_exposure"] == baseline["prior_term_exposure"]
    assert baseline_log["responses"]["prior_term_understanding"] == baseline["prior_term_understanding"]
    assert baseline_log["responses"]["general_ratings"] == baseline["general_ratings"]
    assert posttest_log["responses"]["material_rating_status"] == "not_applicable_not_viewed"
    assert posttest_log["ai_experience_level"] is None
    assert posttest_log["free_comment"] is None
    assert "prior_term_exposure" not in posttest_log["responses"]
    assert "prior_term_understanding" not in posttest_log["responses"]
    assert "experiences" not in posttest_log["responses"]
    csv_response = client.get(f"/api/admin/participants/{pid}/logs.csv")
    assert next(csv.reader(csv_response.text.splitlines())) == experiment.LOG_CSV_COLUMNS
    assert CURRENT_PROTOCOL_ID in csv_response.text
    records = csv.DictReader(csv_response.text.splitlines())
    exported_surveys = [json.loads(row["value_json"]) for row in records if row["record_type"] == "survey"]
    assert [row["survey_version"] for row in exported_surveys] == [presurvey_context["survey_version"], SURVEY_VERSION]
    assert exported_surveys[0]["responses"]["prior_term_exposure"] == baseline["prior_term_exposure"]
    assert exported_surveys[0]["responses"]["prior_term_understanding"] == baseline["prior_term_understanding"]
    assert "prior_term_exposure" not in exported_surveys[1]["responses"]
    assert exported_surveys[1]["free_comment"] is None
    for name in ("hypothesis_metrics", "hypothesis_group_summary"):
        assert client.get(f"/api/admin/export/{name}.csv").status_code == 200
