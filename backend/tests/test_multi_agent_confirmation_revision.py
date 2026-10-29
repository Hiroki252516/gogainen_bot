from copy import deepcopy
import hashlib
import json

import pytest
from admin_client import AuthenticatedTestClient as TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from split_api_support import assert_learning_flow

from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID
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


SCENARIO = "自治体が、災害時に住民向けの避難案内を作成するAIシステムを開発している。このシステムでは、被害状況や道路の情報を集めるAI、集めた情報をもとに避難方法を検討するAI、検討結果から住民向けの案内文を作成するAIにそれぞれ役割を分け、前の担当が出した結果を次の担当に引き継いで案内を行うシステムを作っている。"
TASK = "この仕組みを説明する記述を3つ選びなさい。"
CHOICE_H = "1つのAIエージェントに、道路が通れる場合と通れない場合で案内内容を切り替える仕組みを設け、案内の方法が2つあるので、AIエージェントも2つ存在する。"
CHOICE_I = "性能の高いAIエージェントを1つ用意し、情報収集、避難方法の検討、住民向けの案内文作成をすべて担当させれば、複数のエージェントが連携するマルチエージェントの仕組みになる。"
PREVIOUS_PROTOCOL = "experiment-plan-2026-10-25-learning-confirmation-v1"


def test_v6_only_changes_multi_agent_first_question_and_two_m3_choices():
    assert hashlib.sha256(content_loader.LEARNING_V5_CONTENT_PATH.read_bytes()).hexdigest() == "bc413c1c9a3f25e19111757d7ea0b78e00f95f8af2a2f155e0ab79c825aed9e3"
    expected = deepcopy(load_learning_content(content_version=5))
    expected["version"] = 6
    variant = expected["terms"]["multi_agent"]["variants"][0]
    variant["scenario"] = SCENARIO
    variant["task"] = TASK
    variant["choices"]["M3"][1:] = [CHOICE_H, CHOICE_I]
    assert load_learning_content(content_version=6) == expected
    for stage in ("enrichment", "conceptual_change"):
        spec = learning_question_spec("multi_agent", stage, content_version=6)
        assert spec["body"] == SCENARIO + "\n\n" + TASK
        assert spec["scenario_type"] == "application"
        assert spec["_content_version"] == 6
        assert [option["body"] for option in spec["options"][7:9]] == [CHOICE_H, CHOICE_I]
        assert all(option["misconception_type"] == "M3" and not option["is_correct"] for option in spec["options"][7:9])
        assert spec["options"][-1]["label"] == "J"
        assert spec["options"][-1]["misconception_type"] == "unknown"


def test_missing_v6_does_not_fall_back_to_v5(tmp_path, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(content_loader, "LEARNING_V6_CONTENT_PATH", tmp_path / "missing.yml")
        load_learning_content.cache_clear()
        with pytest.raises(FileNotFoundError):
            load_learning_content(content_version=6)
    load_learning_content.cache_clear()


def test_easy_mode_cannot_load_standard_v6():
    with pytest.raises(ValueError, match="version"):
        load_learning_content("easy", 6)


@pytest.mark.parametrize("snapshot", [False, True])
@pytest.mark.parametrize("version", [3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14])
def test_multi_agent_history_restores_saved_version_without_rewriting_records(tmp_path, monkeypatch, snapshot, version):
    isolated = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    monkeypatch.setattr(database, "engine", isolated)
    Base.metadata.create_all(isolated)
    try:
        with Session(isolated) as db:
            participant = Participant(display_code="MULTI-HISTORY", group_condition="control", question_set_mode="standard",
                                      learning_content_version=version, experiment_spec_version={3: 11, 5: 12, 6: 13, 7: 14, 8: 15, 9: 16, 10: 17, 11: 18, 12: 20, 13: 21, 14: CURRENT_EXPERIMENT_SPEC_VERSION}[version],
                                      protocol_id={3: "experiment-plan-2026-10-25-pretest-f-wording-v1", 5: PREVIOUS_PROTOCOL, 6: "experiment-plan-2026-10-25-multi-agent-confirmation-v1", 7: "experiment-plan-2026-10-25-multi-agent-confirmation-v2", 8: "experiment-plan-2026-10-25-multi-agent-round2-v1", 9: "experiment-plan-2026-10-25-multi-agent-round3-v1", 10: "experiment-plan-2026-10-25-memory-confirmation-v1", 11: "experiment-plan-2026-10-26-memory-round2-v1", 12: "experiment-plan-2026-10-26-multi-memory-retests-v1", 13: "experiment-plan-2026-10-26-llm-round1-dh-v1", 14: CURRENT_PROTOCOL_ID}[version])
            term = Term(slug="multi_agent", label="マルチエージェント", description="description", display_order=2)
            db.add_all([participant, term])
            db.flush()
            session = TutorSession(participant_id=participant.id, term_id=term.id, group_condition="control", session_index=1)
            db.add(session)
            db.flush()
            question = {"body": "保存時の問題", "options": [{"option_id": "I", "label": "I", "body": "保存時の選択本文"}]} if snapshot else {}
            turn = TutorTurn(tutor_session_id=session.id, turn_index=1, teaching_strategy="general_explanation", tutor_message="保存済み教材",
                             learner_response="I", practice_question_json=question, diagnosis_json={"learning_content_version": version},
                             grading_json={"is_sufficient": False, "selected_option_ids": ["I"]})
            db.add(turn)
            db.commit()
            if version != 14:
                before = {model: deepcopy(db.execute(select(model.__table__)).mappings().all()) for model in (Participant, TutorSession, TutorTurn)}
                seed_database(db)
                seed_database(db)
                database.init_db()
                database.init_db()
                for model, rows in before.items():
                    assert db.execute(select(model.__table__)).mappings().all() == rows
            before_json = json.dumps([turn.practice_question_json, turn.diagnosis_json, turn.grading_json], sort_keys=True)
            record = _learning_record(db, session, turn)
            original = learning_question_spec("multi_agent", "enrichment", content_version=version)
            assert record["question_body"] == ("保存時の問題" if snapshot else original["body"])
            assert record["selected_options"] == [{"label": "I", "body": "保存時の選択本文" if snapshot else original["options"][8]["body"]}]
            assert json.dumps([turn.practice_question_json, turn.diagnosis_json, turn.grading_json], sort_keys=True) == before_json
            if not snapshot:
                assert (record["question_body"] == SCENARIO + "\n\n" + TASK) == (version in (6, 7, 8, 9, 10, 11, 12, 13, 14))
                assert (record["selected_options"][0]["body"] == CHOICE_I) == (version == 6)
    finally:
        isolated.dispose()


@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
@pytest.mark.parametrize("initial", ["unknown", "M1"])
@pytest.mark.parametrize("labels,expected_type", [("ABC", None), ("J", "unknown"), ("DEF", "M1"), ("ADH", "M3"), ("ADI", "M3")])
def test_current_multi_agent_display_grading_feedback_replay_and_prefetch(group, layout, initial, labels, expected_type):
    assert_learning_flow("multi_agent", group, layout, initial, labels, expected_type)
