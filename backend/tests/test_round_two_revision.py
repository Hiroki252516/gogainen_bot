from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
import yaml
from admin_client import AuthenticatedTestClient as TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from split_api_support import assert_retest_flow

from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID
from app.core.question_sets import ASSESSMENT_BANK_VERSIONS, HISTORICAL_ASSESSMENT_BANK_VERSIONS, LEARNING_CONTENT_VERSIONS, assessment_construct_key
from app.db import session as database
from app.db.session import SessionLocal
from app.main import app
from app.models import Attempt, Base, EvaluationSummary, Participant, Question, QuestionOption, Term, TutorSession, TutorTurn
from app.seed import content_loader
from app.seed.content_loader import assessment_question_spec, learning_question_spec, load_content, load_learning_content
from app.seed.seed_questions import _upsert_question, seed_database
from app.services import experiment
from app.services.interaction_history import _test_record, _learning_record
from app.services.prefetch import wait_for_prefetch_tasks


EXPECTED = json.loads((Path(__file__).with_name("fixtures") / "round_two_revision_v25.json").read_text(encoding="utf-8"))
OLD_PROTOCOL = "experiment-plan-2026-10-27-multi-memory-retest1-v1"


def test_v25_exact_banks_and_unchanged_content():
    assert CURRENT_EXPERIMENT_SPEC_VERSION >= 25
    assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[25] == {"standard": "scenario-actions-v9"}
    assert ASSESSMENT_BANK_VERSIONS == {"standard": "split-actions-v5"}
    assert LEARNING_CONTENT_VERSIONS == {"standard": 15}
    assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[24] == {"standard": "scenario-actions-v8"}
    assert CURRENT_EXPERIMENT_SPEC_VERSION not in HISTORICAL_ASSESSMENT_BANK_VERSIONS
    for path, digest in (
        (content_loader.SCENARIO_ACTIONS_V8_CONTENT_PATH, "c07ac0de45d78abba642107842bc14d510ace7751a369d9a12a171fb0141c9ed"),
        (content_loader.LEARNING_V14_CONTENT_PATH, "72d37e3ae983758718020ddac5e95ee51fa4e3aade63e4b1936d54f2a8428d0d"),
    ):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    learning = deepcopy(load_learning_content(content_version=14))
    learning["version"] = 15
    for slug, question in EXPECTED["learning"].items():
        learning["terms"][slug]["variants"][1] = question
    assert load_learning_content() == learning
    assessment = yaml.safe_load(content_loader.SCENARIO_ACTIONS_V8_CONTENT_PATH.read_text(encoding="utf-8"))
    assessment["assessment_bank_version"] = "scenario-actions-v9"
    for term in assessment["terms"]:
        term["questions"]["retest"][1] = EXPECTED["retest"][term["slug"]]
    assert load_content() == assessment


@pytest.mark.parametrize("slug", list(EXPECTED["learning"]))
@pytest.mark.parametrize("stage", ["enrichment", "conceptual_change"])
def test_learning_v2_exact_body_roles_and_application(slug, stage):
    spec = learning_question_spec(slug, stage, 2, content_version=15, use_current_assessment_source=False)
    expected = EXPECTED["learning"][slug]
    assert spec["body"] == expected["scenario"] + "\n\n" + expected["task"]
    assert len(spec["body"].split("\n\n")) == (2 if slug == "llm_knowledge" else 3)
    assert spec["scenario_type"] == "application" and spec["_content_version"] == 15
    assert [option["body"] for option in spec["options"][:9]] == [body for role in expected["choices"].values() for body in role]
    assert spec["options"][-1]["label"] == "J"
    assert learning_question_spec(slug, stage, 2, content_version=14)["scenario_type"] == "prediction"


@pytest.mark.parametrize("slug", list(EXPECTED["retest"]))
def test_retest_v2_exact_body_roles_and_unchanged_final(slug):
    spec = assessment_question_spec(slug, "retest", 2)
    expected = EXPECTED["retest"][slug]
    assert spec["body"] == expected["scenario"] + "\n\n" + expected["task"]
    assert len(spec["body"].split("\n\n")) == {"llm_knowledge": 5, "multi_agent": 4, "memory_process": 2}[slug]
    for role, labels in (("correct", "ABC"), ("M1", "DEF"), ("M3", "GHI")):
        assert [option["body"] for option in spec["options"] if option["label"] in labels] == expected["choices"][role]
        assert all(option["misconception_type"] == (None if role == "correct" else role) for option in spec["options"] if option["label"] in labels)
    assert spec["options"][-1] == content_loader.UNKNOWN_OPTION
    assert assessment_question_spec(slug, "final_test")["body"] == assessment_question_spec(slug, "retest", 1)["body"]
    assert spec["body"] != assessment_question_spec(slug, "final_test")["body"]


@pytest.mark.parametrize("kind", ["learning", "assessment"])
@pytest.mark.parametrize("mutation", ["label", "text", "third_variant", "term", "within_question"])
def test_only_approved_text_locations_may_repeat(kind, mutation):
    content = deepcopy(load_learning_content() if kind == "learning" else load_content())
    if kind == "learning":
        variants = content["terms"]["llm_knowledge"]["variants"]
        other = content["terms"]["multi_agent"]["variants"]
        role, index = "M1", 1
        validate = lambda: content_loader._validate_learning_content(content, load_content())
    else:
        variants = content["terms"][0]["questions"]["retest"]
        other = content["terms"][1]["questions"]["retest"]
        role, index = "M1", 2
        validate = lambda: content_loader._validate_content(content)
    body = variants[0]["choices"][role][index]
    if mutation == "label":
        choices = variants[1]["choices"][role]
        choices[index], choices[0] = choices[0], choices[index]
    elif mutation == "text":
        for variant in variants[:2]:
            variant["choices"][role][index] = body + "変更"
    elif mutation == "third_variant":
        target = variants[2] if kind == "learning" else content["terms"][0]["questions"]["pretest"][0]
        target["choices"][role][index] = body
    elif mutation == "term":
        other[1]["choices"][role][index] = body
    else:
        variants[1]["choices"][role][0] = variants[1]["choices"][role][index]
    with pytest.raises(ValueError):
        validate()


@pytest.mark.parametrize("label,role,index", [("E", "M1", 1), ("G", "M3", 0)])
def test_both_learning_repeat_exceptions_require_exact_locations(label, role, index):
    valid = deepcopy(load_learning_content())
    body = valid["terms"]["llm_knowledge"]["variants"][0]["choices"][role][index]
    assert valid["terms"]["llm_knowledge"]["variants"][1]["choices"][role][index] == body
    valid["terms"]["llm_knowledge"]["variants"][2]["choices"][role][index] = body
    with pytest.raises(ValueError, match="unique across"):
        content_loader._validate_learning_content(valid, load_content())


def test_old_learning_bank_keeps_type_and_reuse_restrictions():
    content = deepcopy(load_learning_content(14))
    content["terms"]["llm_knowledge"]["variants"][1]["scenario_type"] = "application"
    with pytest.raises(ValueError, match="scenario types"):
        content_loader._validate_learning_content(content, load_content(), content_version=14)
    content = deepcopy(load_learning_content(14))
    variants = content["terms"]["llm_knowledge"]["variants"]
    variants[1]["choices"]["M1"][1] = variants[0]["choices"]["M1"][1]
    with pytest.raises(ValueError, match="unique across"):
        content_loader._validate_learning_content(content, load_content(), content_version=14)


def test_assessment_exception_is_not_available_to_old_banks():
    old = deepcopy(load_content())
    old["assessment_bank_version"] = "scenario-actions-v8"
    with pytest.raises(ValueError, match="assessment bank version is invalid"):
        content_loader._validate_content(old)


def test_scenario_override_is_only_for_two_terms_and_two_slots():
    for slug in ("llm_knowledge", "multi_agent", "memory_process"):
        content = deepcopy(load_learning_content())
        content["terms"][slug]["variants"][1]["scenario_type"] = "prediction" if slug != "multi_agent" else "application"
        with pytest.raises(ValueError, match="scenario types"):
            content_loader._validate_learning_content(content, load_content())


def test_fixed_test_copy_is_still_rejected():
    content = deepcopy(load_learning_content())
    content["terms"]["llm_knowledge"]["variants"][1]["choices"]["correct"][0] = EXPECTED["retest"]["llm_knowledge"]["choices"]["correct"][0]
    with pytest.raises(ValueError, match="copies fixed"):
        content_loader._validate_learning_content(content, load_content())


def test_missing_v15_has_no_fallback(tmp_path, monkeypatch):
    try:
        with monkeypatch.context() as patch:
            patch.setattr(content_loader, "LEARNING_V15_CONTENT_PATH", tmp_path / "missing.yml")
            load_learning_content.cache_clear()
            with pytest.raises(FileNotFoundError):
                load_learning_content()
    finally:
        load_learning_content.cache_clear()


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def _selected(question, source, labels):
    bodies = {option["body"] for option in source["options"] if option["label"] in labels}
    return [option["option_id"] for option in question["options"] if option["body"] in bodies]


def _answer_test(client, pid, slug, phase, labels, index=1):
    route = "final-test" if phase == "final_test" else phase
    questions = _ok(client.get(f"/api/experiment/{pid}/{route}"))["questions"]
    target = next(question for question in questions if question["term_slug"] == slug)
    for question in questions:
        assert all(set(option) == {"option_id", "label", "body", "exclusive"} for option in question["options"])
        source = assessment_question_spec(question["term_slug"], phase, index)
        payload = {"participant_id": pid, "question_id": question["question_id"], "selected_option_ids": _selected(question, source, labels if question["term_slug"] == slug else "ABC")}
        headers = {"Idempotency-Key": f"round2-{phase}-{index}-{question['term_slug']}"}
        first = _ok(client.post("/api/attempts", json=payload, headers=headers))
        assert _ok(client.post("/api/attempts", json=payload, headers=headers)) == first
    return target


def _learn(client, pid, slug, expected_index):
    session = _ok(client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": slug}))
    turn = _ok(client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}))
    question = turn["practice_question"]
    assert question["learning_variant_index"] == expected_index
    source = learning_question_spec(slug, turn["learning_stage"], expected_index)
    assert question["body"] == source["body"]
    expected_phase = "pretest" if expected_index == 1 else "retest"
    expected = assessment_question_spec(slug, expected_phase, 1)
    assert question["body"] == expected["body"]
    assert {option["body"] for option in question["options"]} == {option["body"] for option in expected["options"]}
    result = _ok(client.post(f"/api/tutor-turns/{turn['turn_id']}/respond", json={"selected_option_ids": _selected(question, source, "ABC")}))
    assert result["is_sufficient"] and result["feedback"]
    wait_for_prefetch_tasks()


@pytest.mark.parametrize("slug", list(EXPECTED["retest"]))
@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
@pytest.mark.parametrize("labels,expected_type", [("ABC", None), ("DEF", "M1"), ("GHI", "M3"), ("ADH", "M3"), ("J", "unknown")])
def test_natural_round2_routes_grading_replay_review_and_limit(slug, group, layout, labels, expected_type):
    assert_retest_flow(slug, group, layout, "retest", labels, expected_type, round_two=True)


@pytest.mark.parametrize("slug", list(EXPECTED["retest"]))
@pytest.mark.parametrize("snapshot", [False, True])
def test_old_spec24_v8_records_survive_seed_repair_and_missing_snapshot_restore(tmp_path, monkeypatch, slug, snapshot):
    phase = "retest"
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    monkeypatch.setattr(database, "engine", engine)
    Base.metadata.create_all(engine)
    old = yaml.safe_load(content_loader.SCENARIO_ACTIONS_V8_CONTENT_PATH.read_text(encoding="utf-8"))
    try:
        with Session(engine) as db:
            for order, data in enumerate(old["terms"], start=1):
                term = Term(slug=data["slug"], label=data["label"], description=data["description"], display_order=order)
                db.add(term)
                db.flush()
                for stored_phase in ("pretest", "retest", "final_test"):
                    variants = data["questions"]["retest"][:1] if stored_phase == "final_test" else data["questions"][stored_phase]
                    for variant in variants:
                        _upsert_question(db, term, phase=stored_phase, question_type="multi_select",
                                         body=variant["scenario"] + "\n\n" + variant["task"], expected_answer="A、B、Cをすべて選択し、それ以外を選ばない。",
                                         construct_key=assessment_construct_key(term.slug, stored_phase, bank_version="scenario-actions-v8"),
                                         variant_key=variant["variant_key"],
                                         options=[(option["label"], option["body"], option["is_correct"], option["misconception_type"]) for option in content_loader._assessment_options(variant)])
            term = db.query(Term).filter_by(slug=slug).one()
            question = db.query(Question).filter_by(
                term_id=term.id, phase=phase, variant_key="retest_v2",
                construct_key=assessment_construct_key(term.slug, phase, bank_version="scenario-actions-v8"),
            ).one()
            old_label = "H"
            option = db.query(QuestionOption).filter_by(question_id=question.id, option_label=old_label).one()
            participant = Participant(display_code="V8-HISTORY", group_condition="control", current_step="learning_targets",
                                      learning_content_version=14, experiment_spec_version=24,
                                      protocol_id=OLD_PROTOCOL, retest_cycles_completed=0 if phase == "final_test" else 1)
            db.add(participant)
            db.flush()
            attempt = Attempt(participant_id=participant.id, term_id=term.id, question_id=question.id, phase=phase,
                              test_round="retest_2", is_correct=False, misconception_type="M3", selected_option_ids=[option.id],
                              question_body_snapshot="保存時の問題" if snapshot else None,
                              option_order_snapshot=[{"option_id": option.id, "label": "B", "body": "保存時の選択肢"}] if snapshot else None)
            session = TutorSession(participant_id=participant.id, term_id=term.id, group_condition="control", session_index=2)
            db.add(session)
            db.flush()
            turn = TutorTurn(tutor_session_id=session.id, turn_index=1, teaching_strategy="general_explanation", tutor_message="保存済み教材",
                             practice_question_json={"body": "保存済み確認問題", "options": []} if snapshot else {}, diagnosis_json={"learning_content_version": 14},
                             grading_json={"is_sufficient": False}, learner_response="J")
            db.add_all([attempt, turn, EvaluationSummary(participant_id=participant.id, group_condition="control", pretest_score=0.125)])
            db.commit()
            protected = {model: deepcopy(db.execute(select(model.__table__)).mappings().all()) for model in (Participant, Attempt, TutorSession, TutorTurn, EvaluationSummary)}
            questions_before = {row.id: (row.body, row.construct_key, row.variant_key) for row in db.query(Question)}
            options_before = {row.id: (row.body, row.is_correct, row.misconception_type) for row in db.query(QuestionOption)}
            seed_database(db)
            seed_database(db)
            database.init_db()
            database.init_db()
            for model, rows in protected.items():
                assert db.execute(select(model.__table__)).mappings().all() == rows
            for qid, fields in questions_before.items():
                saved = db.get(Question, qid)
                assert (saved.body, saved.construct_key, saved.variant_key) == fields and not saved.is_active
            for oid, fields in options_before.items():
                saved = db.get(QuestionOption, oid)
                assert (saved.body, saved.is_correct, saved.misconception_type) == fields
            active = db.query(Question).filter_by(
                term_id=term.id, phase="retest", is_active=True,
                construct_key=assessment_construct_key(term.slug, "retest", bank_version=ASSESSMENT_BANK_VERSIONS["standard"]),
            ).filter(Question.variant_key.in_(["retest_v2", "retest_v2_q1", "retest_v2_q2"])).all()
            assert len(active) == 2 and all(row.id != question.id for row in active)
            assert db.query(Question).count() == 87
            assert db.query(Question).filter_by(is_active=True).count() == 39
            before_json = json.dumps([attempt.question_body_snapshot, attempt.option_order_snapshot], sort_keys=True)
            record = _test_record(db, attempt)
            assert record["question_body"] == ("保存時の問題" if snapshot else question.body)
            assert record["selected_options"] == [{"label": "B" if snapshot else old_label, "body": "保存時の選択肢" if snapshot else option.body}]
            learning_before = json.dumps([turn.practice_question_json, turn.diagnosis_json, turn.grading_json], sort_keys=True)
            restored_learning = _learning_record(db, session, turn)
            expected_learning = learning_question_spec(slug, "enrichment", 2, content_version=14)
            assert restored_learning["question_body"] == ("保存済み確認問題" if snapshot else expected_learning["body"])
            assert json.dumps([turn.practice_question_json, turn.diagnosis_json, turn.grading_json], sort_keys=True) == learning_before
            restored = experiment._test_result_question(db, participant, term, "retest_2", phase)
            assert restored.id == question.id
            review = experiment.latest_test_results(db, participant.id)
            row = next(row for row in review["results"] if row["term_slug"] == slug)
            assert row["question_body"] == record["question_body"]
            assert json.dumps([attempt.question_body_snapshot, attempt.option_order_snapshot], sort_keys=True) == before_json
    finally:
        engine.dispose()
