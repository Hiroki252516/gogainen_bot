from copy import deepcopy
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION
from app.core.question_sets import LEARNING_CONTENT_VERSIONS, STANDARD
from app.db import session as database
from app.db.session import SessionLocal
from app.main import app
from app.models import Base, Participant, Term, TutorSession, TutorTurn
from app.seed import content_loader
from app.seed.content_loader import assessment_question_spec, learning_question_spec, load_learning_content
from app.seed.seed_questions import seed_database
from app.services.interaction_history import _learning_record, build_interaction_history
from app.services.prefetch import wait_for_prefetch_tasks


EXPECTED = {
    "variant_key": "learning_round_v2",
    "scenario_type": "prediction",
    "scenario": "自治体が、被害状況や道路の情報をもとに、住民向けの避難案内を作成するAIシステムについて、次の2つの設計を比較している。\n\n案1： 1つのAIエージェントが、情報収集、避難方法の検討、住民向け案内文の作成を順番に行う。\n\n案2： 情報収集、避難方法の検討、案内文の作成をそれぞれ別のAIエージェントに担当させ、前の担当の結果を次の担当へ引き継ぐ。",
    "task": "案1から案2に変更した場合の仕組みの違いについて、適切な説明を3つ選びなさい。",
    "choices": {
        "correct": [
            "案2では、情報収集担当のAIが集めた道路情報を避難方法の検討担当へ渡し、その検討結果を避難案内文作成担当へ引き継ぐことで、異なる担当の作業を一つの案内作成に繋げられる。",
            "案1では1つのAIが調査から避難案内文の作成まで担当するが、案2では役割ごとに別のAIを設けるため、各担当に異なる指示や必要な資料を設定する構成にできる。",
            "案2で複数のAIを連携させるには、どの担当から次の担当へ何を渡すかを決め、受け取った結果を各AIの作業に利用できるよう、情報の受け渡し方を設計する。"
        ],
        "M1": [
            "案2では、道路情報の調査を専門に担当するAIを設けているため、調査内容の信頼性も確保されており、避難方法の検討担当はその報告を確認せずに利用する。",
            "案2では、情報収集担当がまとめた道路情報を避難計画担当へ渡しておけば、避難計画担当の役割に必要な情報が自動的に選ばれて届くと考え、受け渡す情報の内容は特に指定しない。",
            "案2で情報収集担当が「道路Aは通行可能」と報告し、避難計画担当が「避難には道路Bを使う」と判断した場合、担当同士の結論が一致していないため、両者の判断をそろえなければ連携を続けられない。"
        ],
        "M3": [
            "案1では、1つのAIが情報収集、避難方法の検討、避難案内文の作成を3つの手順に分けて行っているため、3つのAIエージェントが連携している構成として分類できる。",
            "案2では、情報収集担当が作成した道路情報の報告ファイルも、計画担当が避難方法を判断する際に利用されるため、調査担当や避難計画担当と同じく、連携するAIエージェントの一つとして数える。",
            "案2で3つのAIに作業を分担させることは、1つのAIモデルの内部計算を複数に分割して処理速度を上げる方式と同じ種類の仕組みであると考える。"
        ]
    }
}
OLD_PROTOCOL = "experiment-plan-2026-10-25-multi-agent-confirmation-v2"


def test_v8_only_changes_multi_agent_round_two_and_preserves_v7():
    assert hashlib.sha256(content_loader.LEARNING_V7_CONTENT_PATH.read_bytes()).hexdigest() == "041727d841f66489ea0e7c0b5952b9965354f563db195aa6829b9941657080c0"
    previous = deepcopy(load_learning_content(content_version=7))
    previous["version"] = 8
    previous["terms"]["multi_agent"]["variants"][1] = EXPECTED
    assert load_learning_content(content_version=8) == previous


@pytest.mark.parametrize("stage", ["enrichment", "conceptual_change"])
def test_round_two_body_and_role_assignment(stage):
    spec = learning_question_spec("multi_agent", stage, 2, content_version=8)
    assert spec["body"] == EXPECTED["scenario"] + "\n\n" + EXPECTED["task"]
    assert len(spec["body"].split("\n\n")) == 4
    assert "**" not in spec["body"] and "問題：" not in spec["body"]
    assert spec["variant_key"] == "learning_round_v2" and spec["scenario_type"] == "prediction"
    assert spec["_content_version"] == 8
    for role, labels in (("correct", "ABC"), ("M1", "DEF"), ("M3", "GHI")):
        options = [option for option in spec["options"] if option["label"] in labels]
        assert [option["body"] for option in options] == EXPECTED["choices"][role]
        assert all(option["is_correct"] == (role == "correct") for option in options)
        assert all(option["misconception_type"] == (None if role == "correct" else role) for option in options)
    assert spec["options"][-1]["label"] == "J" and spec["options"][-1]["misconception_type"] == "unknown"


def test_missing_v8_never_falls_back(tmp_path, monkeypatch):
    try:
        with monkeypatch.context() as patch:
            patch.setattr(content_loader, "LEARNING_V8_CONTENT_PATH", tmp_path / "missing.yml")
            load_learning_content.cache_clear()
            with pytest.raises(FileNotFoundError):
                load_learning_content(content_version=8)
    finally:
        load_learning_content.cache_clear()


def test_easy_mode_cannot_load_v8():
    with pytest.raises(ValueError, match="version"):
        load_learning_content("easy", 8)


@pytest.mark.parametrize("version,spec_version,protocol", [(7, 14, OLD_PROTOCOL), (8, 15, "experiment-plan-2026-10-25-multi-agent-round2-v1")])
@pytest.mark.parametrize("snapshot", [False, True])
def test_round_two_history_uses_snapshot_or_saved_bank_without_writes(tmp_path, monkeypatch, version, spec_version, protocol, snapshot):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    monkeypatch.setattr(database, "engine", engine)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            participant = Participant(display_code="ROUND2-HISTORY", group_condition="control", question_set_mode="standard",
                                      experiment_spec_version=spec_version, protocol_id=protocol, learning_content_version=version)
            term = Term(slug="multi_agent", label="マルチエージェント", description="description", display_order=2)
            db.add_all([participant, term])
            db.flush()
            session = TutorSession(participant_id=participant.id, term_id=term.id, group_condition="control", session_index=2)
            db.add(session)
            db.flush()
            question = {"body": "保存時のV2問題", "options": [{"option_id": "H", "label": "H", "body": "保存時の選択肢"}]} if snapshot else {}
            turn = TutorTurn(tutor_session_id=session.id, turn_index=1, teaching_strategy="general_explanation", tutor_message="保存済み教材",
                             learner_response="H", practice_question_json=question, diagnosis_json={"learning_content_version": version},
                             grading_json={"is_sufficient": False, "selected_option_ids": ["H"]})
            db.add(turn)
            db.commit()
            if version == 7:
                before_rows = {model: deepcopy(db.execute(select(model.__table__)).mappings().all()) for model in (Participant, TutorSession, TutorTurn)}
                seed_database(db)
                seed_database(db)
                database.init_db()
                database.init_db()
                for model, rows in before_rows.items():
                    assert db.execute(select(model.__table__)).mappings().all() == rows
            before = json.dumps([turn.practice_question_json, turn.diagnosis_json, turn.grading_json], sort_keys=True)
            restored = _learning_record(db, session, turn)
            spec = learning_question_spec("multi_agent", "enrichment", 2, content_version=version)
            assert restored["question_body"] == ("保存時のV2問題" if snapshot else spec["body"])
            assert restored["selected_options"] == [{"label": "H", "body": "保存時の選択肢" if snapshot else spec["options"][7]["body"]}]
            assert json.dumps([turn.practice_question_json, turn.diagnosis_json, turn.grading_json], sort_keys=True) == before
            if not snapshot:
                assert ("案1：" in restored["question_body"]) == (version == 8)
    finally:
        engine.dispose()


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def _answer_phase(client, pid, phase, role):
    questions = _ok(client.get(f"/api/experiment/{pid}/{phase}"))["questions"]
    for question in questions:
        spec = assessment_question_spec(question["term_slug"], phase, 1)
        target = role if question["term_slug"] == "multi_agent" else "correct"
        bodies = {option["body"] for option in spec["options"] if option["is_correct"]} if target == "correct" else {option["body"] for option in spec["options"] if option["misconception_type"] == target}
        _ok(client.post("/api/attempts", json={"participant_id": pid, "question_id": question["question_id"], "selected_option_ids": [option["option_id"] for option in question["options"] if option["body"] in bodies]}))


@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
@pytest.mark.parametrize("initial", ["unknown", "M1"])
@pytest.mark.parametrize("labels,expected_type", [("ABC", None), ("DEF", "M1"), ("ADH", "M3"), ("J", "unknown")])
def test_natural_round_two_route_grading_feedback_replay_and_prefetch(group, layout, initial, labels, expected_type):
    client = TestClient(app)
    _ok(client.put("/api/admin/question-set", json={"mode": "standard"}))
    created = _ok(client.post("/api/participants", json={"assignment_code": group, "consent_checked": True, "student_number": "ROUND2-SYNTHETIC"}))
    pid = created["participant_id"]
    with SessionLocal() as db:
        participant = db.get(Participant, pid)
        assert participant.experiment_spec_version == CURRENT_EXPERIMENT_SPEC_VERSION and participant.learning_content_version == LEARNING_CONTENT_VERSIONS[STANDARD]
        participant.option_order_mode = layout
        db.commit()
    _answer_phase(client, pid, "pretest", initial)
    _ok(client.post(f"/api/participants/{pid}/diagnose-pretest"))
    session1 = _ok(client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "multi_agent"}))
    first = _ok(client.post(f"/api/tutor-sessions/{session1['tutor_session_id']}/turns", json={}))
    assert first["practice_question"]["variant_key"] == "learning_round_v1"
    first_spec = learning_question_spec("multi_agent", first["learning_stage"], 1)
    correct = {option["body"] for option in first_spec["options"] if option["is_correct"]}
    _ok(client.post(f"/api/tutor-turns/{first['turn_id']}/respond", json={"selected_option_ids": [option["option_id"] for option in first["practice_question"]["options"] if option["body"] in correct]}))
    wait_for_prefetch_tasks()
    _answer_phase(client, pid, "retest", initial)
    scored = _ok(client.post(f"/api/participants/{pid}/score-retest"))
    assert scored["post_pretest_tests_completed"] == 1 and scored["next_step"] == "learning_targets"
    session2 = _ok(client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "multi_agent"}))
    sid = session2["tutor_session_id"]
    current = _ok(client.post(f"/api/tutor-sessions/{sid}/turns", json={}))
    question = current["practice_question"]
    assert current["learning_stage"] == ("enrichment" if initial == "unknown" else "conceptual_change")
    assert question["variant_key"] == "learning_round_v2" and question["learning_variant_index"] == 2
    assert question["body"] == EXPECTED["scenario"] + "\n\n" + EXPECTED["task"]
    assert all(set(option) == {"option_id", "label", "body", "exclusive"} for option in question["options"])
    assert question["options"][-1]["exclusive"] and question["options"][-1]["label"] == "J"
    invalid = client.post(f"/api/tutor-turns/{current['turn_id']}/respond", json={"selected_option_ids": [question["options"][0]["option_id"], question["options"][-1]["option_id"]]})
    assert invalid.status_code == 400
    source = learning_question_spec("multi_agent", current["learning_stage"], 2)
    selected_bodies = {option["body"] for option in source["options"] if option["label"] in labels}
    payload = {"selected_option_ids": [option["option_id"] for option in question["options"] if option["body"] in selected_bodies]}
    headers = {"Idempotency-Key": "round-two-answer"}
    result = _ok(client.post(f"/api/tutor-turns/{current['turn_id']}/respond", json=payload, headers=headers))
    assert result["is_sufficient"] == (expected_type is None)
    if expected_type is not None:
        assert result["learning_misconception_type"] == expected_type
    assert result["feedback"]
    assert _ok(client.post(f"/api/tutor-turns/{current['turn_id']}/respond", json=payload, headers=headers)) == result
    wait_for_prefetch_tasks()
    with SessionLocal() as db:
        saved_session = db.get(TutorSession, sid)
        assert saved_session.session_index == 2
        assert db.get(TutorTurn, current["turn_id"]).diagnosis_json["learning_content_version"] == LEARNING_CONTENT_VERSIONS[STANDARD]
        history = build_interaction_history(db, pid, saved_session.term_id)
        record = next(row for row in history if row["source_type"] == "learning_turn" and row["session_index"] == 2)
        assert record["question_body"] == question["body"]
        assert {option["body"] for option in record["selected_options"]} == selected_bodies
    if expected_type is not None:
        retry = _ok(client.post(f"/api/tutor-sessions/{sid}/turns", json={}))
        assert retry["practice_question"] == question
        with SessionLocal() as db:
            assert db.get(TutorTurn, retry["turn_id"]).diagnosis_json["learning_content_version"] == LEARNING_CONTENT_VERSIONS[STANDARD]
