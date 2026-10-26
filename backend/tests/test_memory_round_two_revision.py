from copy import deepcopy
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID
from app.core.question_sets import LEARNING_CONTENT_VERSIONS, STANDARD, HISTORICAL_ASSESSMENT_BANK_VERSIONS
from app.db import session as database
from app.db.session import SessionLocal
from app.main import app
from app.models import Base, Participant, Term, TutorSession, TutorTurn
from app.seed import content_loader
from app.seed.content_loader import assessment_question_spec, learning_question_spec, load_learning_content
from app.seed.seed_questions import seed_database
from app.services.interaction_history import _learning_record, build_interaction_history
from app.services.experiment import _test_result_question
from app.services.prefetch import wait_for_prefetch_tasks


EXPECTED = {
    "variant_key": "learning_round_v2",
    "scenario_type": "prediction",
    "scenario": "料理の献立を提案するAIを開発している。ある利用者は以前の相談で「辛い料理が好き」「調理は20分以内がよい」と伝えていた。その後、同じ利用者が「最近は辛い料理を控えたい」と希望を変更した。開発担当者は、過去の会話で伝えられた希望と新しい希望を、次回以降の提案に役立てる記憶機能を考えている。",
    "task": "このAIが過去の会話を記憶として利用する場合、情報の扱いについて適切な記述を3つ選びなさい。",
    "choices": {
        "correct": [
            "最初の会話から「辛い料理が好き」「20分以内で作りたい」といった希望を取り出して短い記録にまとめれば、会話の全文を保存せずに必要な情報だけを残す方法も選べる。",
            "利用者から次の献立を尋ねられたとき、保存した希望の中から料理の辛さや調理時間に関係する記録を取り出し、その情報を参考に献立を提案できる。",
            "新たに「辛い料理を控えたい」と伝えられたら、以前の「辛い料理が好き」という記録の扱いを更新し、次の相談では変更後の希望を反映できる。"
        ],
        "M1": [
            "以前の「辛い料理が好き」と新しい「辛い料理を控えたい」が食い違っても、次の質問に最も関連する記録を検索すれば、新旧の違いを確認しなくても現在の希望を正しく判断できると考える。",
            "以前の「20分以内で作りたい」という希望を一度検索してAIの回答に使うと、その内容がモデルの重みに保存されるため、次回は記録を取り出さずに同じ希望を反映できると考える。",
            "過去の希望を「辛さ」「調理時間」などに分けて要約して保存すれば、AIは次回の相談に必要な記録を自動的に探せると考え、保存先から情報を取り出す方法は設計しない。"
        ],
        "M3": [
            "「辛い料理が好き」などの希望を短くまとめた要約文を、過去の記録を探し出す検索機能と同じ種類のものとして扱い、要約文を作ることを検索機能の実装とみなす。",
            "保存した「辛い料理を控えたい」という記録を検索してAIの回答に利用する処理を、会話データでモデルを追加訓練して重みを変更する仕組みと同じ種類のものとして扱う。",
            "利用者が過去の希望を見返せる履歴画面を作り、その画面で「辛い料理を控えたい」という記録を表示できることを、AIが提案に使う記憶の検索機能と同じものとして扱う。"
        ]
    }
}
OLD_PROTOCOL = "experiment-plan-2026-10-25-memory-confirmation-v1"


def test_v11_only_changes_memory_round_two_and_preserves_v10():
    assert hashlib.sha256(content_loader.LEARNING_V10_CONTENT_PATH.read_bytes()).hexdigest() == "c3c05882d9773192d0b9bcb703d3913d2334b18840ef2f0dc83c7773112568d2"
    previous = deepcopy(load_learning_content(content_version=10))
    previous["version"] = 11
    previous["terms"]["memory_process"]["variants"][1] = EXPECTED
    assert load_learning_content(content_version=11) == previous


@pytest.mark.parametrize("stage", ["enrichment", "conceptual_change"])
def test_memory_round_two_body_and_role_assignment(stage):
    spec = learning_question_spec("memory_process", stage, 2, content_version=11)
    assert spec["body"] == EXPECTED["scenario"] + "\n\n" + EXPECTED["task"]
    assert len(spec["body"].split("\n\n")) == 2
    assert "**" not in spec["body"] and "問題：" not in spec["body"]
    assert spec["variant_key"] == "learning_round_v2" and spec["scenario_type"] == "prediction"
    assert spec["_content_version"] == 11
    for role, labels in (("correct", "ABC"), ("M1", "DEF"), ("M3", "GHI")):
        options = [option for option in spec["options"] if option["label"] in labels]
        assert [option["body"] for option in options] == EXPECTED["choices"][role]
        assert all(option["is_correct"] == (role == "correct") for option in options)
        assert all(option["misconception_type"] == (None if role == "correct" else role) for option in options)
    assert spec["options"][-1]["label"] == "J" and spec["options"][-1]["misconception_type"] == "unknown"


def test_missing_v11_never_falls_back(tmp_path, monkeypatch):
    try:
        with monkeypatch.context() as patch:
            patch.setattr(content_loader, "LEARNING_V11_CONTENT_PATH", tmp_path / "missing.yml")
            load_learning_content.cache_clear()
            with pytest.raises(FileNotFoundError):
                load_learning_content(content_version=11)
    finally:
        load_learning_content.cache_clear()


def test_easy_mode_cannot_load_v11():
    with pytest.raises(ValueError, match="version"):
        load_learning_content("easy", 11)


@pytest.mark.parametrize("version,spec_version,protocol", [(10, 17, OLD_PROTOCOL), (11, 18, "experiment-plan-2026-10-26-memory-round2-v1"), (12, 20, "experiment-plan-2026-10-26-multi-memory-retests-v1"), (13, CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID)])
@pytest.mark.parametrize("snapshot", [False, True])
def test_memory_round_two_history_preserves_snapshot_and_saved_bank(tmp_path, monkeypatch, version, spec_version, protocol, snapshot):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    monkeypatch.setattr(database, "engine", engine)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            participant = Participant(display_code="MEMORY-V2-HISTORY", group_condition="control", question_set_mode="standard",
                                      experiment_spec_version=spec_version, protocol_id=protocol, learning_content_version=version)
            term = Term(slug="memory_process", label="記憶プロセス", description="description", display_order=2)
            db.add_all([participant, term])
            db.flush()
            session = TutorSession(participant_id=participant.id, term_id=term.id, group_condition="control", session_index=2)
            db.add(session)
            db.flush()
            question = {"body": "保存時の記憶V2問題", "options": [{"option_id": "H", "label": "H", "body": "保存時の選択肢"}]} if snapshot else {}
            turn = TutorTurn(tutor_session_id=session.id, turn_index=1, teaching_strategy="general_explanation", tutor_message="保存済み教材",
                             learner_response="H", practice_question_json=question, diagnosis_json={"learning_content_version": version},
                             grading_json={"is_sufficient": False, "selected_option_ids": ["H"]})
            db.add(turn)
            db.commit()
            if version in (10, 11, 12):
                before = {model: deepcopy(db.execute(select(model.__table__)).mappings().all()) for model in (Participant, TutorSession, TutorTurn)}
                seed_database(db)
                seed_database(db)
                database.init_db()
                database.init_db()
                for model, rows in before.items():
                    assert db.execute(select(model.__table__)).mappings().all() == rows
            before_json = json.dumps([turn.practice_question_json, turn.diagnosis_json, turn.grading_json], sort_keys=True)
            restored = _learning_record(db, session, turn)
            source = learning_question_spec("memory_process", "enrichment", 2, content_version=version)
            assert restored["question_body"] == ("保存時の記憶V2問題" if snapshot else source["body"])
            assert restored["selected_options"] == [{"label": "H", "body": "保存時の選択肢" if snapshot else source["options"][7]["body"]}]
            assert json.dumps([turn.practice_question_json, turn.diagnosis_json, turn.grading_json], sort_keys=True) == before_json
            if not snapshot:
                assert ("料理の献立" in restored["question_body"]) == (version >= 11)
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
def test_natural_memory_round_two_grading_feedback_replay_and_prefetch(group, layout, initial, labels, expected_type):
    client = TestClient(app)
    _ok(client.put("/api/admin/question-set", json={"mode": "standard"}))
    created = _ok(client.post("/api/participants", json={"assignment_code": group, "consent_checked": True, "student_number": "MEMORY-V2-SYNTHETIC"}))
    pid = created["participant_id"]
    with SessionLocal() as db:
        participant = db.get(Participant, pid)
        assert participant.experiment_spec_version == CURRENT_EXPERIMENT_SPEC_VERSION and participant.learning_content_version == LEARNING_CONTENT_VERSIONS[STANDARD]
        participant.option_order_mode = layout
        db.commit()
    _answer_phase(client, pid, "pretest", initial)
    _ok(client.post(f"/api/participants/{pid}/diagnose-pretest"))
    session1 = _ok(client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "memory_process"}))
    first = _ok(client.post(f"/api/tutor-sessions/{session1['tutor_session_id']}/turns", json={}))
    assert first["practice_question"]["variant_key"] == "learning_round_v1"
    first_spec = learning_question_spec("memory_process", first["learning_stage"], 1)
    correct = {option["body"] for option in first_spec["options"] if option["is_correct"]}
    _ok(client.post(f"/api/tutor-turns/{first['turn_id']}/respond", json={"selected_option_ids": [option["option_id"] for option in first["practice_question"]["options"] if option["body"] in correct]}))
    wait_for_prefetch_tasks()
    _answer_phase(client, pid, "retest", initial)
    scored = _ok(client.post(f"/api/participants/{pid}/score-retest"))
    assert scored["post_pretest_tests_completed"] == 1 and scored["next_step"] == "learning_targets"
    session2 = _ok(client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "memory_process"}))
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
    source = learning_question_spec("memory_process", current["learning_stage"], 2)
    selected_bodies = {option["body"] for option in source["options"] if option["label"] in labels}
    payload = {"selected_option_ids": [option["option_id"] for option in question["options"] if option["body"] in selected_bodies]}
    headers = {"Idempotency-Key": "memory-round-two-answer"}
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


@pytest.mark.parametrize("mode", ["standard", "easy"])
def test_current_spec_resolves_without_historical_mapping(mode):
    assert CURRENT_EXPERIMENT_SPEC_VERSION not in HISTORICAL_ASSESSMENT_BANK_VERSIONS
    client = TestClient(app)
    previous_mode = _ok(client.get("/api/admin/question-set"))["mode"]
    try:
        _ok(client.put("/api/admin/question-set", json={"mode": mode}))
        created = _ok(client.post("/api/participants", json={"assignment_code": "A", "consent_checked": True, "student_number": "CURRENT-BANK-SYNTHETIC"}))
        questions = _ok(client.get(f"/api/experiment/{created['participant_id']}/pretest"))["questions"]
        assert len(questions) == 3
        question = next(question for question in questions if question["term_slug"] == "memory_process")
        with SessionLocal() as db:
            participant = db.get(Participant, created["participant_id"])
            assert participant.experiment_spec_version == CURRENT_EXPERIMENT_SPEC_VERSION
            assert participant.learning_content_version == LEARNING_CONTENT_VERSIONS[mode]
            term = db.query(Term).filter_by(slug="memory_process").one()
            restored = _test_result_question(db, participant, term, "test", "pretest")
            assert restored is not None and restored.id == question["question_id"]
    finally:
        _ok(client.put("/api/admin/question-set", json={"mode": previous_mode}))
