from copy import deepcopy
import hashlib
import json

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

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
from app.services.interaction_history import _test_record, build_interaction_history
from app.services.prefetch import wait_for_prefetch_tasks


SCENARIO = "企業が、社員からの「パスワードを忘れた」「社内Wi-Fiにつながらない」「パソコンの電源が入らない」といった問い合わせに対応するAIを開発している。\n\nこのAIは、問い合わせ内容を「アカウント」「ネットワーク」「機器」の3種類に分類し、その分類に応じた対応手順を社員に案内する。\n\n社員への案内は、「確認すること・対応手順・注意点」の順に、わかりやすく説明する形式にそろえたい。\n\nまた、最近、社内の対応手順書が改訂されたため、開発担当者は新しい手順を案内に反映したいと考えている。さらに、担当者が正しく分類した過去の問い合わせ事例を利用して、AIの分類精度も改善したい。"
TASK = "これらの目的を実現するための開発担当者の対応として、適切なものを3つ選びなさい。"
CHANGED_CHOICES = {
    "A": "社員が「社内Wi-Fiにつながらない」と相談したら、改訂後の対応手順書から関係する箇所を検索し、見つけた情報を元に、その内容を参考に案内を作成させる。",
    "B": "社員への回答を「確認すること・対応手順・注意点」の順にそろえるため、AIへ渡す指示文（プロンプト）に説明する項目と順序を指定し、問い合わせへの回答時に利用する。",
    "D": "開発中、「パスワードを忘れた→アカウント」などの分類例を質問に添えるとAIが正しく分類できたため、モデル自体がその分類方法を学習したと考え、新しい会話では例を示さずに分類させる。",
    "G": "担当者が確認した「パスワードを忘れた→アカウント」等の分類例を保存し、問い合わせの度にシステムが似た事例を検索してAIに渡すようにする方法を、モデル自体を追加訓練する仕組みとして扱う。",
    "H": "改訂後の対応手順書を使ってAIを追加訓練し、そのAIが学習した内容から回答する方法を、問い合わせのたびに最新の手順書を検索して確認する方法と同じ仕組みとして扱う。",
    "I": "社員からの質問に応じて「最新版の対応手順書を確認して答える」とAIへの共通指示文（プロンプト）に書き、その指示文を、手順書から必要な箇所を検索して取り出す仕組みと同じものとして扱う。"
}
OLD_PROTOCOL = "experiment-plan-2026-10-27-multi-memory-round1-v1"


def test_v7_changes_only_llm_retest_one_scenario_and_six_choices():
    assert load_learning_content(content_version=14)["version"] == 14
    assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[22] == {"standard": "scenario-actions-v6", "easy": "scenario-actions-easy-v1"}
    assert CURRENT_EXPERIMENT_SPEC_VERSION not in HISTORICAL_ASSESSMENT_BANK_VERSIONS
    for path, digest in (
        (content_loader.SCENARIO_ACTIONS_V6_CONTENT_PATH, "a9161a01940f112b96bdeec37c4243e69009ba463bebca415760f14ea1c59e04"),
        (content_loader.LEARNING_V14_CONTENT_PATH, "72d37e3ae983758718020ddac5e95ee51fa4e3aade63e4b1936d54f2a8428d0d"),
        (content_loader.EASY_CONTENT_PATH, "9b096d2a275a272e719976e07e007afa5b67423abb1eda4ae0c75a09e966f6bb"),
        (content_loader.LEARNING_EASY_CONTENT_PATH, "586e892f63ab4fd0df1f6cfb1a66fe7630763415e91df1c59cf43830655a1206"),
    ):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    expected = yaml.safe_load(content_loader.SCENARIO_ACTIONS_V6_CONTENT_PATH.read_text(encoding="utf-8"))
    expected["assessment_bank_version"] = "scenario-actions-v7"
    question = expected["terms"][0]["questions"]["retest"][0]
    question["scenario"] = SCENARIO
    for label, text in CHANGED_CHOICES.items():
        index = ord(label) - ord("A")
        question["choices"][("correct", "M1", "M3")[index // 3]][index % 3] = text
    adopted = yaml.safe_load(content_loader.SCENARIO_ACTIONS_V7_CONTENT_PATH.read_text(encoding="utf-8"))
    assert adopted == expected


@pytest.mark.parametrize("phase", ["retest", "final_test"])
def test_new_question_has_five_paragraphs_and_unchanged_roles(phase):
    spec = assessment_question_spec("llm_knowledge", phase, 1)
    assert spec["body"] == SCENARIO + "\n\n" + TASK
    assert len(spec["body"].split("\n\n")) == 5
    assert all("\n" not in paragraph for paragraph in spec["body"].split("\n\n"))
    assert "**" not in spec["body"] and "問題：" not in spec["body"]
    assert spec["variant_key"] == "retest_v1"
    old = yaml.safe_load(content_loader.SCENARIO_ACTIONS_V6_CONTENT_PATH.read_text(encoding="utf-8"))
    previous = content_loader._assessment_options(old["terms"][0]["questions"]["retest"][0])
    assert [option for option in spec["options"] if option["label"] not in CHANGED_CHOICES] == [option for option in previous if option["label"] not in CHANGED_CHOICES]
    for option in spec["options"]:
        label = option["label"]
        if label in CHANGED_CHOICES:
            assert option["body"] == CHANGED_CHOICES[label]
        role = "M3" if label in "GHI" else "M1" if label in "DEF" else "unknown" if label == "J" else None
        assert option["misconception_type"] == role
        assert option["is_correct"] == (label in "ABC")
    assert spec["options"][-1] == content_loader.UNKNOWN_OPTION


def test_missing_standard_bank_does_not_fall_back_to_v6_or_easy(tmp_path, monkeypatch):
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


def _answer_test(client, pid, phase, labels, index=1):
    route = "final-test" if phase == "final_test" else phase
    questions = _ok(client.get(f"/api/experiment/{pid}/{route}"))["questions"]
    target = next(question for question in questions if question["term_slug"] == "llm_knowledge")
    for question in questions:
        assert all(set(option) == {"option_id", "label", "body", "exclusive"} for option in question["options"])
        assert question["options"][-1]["label"] == "J" and question["options"][-1]["exclusive"]
        source = assessment_question_spec(question["term_slug"], phase, index)
        chosen = labels if question["term_slug"] == "llm_knowledge" else "ABC"
        payload = {"participant_id": pid, "question_id": question["question_id"], "selected_option_ids": _selected(question, source, chosen)}
        headers = {"Idempotency-Key": f"llm-retest1-{phase}-{index}-{question['term_slug']}"}
        first = _ok(client.post("/api/attempts", json=payload, headers=headers))
        assert _ok(client.post("/api/attempts", json=payload, headers=headers)) == first
    return target


def _learn(client, pid):
    session = _ok(client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "llm_knowledge"}))
    turn = _ok(client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}))
    source = learning_question_spec("llm_knowledge", turn["learning_stage"], turn["practice_question"]["learning_variant_index"])
    result = _ok(client.post(f"/api/tutor-turns/{turn['turn_id']}/respond",
                            json={"selected_option_ids": _selected(turn["practice_question"], source, "ABC")}))
    assert result["is_sufficient"] and result["feedback"]
    wait_for_prefetch_tasks()


@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
@pytest.mark.parametrize("phase", ["retest", "final_test"])
@pytest.mark.parametrize("labels,expected_type", [("ABC", None), ("ABD", "M1"), ("DEF", "M1"), ("ABG", "M3"), ("ADH", "M3"), ("ADI", "M3"), ("GHI", "M3"), ("J", "unknown")])
def test_natural_shared_v1_grading_replay_review_history_and_two_posttest_limit(group, layout, phase, labels, expected_type):
    client = TestClient(app)
    _ok(client.put("/api/admin/question-set", json={"mode": "standard"}))
    created = _ok(client.post("/api/participants", json={"assignment_code": group, "consent_checked": True, "student_number": "LLM-RETEST1-SYNTHETIC"}))
    pid = created["participant_id"]
    with SessionLocal() as db:
        participant = db.get(Participant, pid)
        participant.option_order_mode = layout
        assert participant.experiment_spec_version == CURRENT_EXPERIMENT_SPEC_VERSION and participant.protocol_id == CURRENT_PROTOCOL_ID
        assert participant.learning_content_version == LEARNING_CONTENT_VERSIONS["standard"]
        db.commit()
    _answer_test(client, pid, "pretest", "ABC" if phase == "final_test" else "DEF")
    _ok(client.post(f"/api/participants/{pid}/diagnose-pretest"))
    if phase == "retest":
        _learn(client, pid)
    question = _answer_test(client, pid, phase, labels)
    assert question["body"] == SCENARIO + "\n\n" + TASK
    assert set(CHANGED_CHOICES.values()).issubset({option["body"] for option in question["options"]})
    with SessionLocal() as db:
        attempt = db.query(Attempt).filter_by(participant_id=pid, question_id=question["question_id"]).one()
        assert attempt.is_correct is None and attempt.misconception_type is None
        assert attempt.question_body_snapshot == question["body"]
    score_route = "score-final-test" if phase == "final_test" else "score-retest"
    headers = {"Idempotency-Key": "llm-retest1-score"}
    result = _ok(client.post(f"/api/participants/{pid}/{score_route}", json={}, headers=headers))
    assert _ok(client.post(f"/api/participants/{pid}/{score_route}", json={}, headers=headers)) == result
    assert result["post_pretest_tests_completed"] == 1 and result["post_pretest_test_limit"] == 2
    assert result["next_step"] == ("survey" if expected_type is None else "learning_targets")
    review = _ok(client.get(f"/api/participants/{pid}/learning-targets"))["test_results"]
    assert next(row for row in review["results"] if row["term_slug"] == "llm_knowledge")["question_body"] == question["body"]
    with SessionLocal() as db:
        attempt = db.query(Attempt).filter_by(participant_id=pid, question_id=question["question_id"]).one()
        assert attempt.is_correct == (expected_type is None) and attempt.misconception_type == expected_type
        source = assessment_question_spec("llm_knowledge", phase)
        selected = [option for option in question["options"] if option["option_id"] in _selected(question, source, labels)]
        assert _test_record(db, attempt)["selected_options"] == [{"label": option["label"], "body": option["body"]} for option in selected]
        term = db.query(Term).filter_by(slug="llm_knowledge").one()
        record = next(row for row in build_interaction_history(db, pid, term.id) if row["phase"] == phase and row["source_type"] == "test_attempt")
        assert record["question_body"] == question["body"]
        assert db.get(Participant, pid).retest_cycles_completed == (1 if phase == "retest" else 0)
    if expected_type is not None:
        _learn(client, pid)
        second = _answer_test(client, pid, "retest", "GHI", 2)
        assert second["question_id"] != question["question_id"]
        ended = _ok(client.post(f"/api/participants/{pid}/score-retest", json={}))
        assert ended["post_pretest_tests_completed"] == 2 and ended["next_step"] == "survey"
        with SessionLocal() as db:
            assert db.query(Attempt).filter_by(participant_id=pid).count() == 9
            latest = db.query(Attempt).filter_by(participant_id=pid, question_id=second["question_id"]).one()
            assert not latest.is_correct and latest.misconception_type == "M3"
    assert client.get(f"/api/experiment/{pid}/retest").status_code == 409


@pytest.mark.parametrize("phase", ["retest", "final_test"])
@pytest.mark.parametrize("snapshot", [False, True])
def test_old_spec22_v6_records_survive_seed_repair_and_missing_snapshot_restore(tmp_path, monkeypatch, phase, snapshot):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    monkeypatch.setattr(database, "engine", engine)
    Base.metadata.create_all(engine)
    old = yaml.safe_load(content_loader.SCENARIO_ACTIONS_V6_CONTENT_PATH.read_text(encoding="utf-8"))
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
                                         construct_key=assessment_construct_key(term.slug, stored_phase, bank_version="scenario-actions-v6"),
                                         variant_key=variant["variant_key"],
                                         options=[(option["label"], option["body"], option["is_correct"], option["misconception_type"]) for option in content_loader._assessment_options(variant)])
            term = db.query(Term).filter_by(slug="llm_knowledge").one()
            question = db.query(Question).filter_by(term_id=term.id, phase=phase, variant_key="retest_v1").one()
            option = db.query(QuestionOption).filter_by(question_id=question.id, option_label="H").one()
            participant = Participant(display_code="V6-HISTORY", group_condition="control", current_step="learning_targets",
                                      question_set_mode="standard", learning_content_version=14, experiment_spec_version=22,
                                      protocol_id=OLD_PROTOCOL, retest_cycles_completed=0 if phase == "final_test" else 1)
            db.add(participant)
            db.flush()
            attempt = Attempt(participant_id=participant.id, term_id=term.id, question_id=question.id, phase=phase,
                              test_round="retest_1", is_correct=False, misconception_type="M3", selected_option_ids=[option.id],
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
            assert record["selected_options"] == [{"label": "B" if snapshot else "H", "body": "保存時の選択肢" if snapshot else option.body}]
            restored = experiment._test_result_question(db, participant, term, "retest_1", phase)
            assert restored.id == question.id
            review = experiment.latest_test_results(db, participant.id)
            row = next(row for row in review["results"] if row["term_slug"] == "llm_knowledge")
            assert row["question_body"] == record["question_body"]
            assert json.dumps([attempt.question_body_snapshot, attempt.option_order_snapshot], sort_keys=True) == before_json
    finally:
        engine.dispose()
