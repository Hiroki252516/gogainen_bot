from copy import deepcopy
import hashlib
import json

import pytest
from admin_client import AuthenticatedTestClient as TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from split_api_support import assert_learning_flow

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
    assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[22] == {"standard": "scenario-actions-v6"}
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
    current = learning_question_spec(term_slug, stage, 1, content_version=15, use_current_assessment_source=False)
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


def test_missing_v14_never_falls_back(tmp_path, monkeypatch):
    try:
        with monkeypatch.context() as patch:
            patch.setattr(content_loader, "LEARNING_V14_CONTENT_PATH", tmp_path / "missing.yml")
            load_learning_content.cache_clear()
            with pytest.raises(FileNotFoundError):
                load_learning_content(content_version=14)
    finally:
        load_learning_content.cache_clear()


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
    assert_learning_flow(term_slug, group, layout, initial, labels, expected_type)


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
            participant = Participant(display_code="MULTI-MEMORY-V1-HISTORY", group_condition="control",
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
                assert (selected["body"] == new_text) == (version == 14)
                if term_slug == "memory_process":
                    assert (NEW_MEMORY_PURPOSE in restored["question_body"]) == (version == 14)
            assert json.dumps([turn.practice_question_json, turn.diagnosis_json, turn.grading_json], sort_keys=True) == before_json
    finally:
        engine.dispose()
