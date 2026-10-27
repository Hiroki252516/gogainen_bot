from copy import deepcopy
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID
from app.core.question_sets import ASSESSMENT_BANK_VERSIONS, HISTORICAL_ASSESSMENT_BANK_VERSIONS, LEARNING_CONTENT_VERSIONS
from app.db import session as database
from app.db.session import SessionLocal
from app.main import app
from app.models import Base, Participant, Question, QuestionOption, Term, TutorSession, TutorTurn
from app.seed import content_loader
from app.seed.content_loader import assessment_question_spec, learning_question_spec, load_learning_content
from app.seed.seed_questions import seed_database
from app.services.interaction_history import _learning_record, build_interaction_history
from app.services.prefetch import wait_for_prefetch_tasks


NEW_MULTI_G = "情報収集担当のAIが道路情報のデータベースから通行止めの一覧を取得する検索ツールを使う場合、そのツールも情報を調べて結果を渡すので、別のAIエージェントとして数える。"
NEW_MEMORY_PURPOSE = "開発担当者は、同じ学生が別の日に新しく質問したとき、説明の仕方について希望を毎回伝え直さなくても、その学生が最後に伝えた希望に合わせて説明できるようにしたいと考えている。"
NEW_MEMORY_F = "以前保存した「具体例を先に」という希望をAIに渡して説明させたところ、希望どおりに回答できたので、AIはその希望を新たに覚えたと考え、次の相談では記録を参照させない。"
NEW_MEMORY_H = "同じ会話で「具体例を先に」と伝えた後、続く質問にも希望が反映されたので、会話中の履歴を利用する仕組みを、別の日の新しい会話でも希望を保持する長期記憶と同じものとして扱う。"
OLD_PROTOCOL = "experiment-plan-2026-10-26-llm-round1-dh-v1"


def test_v14_changes_only_the_four_requested_locations_and_keeps_v13():
    assert load_learning_content(content_version=14)["version"] == 14
    assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[22] == {"standard": "scenario-actions-v6", "easy": "scenario-actions-easy-v1"}
    assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[21] == HISTORICAL_ASSESSMENT_BANK_VERSIONS[22]
    assert CURRENT_EXPERIMENT_SPEC_VERSION not in HISTORICAL_ASSESSMENT_BANK_VERSIONS
    assert hashlib.sha256(content_loader.LEARNING_V13_CONTENT_PATH.read_bytes()).hexdigest() == "78fe46d82b29ab5cfcaab969def2410732d19e7306dfd96244a6325d4de78c57"
    expected = deepcopy(load_learning_content(content_version=13))
    expected["version"] = 14
    expected["terms"]["multi_agent"]["variants"][0]["choices"]["M3"][0] = NEW_MULTI_G
    memory = expected["terms"]["memory_process"]["variants"][0]
    memory["scenario"] = memory["scenario"].split("\n\n")[0] + "\n\n" + NEW_MEMORY_PURPOSE
    memory["choices"]["M1"][2] = NEW_MEMORY_F
    memory["choices"]["M3"][1] = NEW_MEMORY_H
    assert load_learning_content(content_version=14) == expected


@pytest.mark.parametrize("term_slug", ["multi_agent", "memory_process"])
@pytest.mark.parametrize("stage", ["enrichment", "conceptual_change"])
def test_revised_round_one_roles_and_paragraphs(term_slug, stage):
    old = learning_question_spec(term_slug, stage, 1, content_version=13)
    current = learning_question_spec(term_slug, stage, 1)
    assert current["variant_key"] == "learning_round_v1" and current["scenario_type"] == "application"
    assert current["_content_version"] == LEARNING_CONTENT_VERSIONS["standard"]
    assert len(current["options"]) == 10
    changed = {"G": (NEW_MULTI_G, "M3")} if term_slug == "multi_agent" else {"F": (NEW_MEMORY_F, "M1"), "H": (NEW_MEMORY_H, "M3")}
    options = {option["label"]: option for option in current["options"]}
    for label, (body, role) in changed.items():
        assert options[label]["body"] == body
        assert options[label]["misconception_type"] == role and not options[label]["is_correct"]
    assert [option for option in current["options"] if option["label"] not in changed] == [option for option in old["options"] if option["label"] not in changed]
    if term_slug == "memory_process":
        assert len(current["body"].split("\n\n")) == 3
        assert current["body"].split("\n\n")[1] == NEW_MEMORY_PURPOSE
        assert current["body"].split("\n\n")[::2] == old["body"].split("\n\n")[::2]
    else:
        assert current["body"] == old["body"]
    assert "**" not in current["body"] and "問題：" not in current["body"]
    assert options["J"]["body"] == "わからない。" and options["J"]["misconception_type"] == "unknown"


def test_missing_v14_or_wrong_mode_never_falls_back(tmp_path, monkeypatch):
    try:
        with monkeypatch.context() as patch:
            patch.setattr(content_loader, "LEARNING_V14_CONTENT_PATH", tmp_path / "missing.yml")
            load_learning_content.cache_clear()
            with pytest.raises(FileNotFoundError):
                load_learning_content(content_version=14)
    finally:
        load_learning_content.cache_clear()
    with pytest.raises(ValueError, match="version"):
        load_learning_content("easy", 14)


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def _selected(question, source, labels):
    bodies = {option["body"] for option in source["options"] if option["label"] in labels}
    return [option["option_id"] for option in question["options"] if option["body"] in bodies]


@pytest.mark.parametrize("term_slug", ["multi_agent", "memory_process"])
@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
@pytest.mark.parametrize("initial", ["J", "DEF", "GHI"])
@pytest.mark.parametrize("labels,expected_type", [("ABC", None), ("ABF", "M1"), ("DEF", "M1"), ("AFG", "M3"), ("AFH", "M3"), ("J", "unknown")])
def test_round_one_display_scoring_feedback_retry_replay_history_and_prefetch(term_slug, group, layout, initial, labels, expected_type):
    client = TestClient(app)
    _ok(client.put("/api/admin/question-set", json={"mode": "standard"}))
    created = _ok(client.post("/api/participants", json={"assignment_code": group, "consent_checked": True, "student_number": "MULTI-MEMORY-V1-SYNTHETIC"}))
    pid = created["participant_id"]
    with SessionLocal() as db:
        participant = db.get(Participant, pid)
        participant.option_order_mode = layout
        assert participant.experiment_spec_version == CURRENT_EXPERIMENT_SPEC_VERSION and participant.learning_content_version == LEARNING_CONTENT_VERSIONS["standard"]
        assert participant.protocol_id == CURRENT_PROTOCOL_ID
        db.commit()
    for question in _ok(client.get(f"/api/experiment/{pid}/pretest"))["questions"]:
        source = assessment_question_spec(question["term_slug"], "pretest")
        _ok(client.post("/api/attempts", json={"participant_id": pid, "question_id": question["question_id"],
                                             "selected_option_ids": _selected(question, source, initial if question["term_slug"] == term_slug else "ABC")}))
    _ok(client.post(f"/api/participants/{pid}/diagnose-pretest"))
    session = _ok(client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": term_slug}))
    sid = session["tutor_session_id"]
    turn = _ok(client.post(f"/api/tutor-sessions/{sid}/turns", json={}))
    question = turn["practice_question"]
    source = learning_question_spec(term_slug, turn["learning_stage"], 1)
    assert turn["learning_stage"] == ("enrichment" if initial == "J" else "conceptual_change")
    assert question["variant_key"] == "learning_round_v1" and question["learning_variant_index"] == 1
    assert question["body"] == source["body"]
    assert {option["body"] for option in question["options"]} == {option["body"] for option in source["options"]}
    assert all(set(option) == {"option_id", "label", "body", "exclusive"} for option in question["options"])
    assert question["options"][-1]["exclusive"] and question["options"][-1]["label"] == "J"
    assert _ok(client.post(f"/api/tutor-sessions/{sid}/turns", json={}))["practice_question"] == question
    invalid = client.post(f"/api/tutor-turns/{turn['turn_id']}/respond", json={"selected_option_ids": [question["options"][0]["option_id"], question["options"][-1]["option_id"]]})
    assert invalid.status_code == 400
    payload = {"selected_option_ids": _selected(question, source, labels)}
    headers = {"Idempotency-Key": "multi-memory-round1-answer"}
    result = _ok(client.post(f"/api/tutor-turns/{turn['turn_id']}/respond", json=payload, headers=headers))
    assert result["is_sufficient"] == (expected_type is None) and result["feedback"]
    if expected_type is not None:
        assert result["learning_misconception_type"] == expected_type
    assert _ok(client.post(f"/api/tutor-turns/{turn['turn_id']}/respond", json=payload, headers=headers)) == result
    wait_for_prefetch_tasks()
    with SessionLocal() as db:
        saved_session = db.get(TutorSession, sid)
        saved_turn = db.get(TutorTurn, turn["turn_id"])
        assert saved_session.session_index == 1
        assert saved_turn.diagnosis_json["learning_content_version"] == LEARNING_CONTENT_VERSIONS["standard"]
        assert saved_turn.practice_question_json["options"] == question["options"]
        record = next(row for row in build_interaction_history(db, pid, saved_session.term_id) if row["source_type"] == "learning_turn")
        assert record["question_body"] == question["body"]
        assert {option["body"] for option in record["selected_options"]} == {option["body"] for option in source["options"] if option["label"] in labels}
    if expected_type is not None:
        retry = _ok(client.post(f"/api/tutor-sessions/{sid}/turns", json={}))
        assert retry["practice_question"] == question
        with SessionLocal() as db:
            saved = db.get(TutorTurn, retry["turn_id"])
            assert saved.diagnosis_json["learning_content_version"] == LEARNING_CONTENT_VERSIONS["standard"]
            assert saved.diagnosis_json["generation_origin"] == "same_session_prefetch"


@pytest.mark.parametrize("version,spec_version,protocol", [(13, 21, OLD_PROTOCOL), (14, 24, "experiment-plan-2026-10-27-multi-memory-retest1-v1"), (15, CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID)])
@pytest.mark.parametrize("snapshot", [False, True])
@pytest.mark.parametrize("term_slug,label,new_text", [("multi_agent", "G", NEW_MULTI_G), ("memory_process", "F", NEW_MEMORY_F), ("memory_process", "H", NEW_MEMORY_H)])
def test_snapshot_or_saved_bank_restoration_and_old_rows_survive_seed_and_startup(tmp_path, monkeypatch, version, spec_version, protocol, snapshot, term_slug, label, new_text):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    monkeypatch.setattr(database, "engine", engine)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            seed_database(db)
            term = db.query(Term).filter_by(slug=term_slug).one()
            participant = Participant(display_code="MULTI-MEMORY-V1-HISTORY", group_condition="control", question_set_mode="standard",
                                      learning_content_version=version, experiment_spec_version=spec_version, protocol_id=protocol)
            db.add(participant)
            db.flush()
            session = TutorSession(participant_id=participant.id, term_id=term.id, group_condition="control", session_index=1)
            db.add(session)
            db.flush()
            question = {"body": "保存時の問題", "options": [{"option_id": label, "label": label, "body": "保存時の選択肢"}]} if snapshot else {}
            turn = TutorTurn(tutor_session_id=session.id, turn_index=1, teaching_strategy="general_explanation", tutor_message="保存済み教材",
                             learner_response=label, practice_question_json=question, diagnosis_json={"learning_content_version": version},
                             grading_json={"is_sufficient": False, "selected_option_ids": [label]})
            db.add(turn)
            db.commit()
            if version == 13:
                protected = {model: deepcopy(db.execute(select(model.__table__)).mappings().all()) for model in (Participant, TutorSession, TutorTurn, Question, QuestionOption)}
                seed_database(db)
                seed_database(db)
                database.init_db()
                database.init_db()
                for model, rows in protected.items():
                    assert db.execute(select(model.__table__)).mappings().all() == rows
            before_json = json.dumps([turn.practice_question_json, turn.diagnosis_json, turn.grading_json], sort_keys=True)
            restored = _learning_record(db, session, turn)
            original = learning_question_spec(term_slug, "enrichment", 1, content_version=version)
            selected = next(option for option in original["options"] if option["label"] == label)
            assert restored["question_body"] == ("保存時の問題" if snapshot else original["body"])
            assert restored["selected_options"] == [{"label": label, "body": "保存時の選択肢" if snapshot else selected["body"]}]
            if not snapshot:
                assert (selected["body"] == new_text) == (version >= 14)
                if term_slug == "memory_process":
                    assert (NEW_MEMORY_PURPOSE in restored["question_body"]) == (version >= 14)
            assert json.dumps([turn.practice_question_json, turn.diagnosis_json, turn.grading_json], sort_keys=True) == before_json
    finally:
        engine.dispose()
