from __future__ import annotations

from collections import Counter
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from admin_client import AuthenticatedTestClient
from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID
from app.core.question_sets import (
    ASSESSMENT_BANK_VERSIONS,
    ASSESSMENT_MODE_BANK_VERSIONS,
    HISTORICAL_ASSESSMENT_BANK_VERSIONS,
    HISTORICAL_ASSESSMENT_BANK_PROTOCOL_VERSIONS,
    LEARNING_CONTENT_VERSIONS,
    STANDARD,
    assessment_bank_for_participant,
    historical_assessment_bank_versions_for,
)
from app.db.session import get_db
from app.main import app
from app.models import Attempt, Base, Participant, ParticipantSurvey, Question, QuestionOption, Term
from app.seed.content_loader import ACTIVE_TERM_SLUGS, FOUR_TOPIC_TERM_SLUGS, assessment_question_spec, four_topic_terms, learning_question_spec, load_content, load_learning_content
from app.seed.seed_questions import seed_database
from app.services.hypothesis_metrics import group_metrics, metrics_export_rows
from app.services.split_assessment import learning_spec, split_bank, split_specs
from split_api_support import complete_presurvey, new_research_code


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
        "four_topic_fundamentals": "split-actions-four-topic-v3",
    }
    assert LEARNING_CONTENT_VERSIONS == {STANDARD: 15}
    assert all(set(banks) == {STANDARD} for banks in HISTORICAL_ASSESSMENT_BANK_VERSIONS.values())
    assert len(load_content()["terms"]) == len(ACTIVE_TERM_SLUGS)
    assert len(load_learning_content()["terms"]) == len(ACTIVE_TERM_SLUGS)
    for slug in ACTIVE_TERM_SLUGS:
        assert assessment_question_spec(slug, "pretest")["body"]
    four_topics = four_topic_terms()
    historical_four_topics = four_topic_terms("split-actions-four-topic-v1")
    previous_four_topics = four_topic_terms("split-actions-four-topic-v2")
    assert tuple(term["slug"] for term in four_topics) == FOUR_TOPIC_TERM_SLUGS
    assert all(len(term["options"]) == 10 for term in four_topics)
    assert all([option["role"] for option in term["options"]] == ["correct"] * 3 + ["M1"] * 3 + ["M3"] * 3 + ["unknown"] for term in four_topics)
    assert "指示チューニング" in historical_four_topics[1]["options"][1]["body"]
    assert "ファインチューニング" in previous_four_topics[1]["options"][1]["body"]
    assert "インストラクションチューニング" in four_topics[1]["options"][1]["body"]
    assert "ファインチューニング" not in str(four_topics[1])
    assert "指示チューニング" not in str(four_topics[1])
    assert len(split_specs("llm_training_stages", "pretest_v1", "split-actions-four-topic-v1")[0]["options"]) == 10
    assert len(split_specs("llm_training_stages", "pretest_v1", "split-actions-four-topic-v2")[0]["options"]) == 10
    assert len(split_specs("llm_training_stages", "pretest_v1", "split-actions-four-topic-v3")[0]["options"]) == 10
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
        assert db.query(Question).count() == 63
        assert db.query(QuestionOption).count() == 522
        historical_questions = db.query(Question).filter(
            Question.construct_key.endswith("split-actions-four-topic-v1")
        ).all()
        current_four_topic_questions = db.query(Question).filter(
            Question.construct_key.endswith("split-actions-four-topic-v3")
        ).all()
        previous_four_topic_questions = db.query(Question).filter(
            Question.construct_key.endswith("split-actions-four-topic-v2")
        ).all()
        assert len(historical_questions) == 12
        assert all(not question.is_active for question in historical_questions)
        assert len(previous_four_topic_questions) == 12
        assert all(not question.is_active for question in previous_four_topic_questions)
        assert len(current_four_topic_questions) == 12
        assert all(question.is_active for question in current_four_topic_questions)
        for mode, bank in ASSESSMENT_MODE_BANK_VERSIONS.items():
            questions = db.query(Question).filter(Question.construct_key.contains(bank)).all()
            expected_questions = {
                "application": 18,
                "basic_understanding": 9,
                "four_topic_fundamentals": 12,
            }[mode]
            assert len(questions) == expected_questions
            assert all(question.construct_key.endswith(bank) for question in questions)
            for question in questions:
                choices = db.query(QuestionOption).filter_by(question_id=question.id).all()
                expected_roles = Counter({"correct": 3, "M1": 3, "M3": 3, "unknown": 1}) if mode == "four_topic_fundamentals" else Counter({"correct": 1, "M1": 2, "M3": 2, "unknown": 1})
                assert Counter(
                    "correct" if choice.is_correct else choice.misconception_type for choice in choices
                ) == expected_roles
    assert "test_content_mode" in {column["name"] for column in inspect(engine).get_columns("participants")}
    assert "test_content_mode" in {column["name"] for column in inspect(engine).get_columns("runtime_settings")}


def test_old_participant_without_mode_keeps_application_bank():
    class ParticipantSnapshot:
        experiment_spec_version = 42
        test_content_mode = None

    assert assessment_bank_for_participant(ParticipantSnapshot()) == "split-actions-v5"


def test_version_43_without_mode_restores_default_bank_without_mutating_snapshot():
    participant = {
        "experiment_spec_version": 43,
        "protocol_id": "experiment-plan-2026-11-08-basic-understanding-question-mode-v1",
        "test_content_mode": None,
    }

    assert assessment_bank_for_participant(participant) == "split-actions-v5"
    assert historical_assessment_bank_versions_for(participant) == {STANDARD: "split-actions-v5"}
    assert participant["test_content_mode"] is None


@pytest.mark.parametrize(
    "mode,expected_bank",
    [
        ("application", "split-actions-v5"),
        ("basic_understanding", "split-actions-basic-v1"),
        ("four_topic_fundamentals", "split-actions-four-topic-v1"),
    ],
)
def test_version_44_restores_its_saved_mode(mode, expected_bank):
    participant = {
        "experiment_spec_version": 44,
        "protocol_id": "experiment-plan-2026-11-09-four-topic-foundation-v1",
        "test_content_mode": mode,
    }

    assert assessment_bank_for_participant(participant) == expected_bank
    assert historical_assessment_bank_versions_for(participant) == {STANDARD: expected_bank}


def test_version_49_restores_the_historical_four_topic_bank():
    participant = {
        "experiment_spec_version": 49,
        "protocol_id": "experiment-plan-2026-11-10-posttest-five-point-evaluation-v1",
        "test_content_mode": "four_topic_fundamentals",
    }

    assert assessment_bank_for_participant(participant) == "split-actions-four-topic-v1"
    assert historical_assessment_bank_versions_for(participant) == {
        STANDARD: "split-actions-four-topic-v1"
    }


@pytest.mark.parametrize(
    "protocol_id,expected_bank",
    [
        ("experiment-plan-2026-11-11-four-topic-finetuning-terminology-v1", "split-actions-four-topic-v2"),
        ("experiment-plan-2026-11-11-presurvey-finetuning-posttest-material-amount-v1", "split-actions-four-topic-v2"),
        ("experiment-plan-2026-11-11-posttest-material-amount-wording-v1", "split-actions-four-topic-v1"),
    ],
)
def test_spec_50_protocol_variants_restore_their_saved_four_topic_bank(protocol_id, expected_bank):
    participant = {
        "experiment_spec_version": 50,
        "protocol_id": protocol_id,
        "test_content_mode": "four_topic_fundamentals",
    }

    assert assessment_bank_for_participant(participant) == expected_bank
    assert historical_assessment_bank_versions_for(participant) == {STANDARD: expected_bank}


def test_spec_51_posttest_protocol_restores_the_pre_instruction_tuning_bank():
    participant = {
        "experiment_spec_version": 51,
        "protocol_id": "experiment-plan-2026-11-12-posttest-material-amount-wording-v1",
        "test_content_mode": "four_topic_fundamentals",
    }

    assert assessment_bank_for_participant(participant) == "split-actions-four-topic-v2"
    assert historical_assessment_bank_versions_for(participant) == {
        STANDARD: "split-actions-four-topic-v2"
    }


def test_spec_51_instruction_tuning_protocol_restores_its_saved_bank():
    participant = {
        "experiment_spec_version": 51,
        "protocol_id": "experiment-plan-2026-11-12-four-topic-instruction-tuning-terminology-v1",
        "test_content_mode": "four_topic_fundamentals",
    }

    assert assessment_bank_for_participant(participant) == "split-actions-four-topic-v3"
    assert historical_assessment_bank_versions_for(participant) == {
        STANDARD: "split-actions-four-topic-v3"
    }


def test_current_version_requires_saved_mode_and_is_not_in_historical_bank_map():
    participant = {
        "experiment_spec_version": CURRENT_EXPERIMENT_SPEC_VERSION,
        "protocol_id": CURRENT_PROTOCOL_ID,
        "test_content_mode": None,
    }

    assert CURRENT_EXPERIMENT_SPEC_VERSION not in HISTORICAL_ASSESSMENT_BANK_VERSIONS
    assert (CURRENT_EXPERIMENT_SPEC_VERSION, participant["protocol_id"]) not in HISTORICAL_ASSESSMENT_BANK_PROTOCOL_VERSIONS
    assert historical_assessment_bank_versions_for(participant) is None
    with pytest.raises(ValueError, match="no supported test content mode"):
        assessment_bank_for_participant(participant)
    assert participant["test_content_mode"] is None

    participant["test_content_mode"] = "four_topic_fundamentals"
    assert assessment_bank_for_participant(participant) == "split-actions-four-topic-v3"
    assert historical_assessment_bank_versions_for(participant) == {
        STANDARD: "split-actions-four-topic-v3"
    }


def test_current_result_restoration_rejects_missing_mode_snapshot(isolated):
    _client, factory, _engine = isolated
    from app.services.experiment import _test_result_question

    with factory() as db:
        participant = Participant(
            display_code="MISSING-MODE-SNAPSHOT",
            group_condition="control",
            experiment_spec_version=CURRENT_EXPERIMENT_SPEC_VERSION,
            protocol_id=CURRENT_PROTOCOL_ID,
            test_content_mode=None,
        )
        db.add(participant)
        db.flush()
        term = db.query(Term).filter_by(slug="memory_process").one()

        with pytest.raises(HTTPException) as error:
            _test_result_question(db, participant, term, "test", "pretest")

    assert error.value.status_code == 503
    assert error.value.detail["error_code"] == "assessment_bank_unavailable"


def test_version_44_without_mode_restores_historical_default_bank():
    participant = {"experiment_spec_version": 44, "test_content_mode": None}

    assert assessment_bank_for_participant(participant) == "split-actions-v5"
    assert historical_assessment_bank_versions_for(participant) == {STANDARD: "split-actions-v5"}


@pytest.mark.parametrize(
    "protocol_id,expected_bank",
    [
        ("experiment-plan-2026-11-09-four-topic-two-retest-rounds-v1", "split-actions-v5"),
        ("experiment-plan-2026-11-09-four-topic-foundation-default-v1", "split-actions-four-topic-v1"),
    ],
)
def test_version_45_without_mode_restores_protocol_specific_bank(protocol_id, expected_bank):
    participant = {
        "experiment_spec_version": 45,
        "protocol_id": protocol_id,
        "test_content_mode": None,
    }

    assert assessment_bank_for_participant(participant) == expected_bank
    assert historical_assessment_bank_versions_for(participant) == {STANDARD: expected_bank}


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
        "mode": "four_topic_fundamentals",
        "label": "4用語版",
        "applies_to": "new_participants_only",
    }
    assert client.put("/api/admin/test-content-mode", json={"mode": "invalid"}).status_code == 422
    assert client.put("/api/admin/test-content-mode", json={"mode": "application", "extra": True}).status_code == 422

    created_ids = []
    presurvey_contexts = {}

    def create_participant(_fixture_label: str) -> str:
        response = client.post("/api/participants", json={
            "assignment_code": "A", "consent_checked": True, "research_code": new_research_code(),
        })
        assert response.status_code == 200, response.text
        participant_id = response.json()["participant_id"]
        created_ids.append(participant_id)
        presurvey_contexts[participant_id] = client.get(
            f"/api/participants/{participant_id}/presurvey"
        ).json()
        complete_presurvey(client, participant_id)
        return participant_id

    try:
        default_id = create_participant("FOUR-TOPIC-DEFAULT-SNAPSHOT-TEST")
        with factory() as db:
            default_participant = db.get(Participant, default_id)
            assert default_participant.test_content_mode == "four_topic_fundamentals"
            assert default_participant.experiment_spec_version == CURRENT_EXPERIMENT_SPEC_VERSION == 52
            assert default_participant.protocol_id == CURRENT_PROTOCOL_ID == "experiment-plan-2026-11-12-four-topic-instruction-tuning-posttest-material-amount-v1"
            default_survey = db.query(ParticipantSurvey).filter_by(
                participant_id=default_id, phase="presurvey"
            ).one()
            assert default_survey.survey_version == "presurvey-four-topic-baseline-v4"
        default_response = client.get(f"/api/experiment/{default_id}/pretest")
        assert default_response.status_code == 200, default_response.text
        default_questions = default_response.json()["questions"]
        assert [question["term_slug"] for question in default_questions] == list(FOUR_TOPIC_TERM_SLUGS)
        assert len(default_questions) == 4
        default_context = presurvey_contexts[default_id]
        assert default_context["survey_version"] == "presurvey-four-topic-baseline-v4"
        assert [item["key"] for item in default_context["term_items"]] == [
            "transformer", "pretraining", "instruction_tuning", "human_feedback_post_training", "multi_agent", "memory_process",
        ]

        saved = client.put("/api/admin/test-content-mode", json={"mode": "basic_understanding"})
        assert saved.status_code == 200
        assert saved.json()["mode"] == "basic_understanding"
        basic_id = create_participant("BASIC-MODE-SNAPSHOT-TEST")
        basic_context = presurvey_contexts[basic_id]
        assert basic_context["survey_version"] == "presurvey-baseline-v4"
        assert [item["key"] for item in basic_context["term_items"]] == [
            "pretraining", "fine_tuning", "rag", "prompt_engineering", "multi_agent", "memory_process",
        ]
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
        application_context = presurvey_contexts[application_id]
        assert application_context == basic_context
        application_questions = client.get(f"/api/experiment/{application_id}/pretest").json()["questions"]
        assert len(application_questions) == 3
        assert "最新の取扱説明書を参照する方法" in application_questions[0]["body"]

        saved = client.put("/api/admin/test-content-mode", json={"mode": "four_topic_fundamentals"})
        assert saved.status_code == 200
        four_id = create_participant("FOUR-TOPIC-MODE-SNAPSHOT-TEST")
        with factory() as db:
            presurvey_record = db.query(ParticipantSurvey).filter_by(
                participant_id=four_id, phase="presurvey"
            ).one()
            assert presurvey_record.survey_version == "presurvey-four-topic-baseline-v4"
        four_questions = client.get(f"/api/experiment/{four_id}/pretest").json()["questions"]
        assert [question["term_slug"] for question in four_questions] == list(FOUR_TOPIC_TERM_SLUGS)
        assert len(four_questions) == 4
        assert all(
            "is_correct" not in option and "misconception_type" not in option
            for question in four_questions
            for option in question["options"]
        )
        assert all(len(question["options"]) == 10 for question in four_questions)
        assert all(question["selection_mode"] == "multiple" and question["min_selections"] == 3 and question["max_selections"] == 3 for question in four_questions)
        assert all(question["options"][-1]["exclusive"] for question in four_questions)
        for phase in ("retest",):
            with factory() as db:
                participant = db.get(Participant, four_id)
                participant.current_step = "retest"
                participant.retest_cycles_completed = 0
                db.commit()
            round_questions = client.get(f"/api/experiment/{four_id}/{phase}").json()["questions"]
            assert len(round_questions) == 4
            assert [(question["term_slug"], question["body"]) for question in round_questions] == [
                (question["term_slug"], question["body"]) for question in four_questions
            ]
            assert [set(option["body"] for option in question["options"]) for question in round_questions] == [
                set(option["body"] for option in question["options"]) for question in four_questions
            ]
        with factory() as db:
            participant = db.get(Participant, four_id)
            participant.current_step = "final_test"
            db.commit()
        assert client.get(f"/api/experiment/{four_id}/final-test").status_code == 409

        with factory() as db:
            participant = db.get(Participant, four_id)
            participant.current_step = "pretest"
            participant.retest_cycles_completed = 0
            db.commit()
        desired_roles = ["mixed_m3", "unknown", "c_e_h", "correct"]
        for question, desired in zip(four_questions, desired_roles, strict=True):
            with factory() as db:
                source_options = db.query(QuestionOption).filter_by(question_id=question["question_id"]).all()
                if desired == "correct":
                    selected_ids = {option.id for option in source_options if option.is_correct}
                elif desired == "unknown":
                    selected_ids = {option.id for option in source_options if option.misconception_type == "unknown"}
                elif desired == "c_e_h":
                    selected_ids = {option.id for option in source_options if option.option_label in {"C", "E", "H"}}
                else:
                    selected_ids = {option.id for option in source_options if option.is_correct}
                    selected_ids.remove(next(iter(selected_ids)))
                    selected_ids.add(next(option.id for option in source_options if option.misconception_type == "M3"))
                displayed_ids = [option["option_id"] for option in question["options"] if option["option_id"] in selected_ids]
                correct_ids = {option.id for option in source_options if option.is_correct}
                invalid_ids = [option["option_id"] for option in question["options"] if option["option_id"] in correct_ids][:2]
                correct_option_id = next(option["option_id"] for option in question["options"] if option["option_id"] in correct_ids)
                unknown_option_id = next(option["option_id"] for option in question["options"] if option["label"] == "J")
            page_body = {
                "participant_id": four_id,
                "phase": "pretest",
                "term_slug": question["term_slug"],
                "test_round": question["test_round"],
                "page_id": f"00000000-0000-4000-8000-{len(question['question_id']):012d}",
                "answers": [{"question_id": question["question_id"], "selected_option_ids": invalid_ids}],
                "question_shown_at": "2026-11-09T00:00:00Z",
                "answered_at": "2026-11-09T00:00:02Z",
                "elapsed_time_sec": 2,
            }
            invalid = client.post("/api/attempts/term-page", json=page_body, headers={"Idempotency-Key": f"invalid-{question['question_id']}"})
            assert invalid.status_code == 400
            page_body["answers"][0]["selected_option_ids"] = [correct_option_id, unknown_option_id]
            invalid_unknown_combo = client.post("/api/attempts/term-page", json=page_body, headers={"Idempotency-Key": f"invalid-unknown-{question['question_id']}"})
            assert invalid_unknown_combo.status_code == 400, "unknown must be selected alone"
            page_body["answers"][0]["selected_option_ids"] = displayed_ids
            response = client.post("/api/attempts/term-page", json=page_body, headers={"Idempotency-Key": f"valid-{question['question_id']}"})
            assert response.status_code == 200, response.text
            review = client.get(f"/api/experiment/{four_id}/pretest").json()["pending_question_review"]
            assert review["term_slug"] == question["term_slug"]
            assert review["results"][0]["is_correct"] is (desired == "correct")
            assert len(review["results"][0]["selected_options"]) == len(displayed_ids)
            selected_review = review["results"][0]["selected_options"]
            assert [option["option_id"] for option in selected_review] == [str(option_id) for option_id in displayed_ids]
            assert all({"option_id", "label", "body", "is_correct"} <= set(option) for option in selected_review)
            with factory() as db:
                correct_by_id = {
                    str(option.id): bool(option.is_correct)
                    for option in db.query(QuestionOption).filter_by(question_id=question["question_id"]).all()
                }
            assert {option["option_id"]: option["is_correct"] for option in selected_review} == {
                str(option_id): correct_by_id[str(option_id)] for option_id in displayed_ids
            }
            if desired == "c_e_h":
                assert {option["label"]: option["is_correct"] for option in selected_review} == {
                    "C": True,
                    "E": False,
                    "H": False,
                }
                assert review["results"][0]["is_correct"] is False
            ack = client.post(f"/api/participants/{four_id}/question-review-acknowledgements", json={"phase": "pretest", "term_slug": question["term_slug"]})
            assert ack.status_code == 200, ack.text
        diagnosed = client.post(f"/api/participants/{four_id}/diagnose-pretest", json={})
        assert diagnosed.status_code == 200, diagnosed.text
        with factory() as db:
            participant = db.get(Participant, four_id)
            assert participant.test_content_mode == "four_topic_fundamentals"
            assert participant.current_step == "learning_targets"
            assert db.query(Attempt).filter_by(participant_id=four_id, phase="pretest", is_correct=True).count() == 1
            transformer = db.query(Term).filter_by(slug="transformer").one()
            confirmation = learning_spec(db, participant, transformer)
            assert confirmation["selection_mode"] == "multiple"
            assert confirmation["min_selections"] == confirmation["max_selections"] == 3
            assert len(confirmation["questions"]) == 1
            assert len(confirmation["questions"][0]["options"]) == 10
            assert confirmation["questions"][0]["question_id"] == four_questions[0]["question_id"]
            source = next(term for term in four_topic_terms() if term["slug"] == transformer.slug)
            learning_question = learning_question_spec(transformer.slug, "enrichment", 1)
            assert learning_question["body"] == source["question"]
            assert {option["label"]: option["body"] for option in learning_question["options"]} == {
                option["label"]: option["body"] for option in source["options"]
            }
            assert Counter("correct" if option["is_correct"] else option["misconception_type"] for option in learning_question["options"]) == Counter({"correct": 3, "M1": 3, "M3": 3, "unknown": 1})
            for source in four_topic_terms():
                generated_spec = learning_question_spec(source["slug"], "enrichment", 1)
                assert generated_spec["body"] == source["question"]
                assert {option["label"]: option["body"] for option in generated_spec["options"]} == {
                    option["label"]: option["body"] for option in source["options"]
                }
            for question, desired in zip(four_questions, desired_roles, strict=True):
                if desired == "correct":
                    continue
                term = db.query(Term).filter_by(slug=question["term_slug"]).one()
                confirmation = learning_spec(db, participant, term)
                assert confirmation["selection_mode"] == "multiple"
                assert confirmation["questions"][0]["question_id"] == question["question_id"]
                assert {option["label"]: option["body"] for option in confirmation["options"]} == {
                    option["label"]: option["body"] for option in question["options"]
                }

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
        assert by_id[four_id]["test_content_mode_label"] == "4用語版"
    finally:
        for participant_id in created_ids:
            response = client.delete(f"/api/admin/participants/{participant_id}")
            assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    "wrong_by_round",
    [
        ({FOUR_TOPIC_TERM_SLUGS[0]}, {FOUR_TOPIC_TERM_SLUGS[1]}, {FOUR_TOPIC_TERM_SLUGS[2]}),
        ({FOUR_TOPIC_TERM_SLUGS[2]}, set(), {FOUR_TOPIC_TERM_SLUGS[0]}),
    ],
)
def test_four_topic_mode_runs_learning_and_two_retests_after_pretest_errors(isolated, wrong_by_round):
    client, factory, _engine = isolated
    mode = client.put("/api/admin/test-content-mode", json={"mode": "four_topic_fundamentals"})
    assert mode.status_code == 200, mode.text
    created = client.post("/api/participants", json={
        "assignment_code": "A",
        "consent_checked": True,
        "research_code": new_research_code(),
    })
    assert created.status_code == 200, created.text
    participant_id = created.json()["participant_id"]
    complete_presurvey(client, participant_id)

    def answer_round(phase: str, wrong_slugs: set[str]) -> list[str]:
        path_phase = phase.replace("_", "-")
        questions_response = client.get(f"/api/experiment/{participant_id}/{path_phase}")
        assert questions_response.status_code == 200, questions_response.text
        questions = questions_response.json()["questions"]
        assert [question["term_slug"] for question in questions] == list(FOUR_TOPIC_TERM_SLUGS)
        for question in questions:
            with factory() as db:
                options = db.query(QuestionOption).filter_by(question_id=question["question_id"]).all()
                correct = [option for option in options if option.is_correct]
                selected = correct
                if question["term_slug"] in wrong_slugs:
                    m1 = next(option for option in options if option.misconception_type == "M1")
                    selected = [*correct[:2], m1]
                selected_ids = [str(option.id) for option in selected]
            payload = {
                "participant_id": participant_id,
                "phase": phase,
                "term_slug": question["term_slug"],
                "test_round": question["test_round"],
                "page_id": str(uuid4()),
                "answers": [{"question_id": question["question_id"], "selected_option_ids": selected_ids}],
                "question_shown_at": "2026-11-09T00:00:00Z",
                "answered_at": "2026-11-09T00:00:02Z",
                "elapsed_time_sec": 2,
            }
            saved = client.post(
                "/api/attempts/term-page",
                json=payload,
                headers={"Idempotency-Key": f"{phase}-{question['question_id']}-{uuid4().hex}"},
            )
            assert saved.status_code == 200, saved.text
            review = client.get(f"/api/experiment/{participant_id}/{path_phase}").json()["pending_question_review"]
            if review:
                acknowledged = client.post(
                    f"/api/participants/{participant_id}/question-review-acknowledgements",
                    json={"phase": phase, "term_slug": question["term_slug"]},
                )
                assert acknowledged.status_code == 200, acknowledged.text
        return [slug for slug in FOUR_TOPIC_TERM_SLUGS if slug in wrong_slugs]

    def assert_learning_sessions_available(target_slugs: list[str]) -> None:
        for term_slug in target_slugs:
            session = client.post(
                "/api/tutor-sessions",
                json={"participant_id": participant_id, "term_slug": term_slug},
            )
            assert session.status_code == 200, session.text
            assert session.json()["tutor_session_id"]

    try:
        pretest_wrong = answer_round("pretest", wrong_by_round[0])
        diagnosed = client.post(f"/api/participants/{participant_id}/diagnose-pretest", json={})
        assert diagnosed.status_code == 200, diagnosed.text
        diagnosis = diagnosed.json()
        pretest_targets = pretest_wrong
        assert diagnosis["next_step"] == "learning_targets"
        assert diagnosis["learning_target_slugs"] == pretest_targets
        assert diagnosis["learning_target_count"] == len(pretest_targets)
        targets = client.get(f"/api/participants/{participant_id}/learning-targets")
        assert targets.status_code == 200, targets.text
        assert [row["term_slug"] for row in targets.json()["targets"]] == pretest_targets
        assert_learning_sessions_available(pretest_targets)
        assert client.get(f"/api/experiment/{participant_id}/final-test").status_code == 409
        assert client.post(f"/api/participants/{participant_id}/give-up-learning", json={}).status_code == 200

        first_wrong = answer_round("retest", wrong_by_round[1])
        first_score = client.post(f"/api/participants/{participant_id}/score-retest", json={})
        assert first_score.status_code == 200, first_score.text
        first_result = first_score.json()
        first_targets = first_wrong or list(FOUR_TOPIC_TERM_SLUGS)
        assert first_result["retest_cycles_completed"] == 1
        assert first_result["post_pretest_tests_completed"] == 1
        assert first_result["next_step"] == "learning_targets"
        assert first_result["learning_target_slugs"] == first_targets
        targets = client.get(f"/api/participants/{participant_id}/learning-targets")
        assert targets.status_code == 200, targets.text
        assert [row["term_slug"] for row in targets.json()["targets"]] == first_targets
        assert_learning_sessions_available(first_targets)
        assert client.get(f"/api/experiment/{participant_id}/final-test").status_code == 409
        assert client.post(f"/api/participants/{participant_id}/give-up-learning", json={}).status_code == 200

        answer_round("retest", wrong_by_round[2])
        second_score = client.post(f"/api/participants/{participant_id}/score-retest", json={})
        assert second_score.status_code == 200, second_score.text
        second_result = second_score.json()
        assert second_result["retest_cycles_completed"] == 2
        assert second_result["post_pretest_tests_completed"] == 2
        assert second_result["next_step"] == "survey"
        assert second_result["retest_cycle_limit_reached"] is bool(wrong_by_round[2])
        assert client.get(f"/api/experiment/{participant_id}/retest").status_code == 409
        assert client.get(f"/api/experiment/{participant_id}/final-test").status_code == 409
        current = client.get(f"/api/participants/{participant_id}/current-step")
        assert current.status_code == 200, current.text
        assert current.json()["step"] == "survey"
    finally:
        deleted = client.delete(f"/api/admin/participants/{participant_id}")
        assert deleted.status_code == 200, deleted.text


def test_hypothesis_metrics_are_partitioned_by_test_content_mode():
    from app.services.research_protocol import MATERIAL_RATING_KEYS

    rows = []
    for mode, offset in (("application", 0.1), ("basic_understanding", 0.8), ("four_topic_fundamentals", 0.5)):
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
        "application", "basic_understanding", "four_topic_fundamentals",
    }
    assert all(len(stratum["groups"]) == 2 for stratum in grouped["strata"])
    exported = metrics_export_rows(rows, grouped=True)
    assert {row["test_content_mode"] for row in exported} == {"application", "basic_understanding", "four_topic_fundamentals"}
    four_topic_summary = next(item for item in grouped["strata"] if item["test_content_mode"] == "four_topic_fundamentals")
    assert four_topic_summary["questions_per_test"] == 4


def test_four_topic_material_rag_uses_configured_directory_and_sections(monkeypatch):
    from app.services import experiment as experiment_service

    captured = []
    monkeypatch.setattr(
        experiment_service,
        "retrieve_rag_context",
        lambda query, **kwargs: captured.append({"query": query, **kwargs}) or {},
    )
    for term in four_topic_terms():
        experiment_service._rag_context(term["slug"], term["label"], term["description"])

    assert [row["topic_slug"] for row in captured] == list(FOUR_TOPIC_TERM_SLUGS)
    assert captured[0]["rag_dir"] == "rag_ready_教材"
    assert captured[0]["allowed_sections"] == ["1.1.2.4"]
    assert captured[1]["rag_dir"] == "rag_ready_教材"
    assert captured[1]["allowed_sections"] == ["1.1.3.2"]


def test_basic_mode_routes_each_round_and_reuses_failed_question_snapshot(isolated):
    client, factory, _engine = isolated
    assert client.put("/api/admin/test-content-mode", json={"mode": "basic_understanding"}).status_code == 200
    created = client.post("/api/participants", json={
        "assignment_code": "A", "consent_checked": True, "research_code": new_research_code(),
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
