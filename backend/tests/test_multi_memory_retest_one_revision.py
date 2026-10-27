from copy import deepcopy
import hashlib
import json

import pytest
import yaml
from admin_client import AuthenticatedTestClient as TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID
from app.core.question_sets import ASSESSMENT_BANK_VERSIONS, HISTORICAL_ASSESSMENT_BANK_VERSIONS, LEARNING_CONTENT_VERSIONS, assessment_construct_key
from app.db import session as database
from app.db.session import SessionLocal
from app.main import app
from app.models import Attempt, Base, EvaluationSummary, Participant, Question, QuestionOption, Term, TutorSession, TutorTurn
from app.seed import content_loader
from app.seed.content_loader import assessment_question_spec, learning_question_spec, load_content
from app.seed.seed_questions import _upsert_question, seed_database
from app.services import experiment
from app.services.interaction_history import _test_record, build_interaction_history
from app.services.prefetch import wait_for_prefetch_tasks


CHANGED_CHOICES = {
    "multi_agent": {
        "E": "観光候補担当が選んだ施設について、日程担当が別の候補を求めると役割分担が崩れると考え、移動時間や営業時間が合わない場合も、担当間で候補の見直しを行う仕組みは設けない。",
        "F": "観光候補担当が営業時間に合う施設を選び、移動確認担当が利用できる電車を調べれば、各担当の結果を組み合わせるだけで17時までに出発駅へ戻れると考え、計画全体の時刻は確認しない。"
    },
    "memory_process": {
        "E": "利用者が「今後はピーマンも使ってほしい」と伝えたら、以前の「避けたい」という記録を残して新しい希望を追加し、どちらが現在の希望かを判断する仕組みがなくても、次回はAIが新しい方を使うと考える。",
        "H": "以前AIが提案した「ピーマンを使わない献立」の履歴を保存し、その履歴を、利用者自身が伝えた現在の食材の希望を管理する記憶と同じものとして扱う。",
        "I": "同じ会話で「ピーマンも使ってほしい」と伝えた後の提案に希望が反映されたため、会話中の発言を参照する仕組みを、別の日の新しい会話でも好みを保存・更新する記憶機能と同じものとして扱う。"
    }
}
OLD_PROTOCOL = "experiment-plan-2026-10-27-llm-retest1-v1"


def test_v8_changes_only_five_retest_choices_and_preserves_banks():
    assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[23] == {"standard": "scenario-actions-v7", "easy": "scenario-actions-easy-v1"}
    assert CURRENT_EXPERIMENT_SPEC_VERSION not in HISTORICAL_ASSESSMENT_BANK_VERSIONS
    for path, digest in (
        (content_loader.SCENARIO_ACTIONS_V7_CONTENT_PATH, "315455197bc0b5833dea365845dff6e41c1b47a28db4ad0dcc033545a105cfe4"),
        (content_loader.LEARNING_V14_CONTENT_PATH, "72d37e3ae983758718020ddac5e95ee51fa4e3aade63e4b1936d54f2a8428d0d"),
        (content_loader.EASY_CONTENT_PATH, "9b096d2a275a272e719976e07e007afa5b67423abb1eda4ae0c75a09e966f6bb"),
        (content_loader.LEARNING_EASY_CONTENT_PATH, "586e892f63ab4fd0df1f6cfb1a66fe7630763415e91df1c59cf43830655a1206"),
    ):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    expected = yaml.safe_load(content_loader.SCENARIO_ACTIONS_V7_CONTENT_PATH.read_text(encoding="utf-8"))
    expected["assessment_bank_version"] = "scenario-actions-v8"
    for term in expected["terms"]:
        for label, body in CHANGED_CHOICES.get(term["slug"], {}).items():
            index = ord(label) - ord("A")
            term["questions"]["retest"][0]["choices"][("correct", "M1", "M3")[index // 3]][index % 3] = body
    adopted = yaml.safe_load(content_loader.SCENARIO_ACTIONS_V8_CONTENT_PATH.read_text(encoding="utf-8"))
    assert adopted == expected


@pytest.mark.parametrize("slug", list(CHANGED_CHOICES))
@pytest.mark.parametrize("phase", ["retest", "final_test"])
def test_five_choices_keep_question_body_paragraphs_roles_and_shared_final_test(slug, phase):
    old = yaml.safe_load(content_loader.SCENARIO_ACTIONS_V7_CONTENT_PATH.read_text(encoding="utf-8"))
    variant = next(term for term in old["terms"] if term["slug"] == slug)["questions"]["retest"][0]
    spec = assessment_question_spec(slug, phase, 1)
    assert spec["body"] == variant["scenario"] + "\n\n" + variant["task"]
    assert len(spec["body"].split("\n\n")) == (4 if slug == "multi_agent" else 2)
    assert spec["variant_key"] == "retest_v1"
    previous = content_loader._assessment_options(variant)
    assert [option for option in spec["options"] if option["label"] not in CHANGED_CHOICES[slug]] == [option for option in previous if option["label"] not in CHANGED_CHOICES[slug]]
    for option in spec["options"]:
        label = option["label"]
        if label in CHANGED_CHOICES[slug]:
            assert option["body"] == CHANGED_CHOICES[slug][label]
        role = "M3" if label in "GHI" else "M1" if label in "DEF" else "unknown" if label == "J" else None
        assert option["misconception_type"] == role
        assert option["is_correct"] == (label in "ABC")
    assert spec["options"][-1] == content_loader.UNKNOWN_OPTION
    assert assessment_question_spec(slug, "final_test")["options"] == assessment_question_spec(slug, "retest")["options"]


def test_missing_standard_bank_does_not_fall_back_to_v7_or_easy(tmp_path, monkeypatch):
    try:
        with monkeypatch.context() as patch:
            patch.setattr(content_loader, "CONTENT_PATH", tmp_path / "missing.yml")
            load_content.cache_clear()
            with pytest.raises(FileNotFoundError):
                load_content()
    finally:
        load_content.cache_clear()


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
        assert question["options"][-1]["label"] == "J" and question["options"][-1]["exclusive"]
        source = assessment_question_spec(question["term_slug"], phase, index)
        chosen = labels if question["term_slug"] == slug else "ABC"
        payload = {"participant_id": pid, "question_id": question["question_id"], "selected_option_ids": _selected(question, source, chosen)}
        headers = {"Idempotency-Key": f"multi-memory-retest1-{phase}-{index}-{question['term_slug']}"}
        first = _ok(client.post("/api/attempts", json=payload, headers=headers))
        assert _ok(client.post("/api/attempts", json=payload, headers=headers)) == first
    return target


def _learn(client, pid, slug):
    session = _ok(client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": slug}))
    turn = _ok(client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}))
    source = learning_question_spec(slug, turn["learning_stage"], turn["practice_question"]["learning_variant_index"])
    result = _ok(client.post(f"/api/tutor-turns/{turn['turn_id']}/respond",
                            json={"selected_option_ids": _selected(turn["practice_question"], source, "ABC")}))
    assert result["is_sufficient"] and result["feedback"]
    wait_for_prefetch_tasks()


@pytest.mark.parametrize("slug", list(CHANGED_CHOICES))
@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
@pytest.mark.parametrize("phase", ["retest", "final_test"])
@pytest.mark.parametrize("labels,expected_type", [("ABC", None), ("ABE", "M1"), ("ABF", "M1"), ("DEF", "M1"), ("ABG", "M3"), ("AEH", "M3"), ("AFI", "M3"), ("GHI", "M3"), ("J", "unknown")])
def test_natural_shared_v1_grading_replay_review_history_and_two_posttest_limit(slug, group, layout, phase, labels, expected_type):
    client = TestClient(app)
    _ok(client.put("/api/admin/question-set", json={"mode": "standard"}))
    created = _ok(client.post("/api/participants", json={"assignment_code": group, "consent_checked": True, "student_number": "MULTI-MEMORY-RETEST1-SYNTHETIC"}))
    pid = created["participant_id"]
    with SessionLocal() as db:
        participant = db.get(Participant, pid)
        participant.option_order_mode = layout
        assert participant.experiment_spec_version == CURRENT_EXPERIMENT_SPEC_VERSION and participant.protocol_id == CURRENT_PROTOCOL_ID
        assert participant.learning_content_version == LEARNING_CONTENT_VERSIONS["standard"]
        db.commit()
    _answer_test(client, pid, slug, "pretest", "ABC" if phase == "final_test" else "DEF")
    _ok(client.post(f"/api/participants/{pid}/diagnose-pretest"))
    if phase == "retest":
        _learn(client, pid, slug)
    question = _answer_test(client, pid, slug, phase, labels)
    assert question["body"] == assessment_question_spec(slug, phase)["body"]
    assert set(CHANGED_CHOICES[slug].values()).issubset({option["body"] for option in question["options"]})
    with SessionLocal() as db:
        attempt = db.query(Attempt).filter_by(participant_id=pid, question_id=question["question_id"]).one()
        assert attempt.is_correct is None and attempt.misconception_type is None
        assert attempt.question_body_snapshot == question["body"]
    score_route = "score-final-test" if phase == "final_test" else "score-retest"
    headers = {"Idempotency-Key": "multi-memory-retest1-score"}
    result = _ok(client.post(f"/api/participants/{pid}/{score_route}", json={}, headers=headers))
    assert _ok(client.post(f"/api/participants/{pid}/{score_route}", json={}, headers=headers)) == result
    assert result["post_pretest_tests_completed"] == 1 and result["post_pretest_test_limit"] == 2
    assert result["next_step"] == ("survey" if expected_type is None else "learning_targets")
    review = _ok(client.get(f"/api/participants/{pid}/learning-targets"))["test_results"]
    assert next(row for row in review["results"] if row["term_slug"] == slug)["question_body"] == question["body"]
    with SessionLocal() as db:
        attempt = db.query(Attempt).filter_by(participant_id=pid, question_id=question["question_id"]).one()
        assert attempt.is_correct == (expected_type is None) and attempt.misconception_type == expected_type
        source = assessment_question_spec(slug, phase)
        selected = [option for option in question["options"] if option["option_id"] in _selected(question, source, labels)]
        assert _test_record(db, attempt)["selected_options"] == [{"label": option["label"], "body": option["body"]} for option in selected]
        term = db.query(Term).filter_by(slug=slug).one()
        record = next(row for row in build_interaction_history(db, pid, term.id) if row["phase"] == phase and row["source_type"] == "test_attempt")
        assert record["question_body"] == question["body"]
        assert db.get(Participant, pid).retest_cycles_completed == (1 if phase == "retest" else 0)
    if expected_type is not None:
        _learn(client, pid, slug)
        second = _answer_test(client, pid, slug, "retest", "GHI", 2)
        assert second["question_id"] != question["question_id"]
        ended = _ok(client.post(f"/api/participants/{pid}/score-retest", json={}))
        assert ended["post_pretest_tests_completed"] == 2 and ended["next_step"] == "survey"
        with SessionLocal() as db:
            assert db.query(Attempt).filter_by(participant_id=pid).count() == 9
            latest = db.query(Attempt).filter_by(participant_id=pid, question_id=second["question_id"]).one()
            assert not latest.is_correct and latest.misconception_type == "M3"
    assert client.get(f"/api/experiment/{pid}/retest").status_code == 409


@pytest.mark.parametrize("slug", list(CHANGED_CHOICES))
@pytest.mark.parametrize("phase", ["retest", "final_test"])
@pytest.mark.parametrize("snapshot", [False, True])
def test_old_spec23_v7_records_survive_seed_repair_and_missing_snapshot_restore(tmp_path, monkeypatch, slug, phase, snapshot):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    monkeypatch.setattr(database, "engine", engine)
    Base.metadata.create_all(engine)
    old = yaml.safe_load(content_loader.SCENARIO_ACTIONS_V7_CONTENT_PATH.read_text(encoding="utf-8"))
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
                                         construct_key=assessment_construct_key(term.slug, stored_phase, bank_version="scenario-actions-v7"),
                                         variant_key=variant["variant_key"],
                                         options=[(option["label"], option["body"], option["is_correct"], option["misconception_type"]) for option in content_loader._assessment_options(variant)])
            term = db.query(Term).filter_by(slug=slug).one()
            question = db.query(Question).filter_by(term_id=term.id, phase=phase, variant_key="retest_v1").one()
            old_label = "E" if slug == "multi_agent" else "H"
            option = db.query(QuestionOption).filter_by(question_id=question.id, option_label=old_label).one()
            participant = Participant(display_code="V7-HISTORY", group_condition="control", current_step="learning_targets",
                                      question_set_mode="standard", learning_content_version=14, experiment_spec_version=23,
                                      protocol_id=OLD_PROTOCOL, retest_cycles_completed=0 if phase == "final_test" else 1)
            db.add(participant)
            db.flush()
            attempt = Attempt(participant_id=participant.id, term_id=term.id, question_id=question.id, phase=phase,
                              test_round="retest_1", is_correct=False, misconception_type="M1" if slug == "multi_agent" else "M3", selected_option_ids=[option.id],
                              question_body_snapshot="保存時の問題" if snapshot else None,
                              option_order_snapshot=[{"option_id": option.id, "label": "B", "body": "保存時の選択肢"}] if snapshot else None)
            session = TutorSession(participant_id=participant.id, term_id=term.id, group_condition="control", session_index=1)
            db.add(session)
            db.flush()
            turn = TutorTurn(tutor_session_id=session.id, turn_index=1, teaching_strategy="general_explanation", tutor_message="保存済み教材",
                             practice_question_json={"body": "保存済み確認問題", "options": []}, diagnosis_json={"learning_content_version": 14},
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
            active = db.query(Question).filter_by(term_id=term.id, phase=phase, variant_key="retest_v1", is_active=True).all()
            assert len(active) == 2 and all(row.id != question.id for row in active)
            assert db.query(Question).count() == 36
            assert db.query(Question).filter_by(is_active=True).count() == 24
            before_json = json.dumps([attempt.question_body_snapshot, attempt.option_order_snapshot], sort_keys=True)
            record = _test_record(db, attempt)
            assert record["question_body"] == ("保存時の問題" if snapshot else question.body)
            assert record["selected_options"] == [{"label": "B" if snapshot else old_label, "body": "保存時の選択肢" if snapshot else option.body}]
            restored = experiment._test_result_question(db, participant, term, "retest_1", phase)
            assert restored.id == question.id
            review = experiment.latest_test_results(db, participant.id)
            row = next(row for row in review["results"] if row["term_slug"] == slug)
            assert row["question_body"] == record["question_body"]
            assert json.dumps([attempt.question_body_snapshot, attempt.option_order_snapshot], sort_keys=True) == before_json
    finally:
        engine.dispose()
