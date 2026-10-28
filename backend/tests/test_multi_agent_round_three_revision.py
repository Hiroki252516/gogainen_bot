from copy import deepcopy
import hashlib
import json

import pytest
from admin_client import AuthenticatedTestClient as TestClient
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
    "variant_key": "learning_round_v3",
    "scenario_type": "comparison",
    "scenario": "大学が、学生からの「学内Wi-Fiにつながらない」という問い合わせに対応するAIシステムを開発している。開発担当者は、次の2つの設計を比較している。\n\n案1： 1つのAIエージェントが、Wi-Fiの設定マニュアルを検索するツールと、大学のネットワーク障害情報を調べるツールを使い、学生への回答を作成する。\n\n案2： 調査担当のAIエージェントが設定マニュアルや障害情報を調べて必要な内容を整理し、その結果を受け取った回答担当のAIエージェントが、学生への回答を作成する。\n\nなお、ここでいう検索ツールとは、指定された資料や情報を探して結果を返す機能を指す。",
    "task": "案1と案2の仕組みの違いについて、適切な説明を3つ選びなさい。",
    "choices": {
        "correct": [
            "案1でWi-Fiの設定手順が検索ツールから返ってきた場合、その手順が学生の端末に合うかを確認し、どの対処を案内するかは、ツールを使うAIエージェントが判断する。",
            "案2では、調査担当のAIが見つけた設定手順や障害情報を、回答担当のAIが受け取り、学生の問い合わせ内容に合わせて説明を組み立てることで、2つのAIが連携できる。",
            "案1で検索ツールを2種類利用しても、AIエージェントが2つに増えるわけではない。案2では調査と回答を別々のAIに担当させ、結果を受け渡している。"
        ],
        "M1": [
            "案1でWi-Fiの設定手順が検索結果の上位に表示された場合、その手順は学生の端末やOSに合うものとして選ばれていると考え、適用条件を確かめずに案内する。",
            "案2で調査担当のAIが設定マニュアルを調べ、接続設定のやり直しを提案した場合、同じ資料を共有する回答担当のAIも同じ対処方法を選ぶと考える。",
            "案1でマニュアル検索と障害情報確認の2つのツールを使って回答すると、使った情報はそのAIの記憶に残るため、記録を保存する仕組みがなくても次の問い合わせに利用できる。"
        ],
        "M3": [
            "案1で検索ツールが返したWi-Fi設定手順の説明文は、学生への回答を作るために使われるので、その文章も案2の調査担当のAIと同じ、1つのエージェントとして数える。",
            "案1ではマニュアル検索と障害情報確認という2つのツールが別々に結果を返すので、ツールが2つあることを、調査担当と回答担当の2つのAIが協力する構成と同じものとして扱う。",
            "案2で調査担当のAIが資料を読んで質問に必要な情報を整理しても、その処理は案1のマニュアル検索ツールと同じ種類の検索機能として分類できる。"
        ]
    }
}
OLD_PROTOCOL = "experiment-plan-2026-10-25-multi-agent-round2-v1"



def test_v9_only_changes_multi_agent_round_three_and_preserves_v8():
    assert hashlib.sha256(content_loader.LEARNING_V8_CONTENT_PATH.read_bytes()).hexdigest() == "8ad80b6152714a1e60b76a0df9f2f562b13626fd68b3db08703a6460564ce57c"
    previous = deepcopy(load_learning_content(content_version=8))
    previous["version"] = 9
    previous["terms"]["multi_agent"]["variants"][2] = EXPECTED
    assert load_learning_content(content_version=9) == previous


@pytest.mark.parametrize("stage", ["enrichment", "conceptual_change"])
def test_round_three_body_and_role_assignment(stage):
    spec = learning_question_spec("multi_agent", stage, 3, content_version=9)
    assert spec["body"] == EXPECTED["scenario"] + "\n\n" + EXPECTED["task"]
    assert len(spec["body"].split("\n\n")) == 5
    assert "**" not in spec["body"] and "問題：" not in spec["body"]
    assert spec["variant_key"] == "learning_round_v3" and spec["scenario_type"] == "comparison"
    assert spec["_content_version"] == 9
    for role, labels in (("correct", "ABC"), ("M1", "DEF"), ("M3", "GHI")):
        options = [option for option in spec["options"] if option["label"] in labels]
        assert [option["body"] for option in options] == EXPECTED["choices"][role]
        assert all(option["is_correct"] == (role == "correct") for option in options)
        assert all(option["misconception_type"] == (None if role == "correct" else role) for option in options)
    assert spec["options"][-1]["label"] == "J" and spec["options"][-1]["misconception_type"] == "unknown"


def test_missing_v9_never_falls_back(tmp_path, monkeypatch):
    try:
        with monkeypatch.context() as patch:
            patch.setattr(content_loader, "LEARNING_V9_CONTENT_PATH", tmp_path / "missing.yml")
            load_learning_content.cache_clear()
            with pytest.raises(FileNotFoundError):
                load_learning_content(content_version=9)
    finally:
        load_learning_content.cache_clear()


def test_easy_mode_cannot_load_v9():
    with pytest.raises(ValueError, match="version"):
        load_learning_content("easy", 9)


@pytest.mark.parametrize("version,spec_version,protocol", [(8, 15, OLD_PROTOCOL), (9, 16, "experiment-plan-2026-10-25-multi-agent-round3-v1")])
@pytest.mark.parametrize("snapshot", [False, True])
def test_round_three_history_preserves_snapshot_and_saved_bank(tmp_path, monkeypatch, version, spec_version, protocol, snapshot):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    monkeypatch.setattr(database, "engine", engine)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            participant = Participant(display_code="ROUND3-HISTORY", group_condition="control", question_set_mode="standard",
                                      experiment_spec_version=spec_version, protocol_id=protocol, learning_content_version=version)
            term = Term(slug="multi_agent", label="マルチエージェント", description="description", display_order=2)
            db.add_all([participant, term])
            db.flush()
            session = TutorSession(participant_id=participant.id, term_id=term.id, group_condition="control", session_index=3)
            db.add(session)
            db.flush()
            question = {"body": "保存時のV3問題", "options": [{"option_id": "H", "label": "H", "body": "保存時の選択肢"}]} if snapshot else {}
            turn = TutorTurn(tutor_session_id=session.id, turn_index=1, teaching_strategy="general_explanation", tutor_message="保存済み教材",
                             learner_response="H", practice_question_json=question, diagnosis_json={"learning_content_version": version},
                             grading_json={"is_sufficient": False, "selected_option_ids": ["H"]})
            db.add(turn)
            db.commit()
            if version == 8:
                before = {model: deepcopy(db.execute(select(model.__table__)).mappings().all()) for model in (Participant, TutorSession, TutorTurn)}
                seed_database(db)
                seed_database(db)
                database.init_db()
                database.init_db()
                for model, rows in before.items():
                    assert db.execute(select(model.__table__)).mappings().all() == rows
            before_json = json.dumps([turn.practice_question_json, turn.diagnosis_json, turn.grading_json], sort_keys=True)
            restored = _learning_record(db, session, turn)
            source = learning_question_spec("multi_agent", "enrichment", 3, content_version=version)
            assert restored["question_body"] == ("保存時のV3問題" if snapshot else source["body"])
            assert restored["selected_options"] == [{"label": "H", "body": "保存時の選択肢" if snapshot else source["options"][7]["body"]}]
            assert json.dumps([turn.practice_question_json, turn.diagnosis_json, turn.grading_json], sort_keys=True) == before_json
            if not snapshot:
                assert ("学内Wi-Fi" in restored["question_body"]) == (version == 9)
    finally:
        engine.dispose()


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def _answer_phase(client, pid, phase, role, variant_index=1):
    questions = _ok(client.get(f"/api/experiment/{pid}/{phase}"))["questions"]
    for question in questions:
        spec = assessment_question_spec(question["term_slug"], phase, variant_index)
        target = role if question["term_slug"] == "multi_agent" else "correct"
        bodies = {option["body"] for option in spec["options"] if option["is_correct"]} if target == "correct" else {option["body"] for option in spec["options"] if option["misconception_type"] == target}
        _ok(client.post("/api/attempts", json={"participant_id": pid, "question_id": question["question_id"], "selected_option_ids": [option["option_id"] for option in question["options"] if option["body"] in bodies]}))



@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
@pytest.mark.parametrize("initial", ["unknown", "M1"])
@pytest.mark.parametrize("labels,expected_type", [("ABC", None), ("DEF", "M1"), ("ADH", "M3"), ("J", "unknown")])
def test_synthetic_round_three_grading_feedback_replay_and_prefetch(group, layout, initial, labels, expected_type):
    client = TestClient(app)
    _ok(client.put("/api/admin/question-set", json={"mode": "standard"}))
    created = _ok(client.post("/api/participants", json={"assignment_code": group, "consent_checked": True, "student_number": "ROUND3-SYNTHETIC"}))
    pid = created["participant_id"]
    with SessionLocal() as db:
        participant = db.get(Participant, pid)
        assert participant.experiment_spec_version == CURRENT_EXPERIMENT_SPEC_VERSION and participant.learning_content_version == LEARNING_CONTENT_VERSIONS[STANDARD]
        participant.option_order_mode = layout
        db.commit()
    _answer_phase(client, pid, "pretest", initial)
    _ok(client.post(f"/api/participants/{pid}/diagnose-pretest"))
    session = _ok(client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "multi_agent"}))
    sid = session["tutor_session_id"]
    # The normal two-cycle flow never reaches V3; only this isolated fixture does.
    with SessionLocal() as db:
        db.get(TutorSession, sid).session_index = 3
        db.commit()
    current = _ok(client.post(f"/api/tutor-sessions/{sid}/turns", json={}))
    question = current["practice_question"]
    assert current["learning_stage"] == ("enrichment" if initial == "unknown" else "conceptual_change")
    assert question["variant_key"] == "learning_round_v3" and question["learning_variant_index"] == 3
    assert question["body"] == EXPECTED["scenario"] + "\n\n" + EXPECTED["task"]
    assert all(set(option) == {"option_id", "label", "body", "exclusive"} for option in question["options"])
    assert question["options"][-1]["exclusive"] and question["options"][-1]["label"] == "J"
    assert _ok(client.post(f"/api/tutor-sessions/{sid}/turns", json={}))["practice_question"] == question
    invalid = client.post(f"/api/tutor-turns/{current['turn_id']}/respond", json={"selected_option_ids": [question["options"][0]["option_id"], question["options"][-1]["option_id"]]})
    assert invalid.status_code == 400
    source = learning_question_spec("multi_agent", current["learning_stage"], 3)
    selected_bodies = {option["body"] for option in source["options"] if option["label"] in labels}
    payload = {"selected_option_ids": [option["option_id"] for option in question["options"] if option["body"] in selected_bodies]}
    headers = {"Idempotency-Key": "round-three-answer"}
    result = _ok(client.post(f"/api/tutor-turns/{current['turn_id']}/respond", json=payload, headers=headers))
    assert result["is_sufficient"] == (expected_type is None)
    if expected_type is not None:
        assert result["learning_misconception_type"] == expected_type
    assert result["feedback"]
    assert _ok(client.post(f"/api/tutor-turns/{current['turn_id']}/respond", json=payload, headers=headers)) == result
    wait_for_prefetch_tasks()
    with SessionLocal() as db:
        saved_session = db.get(TutorSession, sid)
        assert saved_session.session_index == 3
        saved = db.get(TutorTurn, current["turn_id"])
        assert saved.diagnosis_json["learning_content_version"] == LEARNING_CONTENT_VERSIONS[STANDARD]
        assert saved.practice_question_json["options"] == question["options"]
        history = build_interaction_history(db, pid, saved_session.term_id)
        record = next(row for row in history if row["source_type"] == "learning_turn" and row["session_index"] == 3)
        assert record["question_body"] == question["body"]
        assert {option["body"] for option in record["selected_options"]} == selected_bodies
    if expected_type is not None:
        retry = _ok(client.post(f"/api/tutor-sessions/{sid}/turns", json={}))
        assert retry["practice_question"] == question
        with SessionLocal() as db:
            assert db.get(TutorTurn, retry["turn_id"]).diagnosis_json["learning_content_version"] == LEARNING_CONTENT_VERSIONS[STANDARD]


@pytest.mark.parametrize("group", ["A", "B"])
def test_normal_route_still_finishes_after_two_cycles_without_round_three(group):
    client = TestClient(app)
    _ok(client.put("/api/admin/question-set", json={"mode": "standard"}))
    created = _ok(client.post("/api/participants", json={"assignment_code": group, "consent_checked": True, "student_number": "ROUND3-LIMIT"}))
    pid = created["participant_id"]
    _answer_phase(client, pid, "pretest", "unknown")
    _ok(client.post(f"/api/participants/{pid}/diagnose-pretest"))
    for index in (1, 2):
        session = _ok(client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "multi_agent"}))
        turn = _ok(client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}))
        assert turn["practice_question"]["learning_variant_index"] == index
        source = learning_question_spec("multi_agent", turn["learning_stage"], index)
        correct = {option["body"] for option in source["options"] if option["is_correct"]}
        _ok(client.post(f"/api/tutor-turns/{turn['turn_id']}/respond", json={"selected_option_ids": [option["option_id"] for option in turn["practice_question"]["options"] if option["body"] in correct]}))
        wait_for_prefetch_tasks()
        _answer_phase(client, pid, "retest", "unknown", variant_index=index)
        scored = _ok(client.post(f"/api/participants/{pid}/score-retest"))
        assert scored["post_pretest_tests_completed"] == index and scored["post_pretest_test_limit"] == 2
        assert scored["next_step"] == ("learning_targets" if index == 1 else "survey")
    assert client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "multi_agent"}).status_code == 409
    with SessionLocal() as db:
        assert all(session.session_index <= 2 for session in db.query(TutorSession).filter_by(participant_id=pid))
