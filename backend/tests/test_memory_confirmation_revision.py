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
    "variant_key": "learning_round_v1",
    "scenario_type": "application",
    "scenario": "大学が、授業内容について質問できる学習支援AIを開発している。学生は会話の中で「具体例を先に示してほしい」「結論から説明してほしい」など、説明の仕方について希望を伝えることがある。また、同じ学生でも、相談を重ねる中で希望が変わることがある。\n\n開発担当者は、別の日に同じ学生が質問した際にも、その時点の希望に合った説明ができる仕組みを作りたいと考えている。",
    "task": "このAIに記憶機能を設ける場合の対応として、適切なものを3つ選びなさい。",
    "choices": {
        "correct": [
            "学生が「具体例を先に示してほしい」と伝えたら、その希望を学生ごとの記録に保存し、別の日に質問があった際に関係する記録を取り出して、説明の仕方に反映させる。",
            "説明の順番や文章の詳しさなど、記録する希望の項目を決め、学生ごとに情報を管理できるようにするとともに、記録を保持する期間や削除方法も設定する。",
            "「具体例を先に」と希望していた学生が後から「結論を先に」と伝えた場合、以前の記録を新しい希望に合わせて更新し、次回の説明には変更後の希望を反映する。"
        ],
        "M1": [
            "以前「具体例を先に」と希望した学生が後から「結論を先に」と伝えても、最初の希望がその学生の基本的な好みを表すと考え、次回以降も古い記録を優先して使う。",
            "過去の会話をすべて保存しておけば、そこに書かれた説明方法の希望が次の相談でも自動的に使われると考え、今回必要な情報を取り出す方法は特に設計しない。",
            "以前の会話から取り出した「箇条書きで説明してほしい」という希望を回答時に何度も利用すると、その希望がモデルの重みに保存され、次回は記録を取り出さなくても反映されると考える。"
        ],
        "M3": [
            "学生の説明方法の希望を記憶するため、会話から得た希望を追加訓練のデータに使い、更新されたモデルの重みを、学生ごとの希望を保存する記録として扱う。",
            "学生が過去の相談を見返せる履歴画面に「具体例を先に」といった希望を表示し、その画面の表示機能を、AIが希望を保存・検索する記憶管理の仕組みとして扱う。",
            "前回の会話を次の質問と一緒にプロンプトへ貼り付ける操作を、学生ごとの希望を継続して保存し、変更に応じて更新できる記憶管理の仕組みと同じものとして扱う。"
        ]
    }
}
OLD_PROTOCOL = "experiment-plan-2026-10-25-multi-agent-round3-v1"


def test_v10_only_changes_memory_first_question_and_preserves_v9():
    assert hashlib.sha256(content_loader.LEARNING_V9_CONTENT_PATH.read_bytes()).hexdigest() == "9dd6cb46a4bd809bac2ed5938dd78192c3d6e1bf0e5aa67e59d5d81e2c7aeb9e"
    previous = deepcopy(load_learning_content(content_version=9))
    previous["version"] = 10
    previous["terms"]["memory_process"]["variants"][0] = EXPECTED
    assert load_learning_content(content_version=10) == previous


@pytest.mark.parametrize("stage", ["enrichment", "conceptual_change"])
def test_memory_first_question_body_and_role_assignment(stage):
    spec = learning_question_spec("memory_process", stage, 1, content_version=10)
    assert spec["body"] == EXPECTED["scenario"] + "\n\n" + EXPECTED["task"]
    assert len(spec["body"].split("\n\n")) == 3
    assert "**" not in spec["body"] and "問題：" not in spec["body"]
    assert spec["variant_key"] == "learning_round_v1" and spec["scenario_type"] == "application"
    assert spec["_content_version"] == 10
    for role, labels in (("correct", "ABC"), ("M1", "DEF"), ("M3", "GHI")):
        options = [option for option in spec["options"] if option["label"] in labels]
        assert [option["body"] for option in options] == EXPECTED["choices"][role]
        assert all(option["is_correct"] == (role == "correct") for option in options)
        assert all(option["misconception_type"] == (None if role == "correct" else role) for option in options)
    assert spec["options"][-1]["label"] == "J" and spec["options"][-1]["misconception_type"] == "unknown"


def test_missing_v10_never_falls_back(tmp_path, monkeypatch):
    try:
        with monkeypatch.context() as patch:
            patch.setattr(content_loader, "LEARNING_V10_CONTENT_PATH", tmp_path / "missing.yml")
            load_learning_content.cache_clear()
            with pytest.raises(FileNotFoundError):
                load_learning_content(content_version=10)
    finally:
        load_learning_content.cache_clear()


def test_easy_mode_cannot_load_v10():
    with pytest.raises(ValueError, match="version"):
        load_learning_content("easy", 10)


@pytest.mark.parametrize("version,spec_version,protocol", [(9, 16, OLD_PROTOCOL), (10, 17, "experiment-plan-2026-10-25-memory-confirmation-v1")])
@pytest.mark.parametrize("snapshot", [False, True])
def test_memory_first_question_history_preserves_snapshot_and_saved_bank(tmp_path, monkeypatch, version, spec_version, protocol, snapshot):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    monkeypatch.setattr(database, "engine", engine)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            participant = Participant(display_code="MEMORY-V1-HISTORY", group_condition="control", question_set_mode="standard",
                                      experiment_spec_version=spec_version, protocol_id=protocol, learning_content_version=version)
            term = Term(slug="memory_process", label="記憶プロセス", description="description", display_order=2)
            db.add_all([participant, term])
            db.flush()
            session = TutorSession(participant_id=participant.id, term_id=term.id, group_condition="control", session_index=1)
            db.add(session)
            db.flush()
            question = {"body": "保存時の記憶V1問題", "options": [{"option_id": "H", "label": "H", "body": "保存時の選択肢"}]} if snapshot else {}
            turn = TutorTurn(tutor_session_id=session.id, turn_index=1, teaching_strategy="general_explanation", tutor_message="保存済み教材",
                             learner_response="H", practice_question_json=question, diagnosis_json={"learning_content_version": version},
                             grading_json={"is_sufficient": False, "selected_option_ids": ["H"]})
            db.add(turn)
            db.commit()
            if version == 9:
                before = {model: deepcopy(db.execute(select(model.__table__)).mappings().all()) for model in (Participant, TutorSession, TutorTurn)}
                seed_database(db)
                seed_database(db)
                database.init_db()
                database.init_db()
                for model, rows in before.items():
                    assert db.execute(select(model.__table__)).mappings().all() == rows
            before_json = json.dumps([turn.practice_question_json, turn.diagnosis_json, turn.grading_json], sort_keys=True)
            restored = _learning_record(db, session, turn)
            source = learning_question_spec("memory_process", "enrichment", 1, content_version=version)
            assert restored["question_body"] == ("保存時の記憶V1問題" if snapshot else source["body"])
            assert restored["selected_options"] == [{"label": "H", "body": "保存時の選択肢" if snapshot else source["options"][7]["body"]}]
            assert json.dumps([turn.practice_question_json, turn.diagnosis_json, turn.grading_json], sort_keys=True) == before_json
            if not snapshot:
                assert ("授業内容について質問できる" in restored["question_body"]) == (version == 10)
    finally:
        engine.dispose()


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def _answer_phase(client, pid, phase, role, variant_index=1):
    questions = _ok(client.get(f"/api/experiment/{pid}/{phase}"))["questions"]
    for question in questions:
        spec = assessment_question_spec(question["term_slug"], phase, variant_index)
        target = role if question["term_slug"] == "memory_process" else "correct"
        bodies = {option["body"] for option in spec["options"] if option["is_correct"]} if target == "correct" else {option["body"] for option in spec["options"] if option["misconception_type"] == target}
        _ok(client.post("/api/attempts", json={"participant_id": pid, "question_id": question["question_id"], "selected_option_ids": [option["option_id"] for option in question["options"] if option["body"] in bodies]}))



@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
@pytest.mark.parametrize("initial", ["unknown", "M1", "M3"])
@pytest.mark.parametrize("labels,expected_type", [("ABC", None), ("DEF", "M1"), ("ADH", "M3"), ("ADI", "M3"), ("J", "unknown")])
def test_natural_memory_first_question_grading_feedback_replay_and_prefetch(group, layout, initial, labels, expected_type):
    client = TestClient(app)
    _ok(client.put("/api/admin/question-set", json={"mode": "standard"}))
    created = _ok(client.post("/api/participants", json={"assignment_code": group, "consent_checked": True, "student_number": "MEMORY-V1-SYNTHETIC"}))
    pid = created["participant_id"]
    with SessionLocal() as db:
        participant = db.get(Participant, pid)
        assert participant.experiment_spec_version == CURRENT_EXPERIMENT_SPEC_VERSION and participant.learning_content_version == LEARNING_CONTENT_VERSIONS[STANDARD]
        participant.option_order_mode = layout
        db.commit()
    _answer_phase(client, pid, "pretest", initial)
    _ok(client.post(f"/api/participants/{pid}/diagnose-pretest"))
    session = _ok(client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "memory_process"}))
    sid = session["tutor_session_id"]
    current = _ok(client.post(f"/api/tutor-sessions/{sid}/turns", json={}))
    question = current["practice_question"]
    assert current["learning_stage"] == ("enrichment" if initial == "unknown" else "conceptual_change")
    assert question["variant_key"] == "learning_round_v1" and question["learning_variant_index"] == 1
    source = learning_question_spec("memory_process", current["learning_stage"], 1)
    assert question["body"] == source["body"]
    assert all(set(option) == {"option_id", "label", "body", "exclusive"} for option in question["options"])
    assert question["options"][-1]["exclusive"] and question["options"][-1]["label"] == "J"
    assert _ok(client.post(f"/api/tutor-sessions/{sid}/turns", json={}))["practice_question"] == question
    invalid = client.post(f"/api/tutor-turns/{current['turn_id']}/respond", json={"selected_option_ids": [question["options"][0]["option_id"], question["options"][-1]["option_id"]]})
    assert invalid.status_code == 400
    source = learning_question_spec("memory_process", current["learning_stage"], 1)
    selected_bodies = {option["body"] for option in source["options"] if option["label"] in labels}
    payload = {"selected_option_ids": [option["option_id"] for option in question["options"] if option["body"] in selected_bodies]}
    headers = {"Idempotency-Key": "memory-first-answer"}
    result = _ok(client.post(f"/api/tutor-turns/{current['turn_id']}/respond", json=payload, headers=headers))
    assert result["is_sufficient"] == (expected_type is None)
    if expected_type is not None:
        assert result["learning_misconception_type"] == expected_type
    assert result["feedback"]
    assert _ok(client.post(f"/api/tutor-turns/{current['turn_id']}/respond", json=payload, headers=headers)) == result
    wait_for_prefetch_tasks()
    with SessionLocal() as db:
        saved_session = db.get(TutorSession, sid)
        assert saved_session.session_index == 1
        saved = db.get(TutorTurn, current["turn_id"])
        assert saved.diagnosis_json["learning_content_version"] == LEARNING_CONTENT_VERSIONS[STANDARD]
        assert saved.practice_question_json["options"] == question["options"]
        history = build_interaction_history(db, pid, saved_session.term_id)
        record = next(row for row in history if row["source_type"] == "learning_turn" and row["session_index"] == 1)
        assert record["question_body"] == question["body"]
        assert {option["body"] for option in record["selected_options"]} == selected_bodies
    assert result["session_completed"] and result["max_turns"] == 1
    assert result["session_ended_by_attempt_limit"] == (expected_type is not None)
    assert client.post(f"/api/tutor-sessions/{sid}/turns", json={}).status_code == 409
