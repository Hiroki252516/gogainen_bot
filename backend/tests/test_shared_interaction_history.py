import asyncio
import copy
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.ai.codex_app_server_backend import CodexAppServerBackend
from app.ai.interaction_history import COMMON_INPUT_KEYS, INTERACTION_HISTORY_VERSION, SHARED_QUESTION_ROUTE_VERSION, interaction_history_audit, project_model_payload
from app.ai.mock_backend import MockAIBackend
from app.ai.misconception_taxonomy import taxonomy_for_prompt
from app.ai.teaching_contract import PROMPT_CONTRACT_VERSION
from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID
from app.db import session as database
from app.db.session import SessionLocal
from app.main import app
from app.models import Attempt, Base, EvaluationSummary, Participant, Question, QuestionOption, Term, TutorSession, TutorTurn, AICallLog
from app.seed.content_loader import learning_question_spec
from app.seed.seed_questions import seed_database
from app.services import experiment
from app.services.interaction_history import build_interaction_history
from app.services.prefetch import wait_for_prefetch_tasks


client = TestClient(app)


def create_trial(group="A", labels="DEF"):
    participant = client.post("/api/participants", json={"assignment_code": group, "consent_checked": True, "student_number": "TEST-0001"}).json()
    pid = participant["participant_id"]
    questions = client.get(f"/api/experiment/{pid}/pretest").json()["questions"]
    for question in questions:
        ids = [option["option_id"] for option in question["options"] if option["label"] in labels]
        response = client.post("/api/attempts", json={"participant_id": pid, "question_id": question["question_id"], "selected_option_ids": ids})
        assert response.status_code == 200, response.text
    assert client.post(f"/api/participants/{pid}/diagnose-pretest").status_code == 200
    return pid


def start_turn(pid):
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "llm_knowledge"}).json()
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={})
    assert turn.status_code == 200, turn.text
    return session, turn.json()


def answer(turn, labels, **timing):
    ids = [option["option_id"] for option in turn["practice_question"]["options"] if option["label"] in labels]
    result = client.post(f"/api/tutor-turns/{turn['turn_id']}/respond", json={"selected_option_ids": ids, **timing})
    assert result.status_code == 200, result.text
    return result.json()


def test_history_merges_all_rounds_and_sessions_using_snapshots_without_diagnostics():
    pid = create_trial()
    other_pid = create_trial()
    base = datetime(2026, 10, 1)
    with SessionLocal() as db:
        term = db.query(Term).filter_by(slug="llm_knowledge").one()
        pretest = db.query(Attempt).filter_by(participant_id=pid, term_id=term.id, phase="pretest").one()
        pretest.answered_at = base
        pretest.question_body_snapshot = "保存当時の事前問題"
        pretest.option_order_snapshot = [{"option_id": option_id, "label": label, "body": f"保存当時の選択肢{label}", "misconception_type": "PRIVATE_DIAGNOSIS", "is_correct": False} for option_id, label in zip(pretest.selected_option_ids, "DEF")]
        for index, (phase, round_name, labels) in enumerate((("retest", "retest_1", "J"), ("retest", "retest_2", "ADG"), ("final_test", "retest_3", "ABC")), 1):
            question = db.query(Question).filter_by(term_id=term.id, phase=phase).first()
            options = db.query(QuestionOption).filter(QuestionOption.question_id == question.id, QuestionOption.option_label.in_(list(labels))).order_by(QuestionOption.default_order).all()
            db.add(Attempt(participant_id=pid, term_id=term.id, question_id=question.id, phase=phase, test_round=round_name, selected_option_ids=[row.id for row in options], is_correct=labels == "ABC", answered_at=base + timedelta(days=index), misconception_type="M3", natural_language_diagnosis="PRIVATE_REASON"))
        db.add(Attempt(participant_id=pid, term_id=term.id, question_id=pretest.question_id, phase="retest", is_correct=None))
        db.add(Attempt(participant_id=pid, term_id=term.id, question_id=pretest.question_id, phase="l0_check", is_correct=True))
        spec = learning_question_spec(term.slug, "conceptual_change", 1)
        for index in (1, 2):
            session = TutorSession(participant_id=pid, term_id=term.id, group_condition="proposed", session_index=index)
            db.add(session)
            db.flush()
            db.add(TutorTurn(tutor_session_id=session.id, turn_index=1, teaching_strategy="belief_revision", tutor_message="PRIVATE_MATERIAL", learner_prompt="保存された確認問題", practice_question_json={"body": "保存された確認問題", "options": spec["options"]}, learner_response="D / E / F", grading_json={"is_sufficient": False, "selected_option_ids": [row["option_id"] for row in spec["options"] if row["label"] in "DEF"], "learning_misconception_type": "M1", "learning_misconception_reason": "PRIVATE_REASON"}, ai_feedback="PRIVATE_FEEDBACK", answered_at=base + timedelta(days=3 + index)))
            db.add(TutorTurn(tutor_session_id=session.id, turn_index=2, teaching_strategy="belief_revision", tutor_message="UNUSED_PREFETCH", learner_prompt="未回答", practice_question_json={"body": "未回答"}))
        db.commit()
        history = build_interaction_history(db, pid, term.id)
        assert len(history) == 6
        assert [row["phase"] for row in history] == ["pretest", "retest", "retest", "final_test", "learning", "learning"]
        assert history[0]["question_body"] == "保存当時の事前問題"
        assert history[0]["selected_options"][0] == {"label": "D", "body": "保存当時の選択肢D"}
        assert history[1]["selected_options"] == [{"label": "J", "body": "わからない。"}]
        assert [row["label"] for row in history[2]["selected_options"]] == list("ADG")
        assert history[3]["is_correct"] is True
        assert [row["session_index"] for row in history[-2:]] == [1, 2]
        encoded = json.dumps(history, ensure_ascii=False)
        for private in (pid, other_pid, term.id, "PRIVATE_", "UNUSED_PREFETCH", "l0_check", "misconception", "expected_answer", "teaching_strategy", "learning_stage"):
            assert private not in encoded
        assert interaction_history_audit({"interaction_history": history})["record_count"] == 6


@pytest.mark.parametrize("group", ["A", "B"])
def test_projected_answer_history_matches_committed_history_without_writing_early(group):
    pid = create_trial(group)
    _, response = start_turn(pid)
    wait_for_prefetch_tasks()
    with SessionLocal() as db:
        turn = db.get(TutorTurn, response["turn_id"])
        session = db.get(TutorSession, turn.tutor_session_id)
        selected_ids = [row["option_id"] for row in response["practice_question"]["options"] if row["label"] in "ADG"]
        grading = {"is_sufficient": False, "selected_option_ids": selected_ids, "learning_stage": response["learning_stage"]}
        timing = {"question_shown_at": datetime(2030, 1, 1), "answered_at": datetime(2030, 1, 1, 0, 0, 10), "response_time_sec": 10.0}
        previous = build_interaction_history(db, pid, session.term_id)
        projected = build_interaction_history(db, pid, session.term_id, projected_answer={"turn": turn, "grading_json": grading, "timing": timing})
        assert len(projected) == len(previous) + 1
        assert turn.learner_response is None
        assert turn.grading_json is None
        turn.learner_response = "A / D / G"
        turn.grading_json = grading
        turn.question_shown_at = timing["question_shown_at"]
        turn.answered_at = timing["answered_at"]
        turn.response_time_sec = timing["response_time_sec"]
        db.commit()
        assert projected == build_interaction_history(db, pid, session.term_id)
        assert projected == build_interaction_history(db, pid, session.term_id, projected_answer={"turn": turn, "grading_json": grading, "timing": timing})


@pytest.mark.parametrize("method", ["generate_tutoring_turn", "generate_correct_answer_summary", "explain_selected_distractor"])
def test_control_all_tasks_use_shared_history_but_ignore_nested_diagnostic_metadata(monkeypatch, method):
    backend = CodexAppServerBackend()
    captured = []

    async def capture(purpose, prompt, schema, **kwargs):
        captured.append((prompt, schema, kwargs["audit_context"]))
        if purpose == "generate_tutoring_turn":
            return {"tutor_message": "## 用語\n説明", "teaching_strategy": "general_explanation"}
        if purpose == "generate_correct_answer_summary":
            return {"summary": "要点"}
        return {"feedback": "見直す点", "remediation_focus": "役割", "general_knowledge_supplement": None}

    monkeypatch.setattr(backend, "_run_structured_turn", capture)
    payload = {
        "group_condition": "control", "participant_id": "PRIVATE_ID",
        "term": {"slug": "memory_process", "label": "用語", "description": "共通の説明", "primary_misconception": "PRIVATE_DIAGNOSIS"},
        "component_terms": ["保存"], "rag_context": {"chunks": [{"text": "共通資料"}]},
        "interaction_history": [{"source_type": "test_attempt", "phase": "pretest", "question_body": "履歴の問題", "selected_options": [{"label": "D", "body": "履歴の回答", "is_correct": False, "misconception_type": "PRIVATE_DIAGNOSIS"}], "is_correct": False, "reason": "PRIVATE_REASON", "turn_id": "PRIVATE_ID", "learning_stage": "PRIVATE_STAGE"}],
        "active_misconception_type": "PRIVATE_DIAGNOSIS", "learner_state": {"primary_misconception": "PRIVATE_DIAGNOSIS"},
        "misconception_taxonomy": {"M1": "PRIVATE_TAXONOMY"}, "pretest_targets": [{"corrected_claim": "PRIVATE_CORRECTION"}],
        "question_body": "現在の問題", "selected_option_body": "現在の回答", "selected_option_bodies": ["現在の回答"], "material": "現在の教材",
    }
    asyncio.run(getattr(backend, method)(payload))
    changed_diagnosis = {**payload, "active_misconception_type": "OTHER_DIAGNOSIS", "learner_state": {"primary_misconception": "OTHER_DIAGNOSIS"}, "pretest_targets": []}
    asyncio.run(getattr(backend, method)(changed_diagnosis))
    changed_history = copy.deepcopy(payload)
    changed_history["interaction_history"][0]["selected_options"][0]["body"] = "変更後の回答"
    asyncio.run(getattr(backend, method)(changed_history))
    assert captured[0][0] == captured[1][0]
    assert captured[0][0] != captured[2][0]
    assert "履歴の回答" in captured[0][0]
    assert "PRIVATE_" not in captured[0][0]
    model_input = json.loads(captured[0][0].split("入力JSON:\n", 1)[1])
    assert model_input == captured[0][2]["actual_ai_input"]
    assert captured[0][2]["interaction_history"] == interaction_history_audit(payload)
    assert captured[0][2]["question_route_version"] == SHARED_QUESTION_ROUTE_VERSION
    if method == "generate_tutoring_turn":
        assert set(model_input) == set(COMMON_INPUT_KEYS)
        assert captured[0][1]["properties"]["teaching_strategy"]["enum"] == ["general_explanation"]
        assert "現在の問題" not in captured[0][0]
    else:
        assert "現在の問題" in captured[0][0]
        assert "現在の教材" in captured[0][0]
    proposed_input = project_model_payload({**payload, "group_condition": "proposed", "active_misconception_type": "M1"}, proposed=True, feedback=method != "generate_tutoring_turn")
    assert {key: proposed_input[key] for key in COMMON_INPUT_KEYS} == {key: model_input[key] for key in COMMON_INPUT_KEYS}
    assert "misconception_taxonomy" in proposed_input


@pytest.mark.parametrize("initial,following,stage", [("J", "DEF", "conceptual_change"), ("DEF", "J", "enrichment"), ("GHI", "GHI", "conceptual_change")])
def test_both_groups_share_questions_transitions_and_feedback_history(initial, following, stage):
    trials = []
    for group in ("A", "B"):
        pid = create_trial(group, initial)
        session, first = start_turn(pid)
        response = answer(first, following, question_shown_at="2030-01-01T00:00:00", answered_at="2030-01-01T00:00:10", response_time_sec=10)
        assert response["next_learning_stage"] == stage
        next_turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={})
        assert next_turn.status_code == 200, next_turn.text
        next_turn = next_turn.json()
        assert next_turn["learning_stage"] == stage
        with SessionLocal() as db:
            logs = [log for log in db.query(AICallLog).order_by(AICallLog.created_at) if log.request_payload.get("participant_id") == pid]
            first_feedback = next(log for log in logs if log.purpose == "explain_selected_distractor")
            assert len(first_feedback.request_payload["interaction_history"]) == 1
            generation = [log for log in logs if log.purpose == "generate_tutoring_turn" and (log.request_payload.get("term") or {}).get("slug") == "llm_knowledge"][-1]
            history = generation.request_payload["interaction_history"]
            assert len(history) == 2
            assert history[-1]["answered_at"] == "2030-01-01T00:00:10"
            assert [row["label"] for row in history[-1]["selected_options"]] == list(following)
            assert first_feedback.response_payload["feedback"] not in json.dumps(history, ensure_ascii=False)
            assert generation.request_payload["interaction_history_audit"]["record_count"] == 2
            assert generation.request_payload["experiment_spec_version"] == CURRENT_EXPERIMENT_SPEC_VERSION
            assert generation.request_payload["prompt_contract_version"] == PROMPT_CONTRACT_VERSION
            if group == "B":
                assert set(generation.request_payload["input_projection"]) == set(COMMON_INPUT_KEYS)
        success = answer(next_turn, "ABC")
        assert success["next_action"] == "move_next"
        assert success["is_sufficient"] is True
        trials.append((first, next_turn, success))
    assert trials[0][0]["practice_question"] == trials[1][0]["practice_question"]
    assert trials[0][1]["practice_question"] == trials[1][1]["practice_question"]
    assert trials[0][2]["next_url"] == trials[1][2]["next_url"]


@pytest.mark.parametrize("legacy_version", [1, 2, 3, 4, 5, 6])
def test_startup_repairs_only_current_version_and_preserves_old_trials(tmp_path, monkeypatch, legacy_version):
    isolated = create_engine(f"sqlite:///{tmp_path / 'versions.db'}")
    monkeypatch.setattr(database, "engine", isolated)
    Base.metadata.create_all(isolated)
    with Session(isolated) as db:
        seed_database(db)
        question = db.query(Question).filter_by(phase="pretest").first()
        old = Participant(
            display_code="OLD",
            group_condition="control",
            experiment_spec_version=legacy_version,
            protocol_id="experiment-plan-2026-10-18-v1" if legacy_version == 3 else None,
            current_step="finish",
            completed_at=datetime(2026, 10, 1),
        )
        current = Participant(display_code="CURRENT", group_condition="control", experiment_spec_version=CURRENT_EXPERIMENT_SPEC_VERSION, protocol_id=CURRENT_PROTOCOL_ID, current_step="finish", completed_at=datetime(2026, 10, 1))
        db.add_all([old, current])
        db.flush()
        for participant in (old, current):
            db.add(Attempt(participant_id=participant.id, term_id=question.term_id, question_id=question.id, phase="pretest", test_round=None))
            db.add(TutorSession(participant_id=participant.id, term_id=question.term_id, session_index=1, group_condition="control", prefetch_state=""))
            db.add(EvaluationSummary(participant_id=participant.id, group_condition="control", completed=False))
        db.commit()
        old_id, current_id = old.id, current.id
        before = [dict(row) for row in db.execute(text("SELECT * FROM participants WHERE id=:pid"), {"pid": old_id}).mappings()]
    database.init_db()
    database.init_db()
    with Session(isolated) as db:
        after = [dict(row) for row in db.execute(text("SELECT * FROM participants WHERE id=:pid"), {"pid": old_id}).mappings()]
        assert before == after
        assert db.query(Attempt).filter_by(participant_id=old_id).one().test_round is None
        assert db.query(TutorSession).filter_by(participant_id=old_id).one().prefetch_state == ""
        assert db.query(EvaluationSummary).filter_by(participant_id=old_id).one().completed is False
        assert db.get(Participant, current_id).completion_reason == "completed"
        assert db.query(Attempt).filter_by(participant_id=current_id).one().test_round == "test"
        assert db.query(TutorSession).filter_by(participant_id=current_id).one().prefetch_state == "none"
        assert db.query(EvaluationSummary).filter_by(participant_id=current_id).one().completed is True
    assert CURRENT_EXPERIMENT_SPEC_VERSION == 7
    pid = create_trial()
    with SessionLocal() as db:
        assert db.get(Participant, pid).experiment_spec_version == CURRENT_EXPERIMENT_SPEC_VERSION


def test_effective_audit_preserves_provider_input_including_retry_instructions():
    sent = {"term": {"label": "用語"}, "interaction_history": [], "mandatory_element_retry": {"missing": ["transfer_check:empty"]}}
    initial = {"term": {"label": "用語"}, "interaction_history": []}
    effective = experiment._effective_request_with_instruction_audit({"actual_ai_input": sent}, {"actual_ai_input": initial, "instruction_route": "shared_history_diagnostic"})
    assert effective["actual_ai_input"] == sent
    assert effective["instruction_route"] == "shared_history_diagnostic"


def test_history_projection_rejects_diagnostic_objects_as_observation_values():
    projected = project_model_payload({"term": {"label": "用語", "description": {"misconception_type": "PRIVATE"}}, "interaction_history": [{"question_body": {"misconception_type": "PRIVATE"}, "is_correct": {"diagnosis": "PRIVATE"}, "answered_at": {"reason": "PRIVATE"}, "selected_options": [{"label": "D", "body": {"reason": "PRIVATE"}, "diagnosis": "PRIVATE"}]}]}, proposed=False)
    assert "PRIVATE" not in json.dumps(projected)
    assert projected["interaction_history"][0]["selected_options"] == [{"label": "D"}]


def test_missing_snapshot_option_body_is_restored_from_the_question_bank():
    pid = create_trial()
    with SessionLocal() as db:
        term = db.query(Term).filter_by(slug="llm_knowledge").one()
        attempt = db.query(Attempt).filter_by(participant_id=pid, term_id=term.id).one()
        attempt.option_order_snapshot = [{"option_id": option_id, "label": "D", "body": ""} for option_id in attempt.selected_option_ids]
        db.commit()
        history = build_interaction_history(db, pid, term.id)
        assert [option["label"] for option in history[0]["selected_options"]] == list("DEF")
        assert all(option["body"] for option in history[0]["selected_options"])
