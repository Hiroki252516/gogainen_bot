from copy import deepcopy
import hashlib
import json

import pytest
from admin_client import AuthenticatedTestClient as TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from split_api_support import assert_learning_flow

from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID
from app.core.question_sets import LEARNING_CONTENT_VERSIONS, HISTORICAL_ASSESSMENT_BANK_VERSIONS
from app.db import session as database
from app.db.session import SessionLocal
from app.main import app
from app.models import Base, Participant, Term, TutorSession, TutorTurn
from app.seed import content_loader
from app.seed.content_loader import assessment_question_spec, learning_question_spec, load_learning_content
from app.seed.seed_questions import seed_database
from app.services.interaction_history import _learning_record, build_interaction_history
from app.services.prefetch import wait_for_prefetch_tasks


NEW_D = "開発中のテストでAIに改訂後の履修規程を見せ、変更期限を正しく答えられたため、モデルの重みが更新されたことで、新しい規程をAIが覚えたと判断し、実際の学生からの問い合わせでは規程を示さずに案内させる。"
NEW_H = "改訂後の履修規程を使ってAIを追加訓練し、学生から変更期限を尋ねられた際には、AIが学習に使った規程の該当箇所を探して参照できるものとして、文書検索の仕組みの代わりに用いる。"
OLD_PROTOCOL = "experiment-plan-2026-10-26-multi-memory-retests-v1"


def test_v13_changes_only_llm_round_one_d_and_h():
    assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[20] == {"standard": "scenario-actions-v6"}
    assert hashlib.sha256(content_loader.LEARNING_V12_CONTENT_PATH.read_bytes()).hexdigest() == "87dc5c40081f113350b9b7ffabef5f46fe6fe0fd0e68949eb68755c68de6eb4b"
    expected = deepcopy(load_learning_content(content_version=12))
    expected["version"] = 13
    question = expected["terms"]["llm_knowledge"]["variants"][0]
    question["choices"]["M1"][0] = NEW_D
    question["choices"]["M3"][1] = NEW_H
    assert load_learning_content(content_version=13) == expected


@pytest.mark.parametrize("stage", ["enrichment", "conceptual_change"])
def test_revised_choices_keep_their_roles_and_display(stage):
    old = learning_question_spec("llm_knowledge", stage, 1, content_version=12)
    current = learning_question_spec("llm_knowledge", stage, 1, content_version=13)
    assert current["body"] == old["body"]
    assert len(current["body"].split("\n\n")) == 2
    assert current["_content_version"] == 13
    options = {option["label"]: option for option in current["options"]}
    assert options["D"]["body"] == NEW_D and options["D"]["misconception_type"] == "M1"
    assert options["H"]["body"] == NEW_H and options["H"]["misconception_type"] == "M3"
    assert not options["D"]["is_correct"] and not options["H"]["is_correct"]
    assert [option for option in current["options"] if option["label"] not in "DH"] == [option for option in old["options"] if option["label"] not in "DH"]


def test_missing_v13_never_falls_back(tmp_path, monkeypatch):
    try:
        with monkeypatch.context() as patch:
            patch.setattr(content_loader, "LEARNING_V13_CONTENT_PATH", tmp_path / "missing.yml")
            load_learning_content.cache_clear()
            with pytest.raises(FileNotFoundError):
                load_learning_content(content_version=13)
    finally:
        load_learning_content.cache_clear()


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def _selected(question, source, labels):
    bodies = {option["body"] for option in source["options"] if option["label"] in labels}
    return [option["option_id"] for option in question["options"] if option["body"] in bodies]


@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
@pytest.mark.parametrize("initial", ["J", "DEF", "GHI"])
@pytest.mark.parametrize("labels,expected_type", [("ABC", None), ("DEF", "M1"), ("ADH", "M3"), ("J", "unknown")])
def test_revised_round_one_scoring_feedback_replay_history_and_prefetch(group, layout, initial, labels, expected_type):
    assert_learning_flow("llm_knowledge", group, layout, initial, labels, expected_type)


@pytest.mark.parametrize("version,spec_version,protocol", [(12, 20, OLD_PROTOCOL), (13, 21, "experiment-plan-2026-10-26-llm-round1-dh-v1"), (14, CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID)])
@pytest.mark.parametrize("snapshot", [False, True])
@pytest.mark.parametrize("label,new_text", [("D", NEW_D), ("H", NEW_H)])
def test_history_restores_snapshot_or_original_bank_without_changes(tmp_path, monkeypatch, version, spec_version, protocol, snapshot, label, new_text):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    monkeypatch.setattr(database, "engine", engine)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            participant = Participant(display_code="LLM-DH-HISTORY", group_condition="control",
                                      learning_content_version=version, experiment_spec_version=spec_version, protocol_id=protocol)
            term = Term(slug="llm_knowledge", label="LLM", description="description", display_order=1)
            db.add_all([participant, term])
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
            if version in (12, 13):
                protected = {model: deepcopy(db.execute(select(model.__table__)).mappings().all()) for model in (Participant, TutorSession, TutorTurn)}
                seed_database(db)
                seed_database(db)
                database.init_db()
                database.init_db()
                for model, rows in protected.items():
                    assert db.execute(select(model.__table__)).mappings().all() == rows
            before_json = json.dumps([turn.practice_question_json, turn.diagnosis_json, turn.grading_json], sort_keys=True)
            restored = _learning_record(db, session, turn)
            original = learning_question_spec("llm_knowledge", "enrichment", 1, content_version=version)
            selected = next(option for option in original["options"] if option["label"] == label)
            assert restored["question_body"] == ("保存時の問題" if snapshot else original["body"])
            assert restored["selected_options"] == [{"label": label, "body": "保存時の選択肢" if snapshot else selected["body"]}]
            if not snapshot:
                assert (selected["body"] == new_text) == (version >= 13)
            assert json.dumps([turn.practice_question_json, turn.diagnosis_json, turn.grading_json], sort_keys=True) == before_json
    finally:
        engine.dispose()
