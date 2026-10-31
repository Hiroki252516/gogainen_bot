import asyncio
import csv
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from admin_client import AuthenticatedTestClient as TestClient
from sqlalchemy import create_engine, or_, text
from sqlalchemy.orm import Session

from app.ai.backend import AIBackend, strategy_for
from app.ai.codex_app_server_backend import CodexAppServerBackend
from app.ai.mock_backend import MockAIBackend
from app.ai.misconception_taxonomy import TAXONOMY_VERSION, taxonomy_for_prompt
from app.ai.teaching_contract import PROMPT_CONTRACT_VERSION
from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID
from app.db import session as database
from app.db.session import SessionLocal
from app.main import app
from app.models import Attempt, Base, EvaluationSummary, LearnerState, Participant, Question, QuestionOption, Term, TutorSession, TutorTurn
from app.seed.seed_questions import seed_database
from app.services import experiment
from app.services.idempotency import request_fingerprint
from app.models import IdempotencyRecord
from app.services.prefetch import wait_for_prefetch_tasks
from split_api_support import acknowledge_all_question_reviews, case_roles, select_roles


client = TestClient(app)


def create_trial(group="A", labels="DEF"):
    result = client.post("/api/participants", json={"assignment_code": group, "consent_checked": True, "student_number": "TEST-0001"})
    assert result.status_code == 200, result.text
    pid = result.json()["participant_id"]
    questions = client.get(f"/api/experiment/{pid}/pretest").json()["questions"]
    for question in questions:
        options = {option["label"]: option["option_id"] for option in question["options"]}
        saved = client.post("/api/attempts", json={"participant_id": pid, "question_id": question["question_id"], "selected_option_ids": select_roles(question, [case_roles(labels)[0]])})
        assert saved.status_code == 200, saved.text
    acknowledge_all_question_reviews(client, pid, "pretest")
    scored = client.post(f"/api/participants/{pid}/diagnose-pretest")
    assert scored.status_code == 200, scored.text
    return pid, questions


def trial_snapshot(db, pid):
    session_ids = [row.id for row in db.query(TutorSession).filter_by(participant_id=pid)]
    output = {}
    for table in Base.metadata.sorted_tables:
        if table.name == "participants":
            clause, params = "id = :pid", {"pid": pid}
        elif "participant_id" in table.c:
            clause, params = "participant_id = :pid", {"pid": pid}
        elif table.name == "tutor_turns":
            rows = db.query(TutorTurn).filter(TutorTurn.tutor_session_id.in_(session_ids)).all()
            output[table.name] = [{column.name: getattr(row, TutorTurn.__mapper__.get_property_by_column(column).key) for column in table.c} for row in rows]
            continue
        else:
            continue
        output[table.name] = [dict(row) for row in db.execute(text(f"SELECT * FROM {table.name} WHERE {clause} ORDER BY id"), params).mappings()]
    return json.dumps(output, default=str, sort_keys=True)


@pytest.mark.parametrize(
    "bank_version,spec_version,protocol_id",
    [
        (1, None, None), (2, None, None), (1, 1, None), (2, 1, None),
        (1, 2, None), (2, 2, None), (2, 3, None),
        (2, 3, "experiment-plan-2026-10-18-v1"), (2, 99, None),
        (3, 4, "experiment-plan-2026-10-22-v1"),
        (3, 5, "experiment-plan-2026-10-23-learning-rotation-v1"),
        (3, 6, "experiment-plan-2026-10-24-two-posttests-v1"),
        (3, 7, "experiment-plan-2026-10-24-easy-version-v1"),
        (4, 7, "experiment-plan-2026-10-24-easy-version-v1"),
        (3, 8, "experiment-plan-2026-10-25-glossary-v1"),
        (4, 8, "experiment-plan-2026-10-25-glossary-v1"),
        (3, 9, "experiment-plan-2026-10-25-pretest-improvement-v1"),
        (4, 9, "experiment-plan-2026-10-25-pretest-improvement-v1"),
        (3, 10, "experiment-plan-2026-10-25-pretest-wording-v1"),
        (4, 10, "experiment-plan-2026-10-25-pretest-wording-v1"),
        (3, 11, "experiment-plan-2026-10-25-pretest-f-wording-v1"),
        (4, 11, "experiment-plan-2026-10-25-pretest-f-wording-v1"),
        (5, 12, "experiment-plan-2026-10-25-learning-confirmation-v1"),
        (4, 12, "experiment-plan-2026-10-25-learning-confirmation-v1"),
        (6, 13, "experiment-plan-2026-10-25-multi-agent-confirmation-v1"),
        (4, 13, "experiment-plan-2026-10-25-multi-agent-confirmation-v1"),
        (7, 14, "experiment-plan-2026-10-25-multi-agent-confirmation-v2"),
        (4, 14, "experiment-plan-2026-10-25-multi-agent-confirmation-v2"),
        (8, 15, "experiment-plan-2026-10-25-multi-agent-round2-v1"),
        (4, 15, "experiment-plan-2026-10-25-multi-agent-round2-v1"),
        (9, 16, "experiment-plan-2026-10-25-multi-agent-round3-v1"),
        (4, 16, "experiment-plan-2026-10-25-multi-agent-round3-v1"),
        (10, 17, "experiment-plan-2026-10-25-memory-confirmation-v1"),
        (4, 17, "experiment-plan-2026-10-25-memory-confirmation-v1"),
        (11, 18, "experiment-plan-2026-10-26-memory-round2-v1"),
        (4, 18, "experiment-plan-2026-10-26-memory-round2-v1"),
        (12, 19, "experiment-plan-2026-10-26-llm-confirmation-retest-v1"),
        (4, 19, "experiment-plan-2026-10-26-llm-confirmation-retest-v1"),
        (12, 20, "experiment-plan-2026-10-26-multi-memory-retests-v1"),
        (4, 20, "experiment-plan-2026-10-26-multi-memory-retests-v1"),
        (13, 21, "experiment-plan-2026-10-26-llm-round1-dh-v1"),
        (4, 21, "experiment-plan-2026-10-26-llm-round1-dh-v1"),
        (14, 22, "experiment-plan-2026-10-27-multi-memory-round1-v1"),
        (4, 22, "experiment-plan-2026-10-27-multi-memory-round1-v1"),
        (14, 23, "experiment-plan-2026-10-27-llm-retest1-v1"),
        (4, 23, "experiment-plan-2026-10-27-llm-retest1-v1"),
        (14, 24, "experiment-plan-2026-10-27-multi-memory-retest1-v1"),
        (4, 24, "experiment-plan-2026-10-27-multi-memory-retest1-v1"),
        (15, 25, "experiment-plan-2026-10-27-round2-revision-v1"),
        (4, 25, "experiment-plan-2026-10-27-round2-revision-v1"),
        (15, 26, "experiment-plan-2026-10-27-test-glossary-v2"),
        (4, 26, "experiment-plan-2026-10-27-test-glossary-v2"),
        (15, 29, "experiment-plan-2026-10-30-learning-glossary-material-v1"),
    ],
)
def test_legacy_trials_reject_replays_prefetch_and_recalculation_without_writes(bank_version, spec_version, protocol_id):
    pid, questions = create_trial()
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "llm_knowledge"}).json()
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    wait_for_prefetch_tasks()
    body = {"participant_id": pid, "question_id": questions[0]["question_id"], "selected_option_ids": [option["option_id"] for option in questions[0]["options"][:3]]}
    with SessionLocal() as db:
        participant = db.get(Participant, pid)
        participant.learning_content_version = bank_version
        participant.experiment_spec_version = spec_version
        participant.protocol_id = protocol_id
        historical_turn = db.get(TutorTurn, turn["turn_id"])
        historical_turn.diagnosis_json = {key: value for key, value in historical_turn.diagnosis_json.items() if key != "material_glossary"}
        old_attempt = db.query(Attempt).filter_by(participant_id=pid, question_id=questions[0]["question_id"]).one()
        old_attempt_id = old_attempt.id
        old_attempt.legacy_selected_option_id = old_attempt.selected_option_ids[0]
        old_attempt.selected_option_ids = None
        old_attempt.question_body_snapshot = "記録当時の問題文"
        old_attempt.option_order_snapshot = [{"option_id": old_attempt.legacy_selected_option_id, "body": "記録当時の選択肢本文", "label": "D"}]
        db.add(EvaluationSummary(participant_id=pid, group_condition="proposed", pretest_score=0.125, attainment_correct_rate=0.875, completed=True))
        db.add(IdempotencyRecord(scope=f"attempt:{pid}:{body['question_id']}:auto", idempotency_key="legacy-replay", participant_id=pid, request_hash=request_fingerprint({**body, "phase": None, "response_time_sec": None, "question_shown_at": None, "answered_at": None}), status="completed", response_status=200, response_json={"saved": True}))
        db.commit()
        before = trial_snapshot(db, pid)
        for operation in (
            lambda: experiment.prepare_prefetch_sessions(db, pid, session["tutor_session_id"]),
            lambda: experiment.discard_unconsumed_prefetches(db, pid, reason="test"),
            lambda: experiment.recalculate_evaluation(db, pid),
            lambda: asyncio.run(experiment.generate_prefetched_tutor_turn(db, session["tutor_session_id"])),
        ):
            with pytest.raises(HTTPException) as caught:
                operation()
            assert caught.value.status_code == 409
            assert caught.value.detail["error_code"] == "legacy_experiment_read_only"
        assert trial_snapshot(db, pid) == before
    requests = [
        ("/api/attempts", body, {"Idempotency-Key": "legacy-replay"}),
        ("/api/attempts", {**body, "reason_text": "old body", "selected_option_id": "old"}, {}),
        (f"/api/participants/{pid}/diagnose-pretest", {}, {}),
        (f"/api/participants/{pid}/score-retest", {}, {}),
        (f"/api/participants/{pid}/score-final-test", {}, {}),
        (f"/api/participants/{pid}/give-up", {}, {}),
        (f"/api/participants/{pid}/give-up-learning", {}, {}),
        (f"/api/participants/{pid}/survey", {"old": "input"}, {}),
        (f"/api/participants/{pid}/evaluation-summary/recalculate", {}, {}),
        ("/api/tutor-sessions", {"participant_id": pid, "term_slug": "llm_knowledge"}, {}),
        (f"/api/tutor-sessions/{session['tutor_session_id']}/turns", {}, {}),
        (f"/api/tutor-turns/{turn['turn_id']}/respond", {"learner_response": "old input"}, {}),
        (f"/api/tutor-turns/{turn['turn_id']}/material-view", {}, {}),
    ]
    for path, payload, headers in requests:
        response = client.post(path, json=payload, headers=headers)
        assert response.status_code == 409, (path, response.text)
        assert response.json()["detail"]["error_code"] == "legacy_experiment_read_only"
    assert client.delete(f"/api/admin/participants/{pid}").status_code == 409
    assert client.get(f"/api/participants/{pid}/current-step").json() == {
        "step": "legacy_read_only",
        "can_resume": False,
        "next_url": "/start",
        "progress": None,
    }
    logs = client.get(f"/api/admin/participants/{pid}/logs")
    assert logs.status_code == 200
    assert logs.json()["participant"]["can_resume"] is False
    assert logs.json()["latest_evaluation_summary"]["pretest_score"] == 0.125
    assert logs.json()["tutor_sessions"][0]["turns"][0]["material_glossary"] is None
    assert "legacy_fields" in logs.json()["learner_states"][0]
    saved_attempt = next(row for row in logs.json()["attempts"] if row["attempt_id"] == old_attempt_id)
    assert saved_attempt["question_body"] == "記録当時の問題文"
    assert saved_attempt["selected_option_body"] == "記録当時の選択肢本文"
    summary = client.get("/api/admin/evaluation-summary").json()
    overview_response = client.get("/api/admin/logs/overview")
    assert overview_response.status_code == 200, overview_response.text
    overview = overview_response.json()
    old_summary = next(row for row in overview["evaluation_summaries"] if row["participant_id"] == pid)
    assert old_summary["legacy_read_only"] is True
    assert old_summary["pretest_score"] == 0.125
    assert all(row["legacy_read_only"] for row in overview["recent_answer_history"] if row["participant_id"] == pid)
    with SessionLocal() as db:
        for group in summary["groups"]:
            assert group["participant_count"] == db.query(Participant).filter_by(group_condition=group["group_condition"], experiment_spec_version=CURRENT_EXPERIMENT_SPEC_VERSION, protocol_id=CURRENT_PROTOCOL_ID).filter(or_(Participant.question_set_mode.is_(None), Participant.question_set_mode == "standard")).count()
    exported = client.get(f"/api/admin/participants/{pid}/logs.csv")
    assert exported.status_code == 200
    assert next(csv.reader(exported.text.splitlines())) == experiment.LOG_CSV_COLUMNS
    with SessionLocal() as db:
        assert trial_snapshot(db, pid) == before
    new = client.post("/api/participants", json={"assignment_code": "A", "consent_checked": True, "student_number": "TEST-0001"}).json()
    assert new["participant_id"] != pid
    with SessionLocal() as db:
        assert db.get(Participant, new["participant_id"]).retest_cycles_completed == 0


def test_fresh_seed_and_old_database_migration_preserve_history(tmp_path, monkeypatch):
    isolated = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    monkeypatch.setattr(database, "engine", isolated)
    Base.metadata.create_all(isolated)
    with Session(isolated) as db:
        seed_database(db)
        assert db.query(Question).count() == 30
        assert {phase: db.query(Question).filter_by(phase=phase).count() for phase in ("pretest", "retest", "final_test")} == {"pretest": 9, "retest": 18, "final_test": 3}
        participant = Participant(display_code="OLD", group_condition="proposed", current_step="finish", completion_reason=None)
        db.add(participant)
        db.flush()
        term = db.query(Term).first()
        old_question = Question(term_id=term.id, phase="l0_check", question_type="l0_free_response", body="historical", variant_key="legacy", construct_key="legacy")
        transfer = Question(term_id=term.id, phase="transfer", question_type="transfer", body="historical transfer", variant_key="legacy", construct_key="legacy")
        retired_variant = Question(term_id=term.id, phase="pretest", question_type="multi_select", body="historical variant", variant_key="retired_v1", construct_key="legacy")
        current_question = db.query(Question).filter_by(phase="pretest").first()
        extra_option = QuestionOption(question_id=current_question.id, option_label="K", body="historical option", default_order=11, is_correct=False)
        db.add_all([old_question, transfer, retired_variant, extra_option, EvaluationSummary(participant_id=participant.id, group_condition="proposed", pretest_score=0.5, completed=True)])
        db.flush()
        db.add(Attempt(participant_id=participant.id, term_id=current_question.term_id, question_id=current_question.id, phase="pretest", legacy_selected_option_id=extra_option.id))
        db.commit()
        before = trial_snapshot(db, participant.id)
        pid = participant.id
        seed_database(db)
        seed_database(db)
        assert db.query(Question).count() == 33
        assert db.query(Question).filter_by(is_active=True).count() == 30
        assert not old_question.is_active and not transfer.is_active
        db.refresh(retired_variant)
        assert not retired_variant.is_active
        assert db.get(QuestionOption, extra_option.id) is not None
        assert len(experiment._displayed_options(db, participant, current_question)) == 4
        assert trial_snapshot(db, pid) == before
    with isolated.begin() as connection:
        connection.execute(text("ALTER TABLE participants DROP COLUMN experiment_spec_version"))
        connection.execute(text("ALTER TABLE participants DROP COLUMN option_order_mode"))
        connection.execute(text("ALTER TABLE participants DROP COLUMN retest_cycles_completed"))
        connection.execute(text("ALTER TABLE participants DROP COLUMN learning_material_glossary_mode"))
        connection.execute(text("ALTER TABLE runtime_settings DROP COLUMN learning_material_glossary_mode"))
    database.init_db()
    database.init_db()
    with Session(isolated) as db:
        assert db.get(Participant, pid).experiment_spec_version is None
        assert db.get(Participant, pid).option_order_mode is None
        assert db.get(Participant, pid).retest_cycles_completed is None
        assert db.get(Participant, pid).learning_material_glossary_mode is None
        assert trial_snapshot(db, pid) == before
    isolated.dispose()


def test_l0_is_not_available_and_final_test_cannot_start_learning():
    pid, _ = create_trial(labels="ABC")
    assert client.get(f"/api/experiment/{pid}/l0-check").status_code == 404
    assert client.post(f"/api/participants/{pid}/score-l0-check", json={}).status_code == 404
    assert client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "llm_knowledge"}).status_code == 409
    assert client.get(f"/api/participants/{pid}/current-step").json()["step"] == "final_test"


@pytest.mark.parametrize("retired", ["selected_option_id", "free_text_answer", "reason_text", "confidence", "selected_item_option_ids", "learner_response"])
def test_current_answer_api_rejects_retired_fields(retired):
    pid, questions = create_trial()
    body = {"participant_id": pid, "question_id": questions[0]["question_id"], "selected_option_ids": [], retired: "retired"}
    assert client.post("/api/attempts", json=body).status_code == 422


@pytest.mark.parametrize("group", ["proposed", "control"])
@pytest.mark.parametrize("mtype", ["M1", "M3", "unknown"])
def test_current_effective_prompts_and_schema_lock_backend_strategy(monkeypatch, group, mtype):
    backend = CodexAppServerBackend()
    payload = {"group_condition": group, "term": {"slug": "memory_process", "label": "記憶プロセス", "description": "情報を保存し、検索して処理へ渡す仕組みです。"}, "active_misconception_type": mtype, "misconception_taxonomy": taxonomy_for_prompt(), "taxonomy_version": TAXONOMY_VERSION, "prompt_contract_version": PROMPT_CONTRACT_VERSION, "learner_state": {"primary_misconception": mtype, "scaffolding_level": "L3"}}
    captured = {}
    async def capture(purpose, prompt, schema, **kwargs):
        captured.update(prompt=prompt, schema=schema)
        return await MockAIBackend().generate_tutoring_turn(payload)
    monkeypatch.setattr(backend, "_run_structured_turn", capture)
    result = asyncio.run(backend.generate_tutoring_turn(payload))
    selected = strategy_for(mtype, None, group)
    assert captured["schema"]["properties"]["teaching_strategy"]["enum"] == [selected]
    assert result["teaching_strategy"] == selected
    for retired in ("M2", "M4", "L2", "L3", "scaffolding_level", "deep_structure_focus", "self_explanation_check", "context_transfer_training"):
        assert retired not in captured["prompt"]
        assert retired not in json.dumps(captured["schema"])
    if group == "proposed":
        assert "transfer_check" in captured["schema"]["properties"]["teaching_contract"]["required"]
        assert result["teaching_contract"]["transfer_check"]
    else:
        assert "misconception_taxonomy" not in captured["prompt"]


def test_strategy_mismatch_is_retried_then_rejected_without_mock_fallback(monkeypatch):
    payload = {"group_condition": "proposed", "active_misconception_type": "M1", "term": {"label": "記憶プロセス", "description": "情報を保存して検索します。"}}
    attempts = []
    async def fake_call(db, purpose, sent):
        attempts.append(sent["generation_attempt"])
        result = await MockAIBackend().generate_tutoring_turn(payload)
        result["teaching_strategy"] = "general_explanation"
        return result
    monkeypatch.setattr(experiment, "_ai_call", fake_call)
    monkeypatch.setattr(experiment, "_attach_generation_validation", lambda *_: None)
    with pytest.raises(HTTPException) as error:
        asyncio.run(experiment._generate_validated_tutoring_turn(None, payload))
    assert error.value.status_code == 503
    assert "teaching_strategy.mismatch" in error.value.detail["missing"]
    assert attempts == [1, 2, 3]
    for backend in (AIBackend, MockAIBackend, CodexAppServerBackend):
        for retired in ("diagnose_answer", "grade_response", "generate_feedback", "summarize_learner_state"):
            assert not hasattr(backend, retired)
