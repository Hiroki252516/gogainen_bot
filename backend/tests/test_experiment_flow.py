import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

try:
    import uvloop
except ImportError:
    uvloop = None

from app.ai.backend import strategy_for
from app.ai.codex_app_server_backend import CodexAppServerBackend, CodexAppServerError
from app.ai.mock_backend import MockAIBackend
from app.ai.misconception_taxonomy import MISCONCEPTION_TAXONOMY, TAXONOMY_VERSION
from app.ai.teaching_contract import PROMPT_CONTRACT_VERSION
from app.core.config import get_settings
from app.core.runtime_config import reset_reasoning_effort_override, set_reasoning_effort
from app.db.session import SessionLocal, _backfill_completion_reasons, _backfill_evaluation_completion_flags, engine
from app.main import app
from app.models import (
    AICallLog,
    AuditEvent,
    Attempt,
    EvaluationSummary,
    IdempotencyRecord,
    LearnerState,
    Participant,
    ParticipantSurvey,
    Question,
    QuestionDisplayOrder,
    QuestionOption,
    RecurrenceEvent,
    Term,
    TermAssignment,
    TutorSession,
    TutorTurn,
)
from app.rag.retriever import retrieve_rag_context
from app.seed.content_loader import ACTIVE_TERM_SLUGS, content_term, load_content
import app.services.experiment as experiment_service
from app import main as main_module


client = TestClient(app, backend_options={"use_uvloop": True}) if uvloop else TestClient(app)
QUESTION_SHOWN_AT = "2026-06-22T06:00:00"
ANSWERED_AT = "2026-06-22T06:00:05"


def _assignment_code_for_group(group: str) -> str:
    return {"proposed": "A", "control": "B"}[group]


def _latest_turn(turn_id: str) -> TutorTurn | None:
    db = SessionLocal()
    try:
        return db.get(TutorTurn, turn_id)
    finally:
        db.close()


def _ids_for_labels(question: dict, labels: list[str]) -> list[str]:
    by_label = {option["label"]: option["option_id"] for option in question["options"]}
    return [by_label[label] for label in labels]


def _submit_phase_questions(pid: str, phase: str, labels: list[str]) -> list[dict]:
    questions_response = client.get(f"/api/experiment/{pid}/{phase.replace('_', '-')}")
    assert questions_response.status_code == 200, questions_response.text
    questions = questions_response.json()["questions"]
    for question in questions:
        response = client.post(
            "/api/attempts",
            json={
                "participant_id": pid,
                "question_id": question["question_id"],
                "phase": phase,
                "selected_option_ids": _ids_for_labels(question, labels),
                "response_time_sec": 1.25,
                "question_shown_at": QUESTION_SHOWN_AT,
                "answered_at": ANSWERED_AT,
            },
        )
        assert response.status_code == 200, response.text
    return questions


def _submit_phase_questions_by_term(pid: str, phase: str, labels_by_term: dict[str, list[str]]) -> list[dict]:
    questions = client.get(f"/api/experiment/{pid}/{phase}").json()["questions"]
    for question in questions:
        response = client.post(
            "/api/attempts",
            json={
                "participant_id": pid,
                "question_id": question["question_id"],
                "phase": phase,
                "selected_option_ids": _ids_for_labels(question, labels_by_term[question["term_slug"]]),
            },
        )
        assert response.status_code == 200, response.text
    return questions


def _create_participant_with_pretest(group: str = "proposed", labels: list[str] | None = None) -> str:
    participant = client.post(
        "/api/participants",
        json={"assignment_code": _assignment_code_for_group(group), "consent_checked": True},
    ).json()
    pid = participant["participant_id"]
    _submit_phase_questions(pid, "pretest", labels or ["D", "E", "F"])
    diagnosis = client.post(f"/api/participants/{pid}/diagnose-pretest")
    assert diagnosis.status_code == 200, diagnosis.text
    return pid


def test_content_contract_has_three_terms_and_required_variant_counts():
    content = load_content()
    assert tuple(term["slug"] for term in content["terms"]) == ACTIVE_TERM_SLUGS
    for term in content["terms"]:
        assert len(term["questions"]["pretest"]) == 1
        assert len(term["questions"]["retest"]) == 4
        assert len(term["questions"]["final_test"]) == 1
        assert len(term["learning"]["enrichment"]["variants"]) == 5
        assert len(term["learning"]["conceptual_change"]["variants"]) == 5


def test_pretest_returns_three_multi_select_questions_with_ten_options():
    participant = client.post("/api/participants", json={"assignment_code": "A", "consent_checked": True}).json()
    questions = client.get(f"/api/experiment/{participant['participant_id']}/pretest").json()["questions"]

    assert [question["term_slug"] for question in questions] == list(ACTIVE_TERM_SLUGS)
    assert {question["test_round"] for question in questions} == {"test"}
    assert {question["test_round_label"] for question in questions} == {"テスト"}
    for question in questions:
        assert question["selection_mode"] == "multiple"
        assert question["min_selections"] == 3
        assert question["max_selections"] == 3
        assert [option["label"] for option in question["options"]] == list("ABCDEFGHIJ")
        assert len(question["options"]) == 10
        assert question["requires_reason"] is False


def test_idempotency_replays_same_attempt_and_rejects_changed_or_duplicate_answers():
    participant_response = client.post(
        "/api/participants",
        json={"assignment_code": "A", "consent_checked": True},
        headers={"Idempotency-Key": "participant-idempotency-test"},
    )
    assert participant_response.status_code == 200, participant_response.text
    repeated_participant_response = client.post(
        "/api/participants",
        json={"assignment_code": "A", "consent_checked": True},
        headers={"Idempotency-Key": "participant-idempotency-test"},
    )
    assert repeated_participant_response.status_code == 200, repeated_participant_response.text
    assert repeated_participant_response.json() == participant_response.json()

    pid = participant_response.json()["participant_id"]
    question = client.get(f"/api/experiment/{pid}/pretest").json()["questions"][0]
    body = {
        "participant_id": pid,
        "question_id": question["question_id"],
        "phase": "pretest",
        "selected_option_ids": _ids_for_labels(question, ["A", "B", "C"]),
        "response_time_sec": 1.25,
        "question_shown_at": QUESTION_SHOWN_AT,
        "answered_at": ANSWERED_AT,
    }
    first = client.post("/api/attempts", json=body, headers={"Idempotency-Key": "attempt-idempotency-test"})
    assert first.status_code == 200, first.text
    replay = client.post("/api/attempts", json=body, headers={"Idempotency-Key": "attempt-idempotency-test"})
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()

    changed_body = {**body, "selected_option_ids": _ids_for_labels(question, ["D", "E", "F"])}
    changed = client.post(
        "/api/attempts",
        json=changed_body,
        headers={"Idempotency-Key": "attempt-idempotency-test"},
    )
    assert changed.status_code == 409, changed.text
    assert changed.json()["detail"]["error_code"] == "idempotency_key_conflict"

    duplicate = client.post(
        "/api/attempts",
        json=changed_body,
        headers={"Idempotency-Key": "attempt-idempotency-new-test"},
    )
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["detail"]["error_code"] == "answer_already_submitted"

    questions_after_submit = client.get(f"/api/experiment/{pid}/pretest").json()["questions"]
    assert questions_after_submit[0]["answer_status"] == "submitted"
    assert questions_after_submit[0]["submitted_answer"]["selected_option_ids"] == body["selected_option_ids"]
    assert questions_after_submit[0]["submitted_answer"]["reason_text"] is None
    db = SessionLocal()
    try:
        assert db.query(Attempt).filter_by(participant_id=pid, question_id=question["question_id"], phase="pretest").count() == 1
        assert db.query(IdempotencyRecord).filter_by(participant_id=pid).count() >= 1
    finally:
        db.close()


def test_participant_creation_requires_consent():
    without_consent = client.post("/api/participants", json={"assignment_code": "A", "consent_checked": False})
    assert without_consent.status_code == 400
    missing_consent = client.post("/api/participants", json={"assignment_code": "A"})
    assert missing_consent.status_code == 400


def test_participant_creation_reports_database_unavailable(monkeypatch):
    def raise_database_error(*_args, **_kwargs):
        from sqlalchemy.exc import OperationalError

        raise OperationalError("INSERT", {}, ConnectionError("database is unavailable"))

    monkeypatch.setattr(main_module, "create_participant", raise_database_error)

    response = client.post("/api/participants", json={"assignment_code": "A", "consent_checked": True})

    assert response.status_code == 503
    assert response.json() == {"detail": "データベースに接続できません。管理者に確認してください。"}


def test_participant_creation_with_idempotency_key_replays_database_failure(monkeypatch):
    def raise_database_error(*_args, **_kwargs):
        from sqlalchemy.exc import OperationalError

        raise OperationalError("INSERT", {}, ConnectionError("database is unavailable"))

    monkeypatch.setattr(main_module, "create_participant", raise_database_error)
    headers = {"Idempotency-Key": "participant-db-error-replay"}

    first = client.post(
        "/api/participants",
        json={"assignment_code": "A", "consent_checked": True},
        headers=headers,
    )
    replay = client.post(
        "/api/participants",
        json={"assignment_code": "A", "consent_checked": True},
        headers=headers,
    )

    assert first.status_code == 503, first.text
    assert replay.status_code == 503, replay.text
    assert replay.json() == first.json()
    db = SessionLocal()
    try:
        record = db.query(IdempotencyRecord).filter_by(scope="participant:create", idempotency_key=headers["Idempotency-Key"]).one()
        assert record.status == "failed"
        assert record.response_status == 503
    finally:
        db.close()


def test_participant_creation_retry_after_database_error_does_not_duplicate(monkeypatch):
    from sqlalchemy.exc import OperationalError

    original_create_participant = main_module.create_participant
    call_count = 0

    def fail_once(db, assignment_code, consent_checked):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise OperationalError("INSERT", {}, ConnectionError("database is unavailable"))
        return original_create_participant(db, assignment_code, consent_checked)

    monkeypatch.setattr(main_module, "create_participant", fail_once)
    headers = {"Idempotency-Key": "participant-db-error-retry"}
    payload = {"assignment_code": "B", "consent_checked": True}

    first = client.post("/api/participants", json=payload, headers=headers)
    retry = client.post("/api/participants", json=payload, headers=headers)
    replay = client.post("/api/participants", json=payload, headers=headers)

    assert first.status_code == 503, first.text
    assert retry.status_code == 200, retry.text
    assert replay.status_code == 200, replay.text
    assert replay.json() == retry.json()
    assert call_count == 2

    participant_id = retry.json()["participant_id"]
    db = SessionLocal()
    try:
        assert db.query(Participant).filter_by(id=participant_id).count() == 1
        record = db.query(IdempotencyRecord).filter_by(scope="participant:create", idempotency_key=headers["Idempotency-Key"]).one()
        assert record.status == "completed"
        assert record.response_status == 200
    finally:
        db.close()


def test_health_reports_database_unavailable(monkeypatch):
    from sqlalchemy.exc import OperationalError

    class BrokenSession:
        rolled_back = False

        def execute(self, *_args, **_kwargs):
            raise OperationalError("SELECT 1", {}, ConnectionError("database is unavailable"))

        def rollback(self):
            self.rolled_back = True

    with pytest.raises(Exception) as raised:
        main_module.health(BrokenSession())

    assert raised.value.status_code == 503
    assert raised.value.detail == "データベースに接続できません。管理者に確認してください。"


def test_participant_creation_requires_valid_admin_assignment_code():
    for payload in (
        {"consent_checked": True},
        {"assignment_code": "C", "consent_checked": True},
        {"group_condition": "proposed", "consent_checked": True},
    ):
        response = client.post("/api/participants", json=payload)
        assert response.status_code == 400, response.text


def test_participant_creation_maps_admin_assignment_code_without_exposing_group():
    proposed_response = client.post("/api/participants", json={"assignment_code": "a", "consent_checked": True})
    control_response = client.post("/api/participants", json={"assignment_code": " b ", "consent_checked": True})
    assert proposed_response.status_code == 200, proposed_response.text
    assert control_response.status_code == 200, control_response.text
    assert "group_condition" not in proposed_response.json()
    assert "group_condition" not in control_response.json()

    db = SessionLocal()
    try:
        proposed = db.get(Participant, proposed_response.json()["participant_id"])
        control = db.get(Participant, control_response.json()["participant_id"])
        assert proposed is not None and proposed.group_condition == "proposed" and proposed.assignment_method == "admin_code"
        assert control is not None and control.group_condition == "control" and control.assignment_method == "admin_code"
    finally:
        db.close()


def test_attempt_requires_three_from_a_to_i_or_unknown_j_only():
    participant = client.post("/api/participants", json={"assignment_code": "A", "consent_checked": True}).json()
    pid = participant["participant_id"]
    question = client.get(f"/api/experiment/{pid}/pretest").json()["questions"][0]

    for labels in (["A"], ["A", "B", "C", "D"], ["A", "D", "J"]):
        response = client.post(
            "/api/attempts",
            json={"participant_id": pid, "question_id": question["question_id"], "phase": "pretest", "selected_option_ids": _ids_for_labels(question, labels)},
        )
        assert response.status_code == 400

    unknown_only = client.post(
        "/api/attempts",
        json={"participant_id": pid, "question_id": question["question_id"], "phase": "pretest", "selected_option_ids": _ids_for_labels(question, ["J"])},
    )
    assert unknown_only.status_code == 200


def test_pretest_scoring_correct_m1_m3_unknown_and_snapshots():
    cases = [
        (["A", "B", "C"], True, None, "stable_correct"),
        (["A", "B", "D"], False, "M1", "misconception"),
        (["A", "D", "G"], False, "M3", "misconception"),
        (["D", "E", "F"], False, "M1", "misconception"),
        (["G", "H", "I"], False, "M3", "misconception"),
        (["J"], False, "unknown", "unknown"),
    ]
    for labels, is_correct, misconception_type, status in cases:
        pid = _create_participant_with_pretest(labels=labels)
        db = SessionLocal()
        try:
            attempts = db.query(Attempt).filter_by(participant_id=pid, phase="pretest").all()
            assert len(attempts) == 3
            assert all(attempt.is_correct is is_correct for attempt in attempts)
            assert all(attempt.misconception_type == misconception_type for attempt in attempts)
            assert all(attempt.diagnosed_status == status for attempt in attempts)
            assert all(attempt.selected_option_ids for attempt in attempts)
            assert all(attempt.question_shown_at.isoformat() == QUESTION_SHOWN_AT for attempt in attempts)
            assert all(attempt.answered_at.isoformat() == ANSWERED_AT for attempt in attempts)
            assert all(len(attempt.option_order_snapshot) == 10 for attempt in attempts)
        finally:
            db.close()


def test_learning_routes_m1_to_conceptual_change_and_unknown_to_enrichment():
    m1_pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    m1_session = client.post("/api/tutor-sessions", json={"participant_id": m1_pid, "term_slug": "llm_knowledge"}).json()
    m1_turn = client.post(f"/api/tutor-sessions/{m1_session['tutor_session_id']}/turns", json={}).json()
    assert m1_turn["learning_stage"] == "conceptual_change"
    assert m1_turn["learning_stage_label"] == "概念変化"
    assert m1_turn["practice_question"]["selection_mode"] == "multiple"

    unknown_pid = _create_participant_with_pretest(labels=["J"])
    unknown_session = client.post("/api/tutor-sessions", json={"participant_id": unknown_pid, "term_slug": "llm_knowledge"}).json()
    unknown_turn = client.post(f"/api/tutor-sessions/{unknown_session['tutor_session_id']}/turns", json={}).json()
    assert unknown_turn["learning_stage"] == "enrichment"
    assert unknown_turn["learning_stage_label"] == "豊富化"


def test_learning_target_display_reflects_m1_m3_and_unknown_diagnoses():
    cases = [
        (["D", "E", "F"], "概念についての個別の説明に関する捉え方を見直します。", "概念変化"),
        (["G", "H", "I"], "概念の分類や位置づけに関する捉え方を見直します。", "概念変化"),
        (["J"], "基本知識が不足している可能性があります。", "豊富化"),
    ]
    for labels, expected_summary, expected_stage in cases:
        pid = _create_participant_with_pretest(labels=labels)
        response = client.get(f"/api/participants/{pid}/learning-targets")
        assert response.status_code == 200, response.text
        target = next(item for item in response.json()["targets"] if item["term_slug"] == "llm_knowledge")
        assert target["summary_for_learner"] == expected_summary
        assert target["current_stage_for_display"] == expected_stage


def test_admin_learner_state_stage_uses_diagnosis_for_misconception_and_unknown():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    db = SessionLocal()
    try:
        terms = {term.slug: term.id for term in db.query(Term).all()}
        states = {state.term_id: state for state in db.query(LearnerState).filter_by(participant_id=pid).all()}
        states[terms["llm_knowledge"]].current_status = "misconception"
        states[terms["llm_knowledge"]].primary_misconception = "M3"
        states[terms["llm_knowledge"]].scaffolding_level = "L3"
        states[terms["memory_process"]].current_status = "unknown"
        states[terms["memory_process"]].primary_misconception = "unknown"
        states[terms["memory_process"]].scaffolding_level = "L2"
        db.commit()
    finally:
        db.close()

    response = client.get(f"/api/admin/participants/{pid}/logs")
    assert response.status_code == 200, response.text
    states = {row["term_slug"]: row for row in response.json()["learner_states"]}
    assert states["llm_knowledge"]["current_stage_for_display"] == "概念変化"
    assert states["memory_process"]["current_stage_for_display"] == "豊富化"


def test_admin_overview_returns_only_latest_evaluation_summary_per_participant():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    assert client.post(f"/api/participants/{pid}/evaluation-summary/recalculate").status_code == 200
    assert client.post(f"/api/participants/{pid}/evaluation-summary/recalculate").status_code == 200

    response = client.get("/api/admin/logs/overview")
    assert response.status_code == 200, response.text
    summaries = [row for row in response.json()["evaluation_summaries"] if row["participant_id"] == pid]
    assert len(summaries) == 1


def test_db_backfill_uses_give_up_audit_for_completion_metadata():
    participant = client.post("/api/participants", json={"assignment_code": "A", "consent_checked": True}).json()
    pid = participant["participant_id"]
    db = SessionLocal()
    try:
        row = db.get(Participant, pid)
        assert row is not None
        row.current_step = "finish"
        row.completed_at = row.created_at
        row.completion_reason = None
        db.add(
            AuditEvent(
                actor="participant",
                action="give_up_experiment",
                entity_type="participant",
                entity_id=pid,
                before_json={"current_step": "retest"},
                after_json={"current_step": "finish", "completion_reason": "give_up"},
            )
        )
        db.add(EvaluationSummary(participant_id=pid, group_condition=row.group_condition, completed=True))
        db.commit()
    finally:
        db.close()

    with engine.begin() as connection:
        _backfill_completion_reasons(connection)
        _backfill_evaluation_completion_flags(connection)

    db = SessionLocal()
    try:
        row = db.get(Participant, pid)
        summary = db.query(EvaluationSummary).filter_by(participant_id=pid).one()
        assert row is not None
        assert row.completion_reason == "give_up"
        assert summary.completed is False
    finally:
        db.close()


def test_attempts_cannot_be_saved_for_wrong_phase_or_after_pretest():
    participant = client.post("/api/participants", json={"assignment_code": "A", "consent_checked": True}).json()
    pid = participant["participant_id"]
    questions = client.get(f"/api/experiment/{pid}/pretest").json()["questions"]
    for question in questions:
        response = client.post(
            "/api/attempts",
            json={
                "participant_id": pid,
                "question_id": question["question_id"],
                "phase": "pretest",
                "selected_option_ids": _ids_for_labels(question, ["A", "B", "C"]),
            },
        )
        assert response.status_code == 200, response.text
    assert client.post(f"/api/participants/{pid}/diagnose-pretest").status_code == 200

    pretest_question = questions[0]
    after_diagnosis = client.post(
        "/api/attempts",
        json={
            "participant_id": pid,
            "question_id": pretest_question["question_id"],
            "phase": "pretest",
            "selected_option_ids": _ids_for_labels(pretest_question, ["A", "B", "C"]),
        },
    )
    assert after_diagnosis.status_code == 409

    retest_question = client.get(f"/api/experiment/{pid}/final-test").json()["questions"][0]
    wrong_phase = client.post(
        "/api/attempts",
        json={
            "participant_id": pid,
            "question_id": retest_question["question_id"],
            "phase": "pretest",
            "selected_option_ids": _ids_for_labels(retest_question, ["A", "B", "C"]),
        },
    )
    assert wrong_phase.status_code == 400


def test_learning_targets_returns_all_pretest_results_without_internal_labels():
    participant = client.post("/api/participants", json={"assignment_code": "A", "consent_checked": True}).json()
    pid = participant["participant_id"]
    questions = client.get(f"/api/experiment/{pid}/pretest").json()["questions"]
    labels_by_term = {
        "llm_knowledge": ["A", "B", "C"],
        "multi_agent": ["G", "H", "I"],
        "memory_process": ["J"],
    }
    for question in questions:
        response = client.post(
            "/api/attempts",
            json={
                "participant_id": pid,
                "question_id": question["question_id"],
                "phase": "pretest",
                "selected_option_ids": _ids_for_labels(question, labels_by_term[question["term_slug"]]),
                "response_time_sec": 1.25,
                "question_shown_at": QUESTION_SHOWN_AT,
                "answered_at": ANSWERED_AT,
            },
        )
        assert response.status_code == 200, response.text
    diagnosis = client.post(f"/api/participants/{pid}/diagnose-pretest")
    assert diagnosis.status_code == 200, diagnosis.text

    response = client.get(f"/api/participants/{pid}/learning-targets")
    assert response.status_code == 200, response.text
    payload = response.json()
    results = payload["pretest_results"]
    assert [result["term_slug"] for result in results] == list(ACTIVE_TERM_SLUGS)
    assert [result["is_correct"] for result in results] == [True, False, False]
    assert [result["result_label"] for result in results] == ["正解", "不正解", "不正解"]
    assert [result["is_learning_target"] for result in results] == [False, True, True]
    assert "概念の分類や位置づけに関する捉え方を見直します。" in results[1]["result_summary"]
    assert results[2]["result_summary"] == "基本知識が不足している可能性があります。"
    assert all("misconception_type" not in result for result in results)
    assert all("M1" not in str(result) and "M3" not in str(result) for result in results)

    test_results = payload["test_results"]
    assert test_results["test_round"] == "test"
    assert test_results["test_round_label"] == "テスト"
    assert [result["term_slug"] for result in test_results["results"]] == list(ACTIVE_TERM_SLUGS)
    assert all(result["question_body"] for result in test_results["results"])
    assert [result["is_correct"] for result in test_results["results"]] == [True, False, False]
    assert [result["result_label"] for result in test_results["results"]] == ["正解", "不正解", "不正解"]
    assert all(result["selected_options"] for result in test_results["results"])
    assert all(
        "correct_answer" not in result
        and "expected_answer" not in result
        and all("is_correct" not in option for option in result["selected_options"])
        for result in test_results["results"]
    )


def test_learning_targets_follow_pretest_order_not_diagnosis_priority():
    participant = client.post("/api/participants", json={"assignment_code": "A", "consent_checked": True}).json()
    pid = participant["participant_id"]
    _submit_phase_questions_by_term(
        pid,
        "pretest",
        {
            "llm_knowledge": ["J"],
            "multi_agent": ["G", "H", "I"],
            "memory_process": ["D", "E", "F"],
        },
    )
    diagnosis = client.post(f"/api/participants/{pid}/diagnose-pretest")
    assert diagnosis.status_code == 200, diagnosis.text

    response = client.get(f"/api/participants/{pid}/learning-targets")
    assert response.status_code == 200, response.text
    assert [target["term_slug"] for target in response.json()["targets"]] == list(ACTIVE_TERM_SLUGS)


def test_learning_answer_correct_completes_and_incorrect_routes_by_type():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "llm_knowledge"}).json()
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()

    mixed_unknown = client.post(
        f"/api/tutor-turns/{turn['turn_id']}/respond",
        json={"selected_option_ids": _ids_for_labels(turn["practice_question"], ["A", "D", "J"])},
    )
    assert mixed_unknown.status_code == 400

    wrong = client.post(
        f"/api/tutor-turns/{turn['turn_id']}/respond",
        json={"selected_option_ids": _ids_for_labels(turn["practice_question"], ["A", "D", "G"])},
    ).json()
    assert wrong["is_sufficient"] is False
    assert wrong["next_learning_stage"] == "conceptual_change"
    assert wrong["learning_misconception_type"] == "M3"

    retry = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert retry["learning_stage"] == "conceptual_change"
    correct = client.post(
        f"/api/tutor-turns/{retry['turn_id']}/respond",
        json={"selected_option_ids": _ids_for_labels(retry["practice_question"], ["A", "B", "C"]), "response_time_sec": 2.5, "question_shown_at": QUESTION_SHOWN_AT, "answered_at": ANSWERED_AT},
    ).json()
    assert correct["is_sufficient"] is True
    assert correct["session_completed"] is True
    assert correct["next_learning_stage"] == "final_feedback"
    saved_turn = _latest_turn(retry["turn_id"])
    assert saved_turn is not None
    assert saved_turn.response_time_sec == 2.5
    assert saved_turn.grading_json["selected_option_ids"] == ["A", "B", "C"]

    assert correct["next_url"] == "/learning/multi_agent"
    assert client.get(f"/api/participants/{pid}/current-step").json() == {
        "step": "learning_targets",
        "next_url": "/learning-targets",
    }
    targets = client.get(f"/api/participants/{pid}/learning-targets").json()["targets"]
    assert [target["term_slug"] for target in targets] == ["multi_agent", "memory_process"]
    stale_session = client.post(
        "/api/tutor-sessions",
        json={"participant_id": pid, "term_slug": "llm_knowledge"},
    )
    assert stale_session.status_code == 409
    assert "現在の学習対象ではありません" in stale_session.text


def test_idempotency_replays_learning_session_turn_and_feedback_without_duplicates():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    session_body = {"participant_id": pid, "term_slug": "llm_knowledge"}
    session = client.post(
        "/api/tutor-sessions",
        json=session_body,
        headers={"Idempotency-Key": "learning-session-idempotency-test"},
    )
    assert session.status_code == 200, session.text
    repeated_session = client.post(
        "/api/tutor-sessions",
        json=session_body,
        headers={"Idempotency-Key": "learning-session-idempotency-test"},
    )
    assert repeated_session.status_code == 200, repeated_session.text
    assert repeated_session.json() == session.json()

    session_id = session.json()["tutor_session_id"]
    turn = client.post(
        f"/api/tutor-sessions/{session_id}/turns",
        json={},
        headers={"Idempotency-Key": "learning-turn-idempotency-test"},
    )
    assert turn.status_code == 200, turn.text
    repeated_turn = client.post(
        f"/api/tutor-sessions/{session_id}/turns",
        json={},
        headers={"Idempotency-Key": "learning-turn-idempotency-test"},
    )
    assert repeated_turn.status_code == 200, repeated_turn.text
    assert repeated_turn.json() == turn.json()

    turn_id = turn.json()["turn_id"]
    response_body = {"selected_option_ids": _ids_for_labels(turn.json()["practice_question"], ["A", "D", "G"])}
    response = client.post(
        f"/api/tutor-turns/{turn_id}/respond",
        json=response_body,
        headers={"Idempotency-Key": "learning-response-idempotency-test"},
    )
    assert response.status_code == 200, response.text
    repeated_response = client.post(
        f"/api/tutor-turns/{turn_id}/respond",
        json=response_body,
        headers={"Idempotency-Key": "learning-response-idempotency-test"},
    )
    assert repeated_response.status_code == 200, repeated_response.text
    assert repeated_response.json() == response.json()

    next_turn = client.post(
        f"/api/tutor-sessions/{session_id}/turns",
        json={},
        headers={"Idempotency-Key": "learning-next-turn-idempotency-test"},
    )
    assert next_turn.status_code == 200, next_turn.text
    assert next_turn.json()["turn_id"] != turn_id
    assert next_turn.json()["turn_index"] == turn.json()["turn_index"] + 1
    repeated_next_turn = client.post(
        f"/api/tutor-sessions/{session_id}/turns",
        json={},
        headers={"Idempotency-Key": "learning-next-turn-idempotency-test"},
    )
    assert repeated_next_turn.status_code == 200, repeated_next_turn.text
    assert repeated_next_turn.json() == next_turn.json()

    db = SessionLocal()
    try:
        before_ai_log_count = db.query(AICallLog).filter(AICallLog.request_payload["participant_id"].as_string() == pid).count()
    finally:
        db.close()
    duplicate_response = client.post(
        f"/api/tutor-turns/{turn_id}/respond",
        json={"selected_option_ids": _ids_for_labels(turn.json()["practice_question"], ["A", "B", "C"])},
        headers={"Idempotency-Key": "learning-response-another-key"},
    )
    assert duplicate_response.status_code == 409, duplicate_response.text
    assert duplicate_response.json()["detail"]["error_code"] == "answer_already_submitted"

    db = SessionLocal()
    try:
        assert db.query(TutorSession).filter_by(participant_id=pid).count() == 1
        assert db.query(TutorTurn).filter_by(tutor_session_id=session_id).count() == 2
        assert db.query(AICallLog).filter(AICallLog.request_payload["participant_id"].as_string() == pid).count() == before_ai_log_count
    finally:
        db.close()


def test_learning_answer_generates_feedback_with_group_specific_payloads():
    proposed_pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    proposed_session = client.post("/api/tutor-sessions", json={"participant_id": proposed_pid, "term_slug": "multi_agent"}).json()
    proposed_turn = client.post(f"/api/tutor-sessions/{proposed_session['tutor_session_id']}/turns", json={}).json()
    proposed_wrong = client.post(
        f"/api/tutor-turns/{proposed_turn['turn_id']}/respond",
        json={"selected_option_ids": _ids_for_labels(proposed_turn["practice_question"], ["A", "D", "G"])},
    )
    assert proposed_wrong.status_code == 200, proposed_wrong.text
    assert "## どこが違うか" in proposed_wrong.json()["feedback"]

    control_pid = _create_participant_with_pretest(group="control", labels=["D", "E", "F"])
    control_session = client.post("/api/tutor-sessions", json={"participant_id": control_pid, "term_slug": "multi_agent"}).json()
    control_turn = client.post(f"/api/tutor-sessions/{control_session['tutor_session_id']}/turns", json={}).json()
    control_wrong = client.post(
        f"/api/tutor-turns/{control_turn['turn_id']}/respond",
        json={"selected_option_ids": _ids_for_labels(control_turn["practice_question"], ["A", "D", "G"])},
    )
    assert control_wrong.status_code == 200, control_wrong.text

    correct_pid = _create_participant_with_pretest(labels=["A", "B", "C"])
    correct_session = client.post("/api/tutor-sessions", json={"participant_id": correct_pid, "term_slug": "memory_process"}).json()
    correct_turn = client.post(f"/api/tutor-sessions/{correct_session['tutor_session_id']}/turns", json={}).json()
    correct = client.post(
        f"/api/tutor-turns/{correct_turn['turn_id']}/respond",
        json={"selected_option_ids": _ids_for_labels(correct_turn["practice_question"], ["A", "B", "C"])},
    )
    assert correct.status_code == 200, correct.text
    assert "## 今回の要点" in correct.json()["feedback"]

    db = SessionLocal()
    try:
        explanation_logs = db.query(AICallLog).filter(AICallLog.purpose.in_(["generate_correct_answer_summary", "explain_selected_distractor"])).all()
        proposed_log = next(log for log in reversed(explanation_logs) if log.request_payload.get("participant_id") == proposed_pid)
        control_log = next(log for log in reversed(explanation_logs) if log.request_payload.get("participant_id") == control_pid)
        summary_log = next(log for log in reversed(explanation_logs) if log.request_payload.get("participant_id") == correct_pid)
        tutoring_logs = db.query(AICallLog).filter_by(purpose="generate_tutoring_turn").all()
        proposed_tutoring_log = next(log for log in reversed(tutoring_logs) if log.request_payload.get("participant_id") == proposed_pid)
        control_tutoring_log = next(log for log in reversed(tutoring_logs) if log.request_payload.get("participant_id") == control_pid)
        assert proposed_log.purpose == "explain_selected_distractor"
        assert proposed_log.request_payload["misconception_taxonomy"] == MISCONCEPTION_TAXONOMY
        assert "session_misconception_history" in proposed_log.request_payload
        assert control_log.purpose == "explain_selected_distractor"
        assert "misconception_taxonomy" not in control_log.request_payload
        assert "learner_state" not in control_log.request_payload
        assert "session_misconception_history" not in control_log.request_payload
        assert summary_log.purpose == "generate_correct_answer_summary"
        assert proposed_log.request_payload["rag_context"] == proposed_tutoring_log.request_payload["rag_context"]
        assert control_log.request_payload["rag_context"] == control_tutoring_log.request_payload["rag_context"]
    finally:
        db.close()


def test_next_learning_material_retains_previous_context_but_excludes_feedback():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "multi_agent"}).json()
    first_turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    first_result = client.post(
        f"/api/tutor-turns/{first_turn['turn_id']}/respond",
        json={"selected_option_ids": _ids_for_labels(first_turn["practice_question"], ["A", "D", "G"])},
    )
    assert first_result.status_code == 200, first_result.text
    previous_turn = _latest_turn(first_turn["turn_id"])
    assert previous_turn is not None
    assert previous_turn.ai_feedback == first_result.json()["feedback"]

    next_turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={})
    assert next_turn.status_code == 200, next_turn.text
    next_material = next_turn.json()["tutor_message"]
    assert f"前の問題: {first_turn['practice_question']['body']}" in next_material
    assert f"あなたの回答: {previous_turn.learner_response}" in next_material
    assert previous_turn.ai_feedback not in next_material
    assert "振り返り:" not in next_material

    db = SessionLocal()
    try:
        next_generation_log = (
            db.query(AICallLog)
            .filter_by(purpose="generate_tutoring_turn")
            .order_by(AICallLog.created_at.desc())
            .all()
        )
        next_generation_log = next(
            log for log in next_generation_log if log.request_payload.get("participant_id") == pid
        )
        assert next_generation_log.request_payload["previous_practice_question"] == first_turn["practice_question"]["body"]
        assert next_generation_log.request_payload["previous_learner_response"] == previous_turn.learner_response
        assert "previous_feedback_for_learner" not in next_generation_log.request_payload
        assert previous_turn.ai_feedback not in str(next_generation_log.request_payload)
        assert next_generation_log.request_payload["previous_learning_misconception"]["misconception_type"] == "M3"
        assert next_generation_log.request_payload["session_misconception_history"]
    finally:
        db.close()


def test_new_tutor_session_does_not_reuse_previous_session_context():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    first_session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "multi_agent"}).json()
    first_turn = client.post(f"/api/tutor-sessions/{first_session['tutor_session_id']}/turns", json={}).json()
    answer = client.post(
        f"/api/tutor-turns/{first_turn['turn_id']}/respond",
        json={"selected_option_ids": _ids_for_labels(first_turn["practice_question"], ["A", "D", "G"])},
    )
    assert answer.status_code == 200, answer.text

    db = SessionLocal()
    try:
        stored_session = db.get(TutorSession, first_session["tutor_session_id"])
        assert stored_session is not None
        stored_session.ended_at = stored_session.started_at
        db.commit()
    finally:
        db.close()

    second_session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "multi_agent"}).json()
    assert second_session["tutor_session_id"] != first_session["tutor_session_id"]
    second_turn = client.post(f"/api/tutor-sessions/{second_session['tutor_session_id']}/turns", json={})
    assert second_turn.status_code == 200, second_turn.text
    second_material = second_turn.json()["tutor_message"]
    assert "前の問題:" not in second_material
    assert "あなたの回答:" not in second_material

    db = SessionLocal()
    try:
        generation_log = (
            db.query(AICallLog)
            .filter_by(purpose="generate_tutoring_turn")
            .order_by(AICallLog.created_at.desc())
            .first()
        )
        assert generation_log is not None
        assert generation_log.request_payload["participant_id"] == pid
        assert generation_log.request_payload["previous_practice_question"] == ""
        assert generation_log.request_payload["previous_learner_response"] == ""
    finally:
        db.close()


def test_previous_turn_prefix_supports_items_and_missing_response():
    previous_turn = SimpleNamespace(
        practice_question_json={"items": [{"body": "第一問"}, {"body": "第二問"}]},
        learner_response=None,
    )

    assert experiment_service._previous_turn_prefix(previous_turn) == "前の問題: 第一問 / 第二問\n\n"


def test_learning_answer_does_not_commit_turn_when_explanation_fails(monkeypatch):
    class FailingBackend:
        provider = "codex_app_server"

        async def explain_selected_distractor(self, payload):
            raise CodexAppServerError("turn_failed", "解説生成に失敗しました。")

    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "llm_knowledge"}).json()
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    monkeypatch.setattr(experiment_service, "get_ai_backend", lambda reasoning_effort=None: FailingBackend())
    response = client.post(
        f"/api/tutor-turns/{turn['turn_id']}/respond",
        json={"selected_option_ids": _ids_for_labels(turn["practice_question"], ["A", "D", "G"])},
        headers={"Idempotency-Key": "learning-failure-idempotency-test"},
    )
    assert response.status_code == 503
    saved_turn = _latest_turn(turn["turn_id"])
    assert saved_turn is not None
    assert saved_turn.learner_response is None
    assert saved_turn.grading_json is None

    db = SessionLocal()
    try:
        failed_log = (
            db.query(AICallLog)
            .filter_by(purpose="explain_selected_distractor", status="failed")
            .order_by(AICallLog.created_at.desc())
            .first()
        )
        assert failed_log is not None
        assert failed_log.request_payload["participant_id"] == pid
        record = db.query(IdempotencyRecord).filter_by(
            scope=f"tutor_turn_respond:{turn['turn_id']}",
            idempotency_key="learning-failure-idempotency-test",
        ).one()
        assert record.status == "failed"
        assert record.response_status == 503
    finally:
        db.close()


def test_control_group_logs_same_stage_but_uses_general_explanation():
    pid = _create_participant_with_pretest(group="control", labels=["G", "H", "I"])
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "llm_knowledge"}).json()
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()

    assert turn["learning_stage"] == "conceptual_change"
    assert turn["teaching_strategy"] == "general_explanation"
    assert turn["tutor_message"]
    assert turn["practice_question"]["selection_mode"] == "multiple"


def test_retest_uses_four_variants_then_reuses_variant_four():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    observed: list[str] = []
    for _ in range(5):
        questions = client.get(f"/api/experiment/{pid}/retest").json()["questions"]
        assert len(questions) == 3
        target_question = next(question for question in questions if question["term_slug"] == "llm_knowledge")
        observed.append(target_question["body"])
        for question in questions:
            response = client.post(
                "/api/attempts",
                json={"participant_id": pid, "question_id": question["question_id"], "phase": "retest", "selected_option_ids": _ids_for_labels(question, ["D", "E", "F"])},
            )
            assert response.status_code == 200, response.text
        score = client.post(f"/api/participants/{pid}/score-retest")
        assert score.status_code == 200, score.text
        assert score.json()["next_step"] == "learning_targets"
        assert score.json()["learning_target_slugs"] == list(ACTIVE_TERM_SLUGS)
    assert len(set(observed[:4])) == 4
    assert observed[4] == observed[3]


def test_retest_non_mastery_routes_to_first_failed_learning_session_and_blocks_final_test():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    _submit_phase_questions_by_term(
        pid,
        "retest",
        {
            "llm_knowledge": ["A", "B", "C"],
            "multi_agent": ["D", "E", "F"],
            "memory_process": ["A", "B", "C"],
        },
    )

    score = client.post(f"/api/participants/{pid}/score-retest")
    assert score.status_code == 200, score.text
    payload = score.json()
    assert payload["next_step"] == "learning_targets"
    assert payload["next_url"] == "/learning/multi_agent"
    assert payload["learning_target_slugs"] == ["multi_agent"]
    assert client.get(f"/api/participants/{pid}/current-step").json()["step"] == "learning_targets"
    assert client.get(f"/api/experiment/{pid}/final-test").status_code == 409
    assert client.post(f"/api/participants/{pid}/score-final-test").status_code == 409

    result_payload = client.get(f"/api/participants/{pid}/learning-targets").json()["test_results"]
    assert result_payload["test_round"] == "retest_1"
    assert result_payload["test_round_label"] == "再テスト1"
    assert [result["is_correct"] for result in result_payload["results"]] == [True, False, True]
    assert all(result["question_body"] for result in result_payload["results"])
    assert all(result["selected_options"] for result in result_payload["results"])
    assert all("correct_answer" not in result and "expected_answer" not in result for result in result_payload["results"])

    db = SessionLocal()
    try:
        final_question = db.query(Question).filter_by(phase="final_test").join(Term).filter(Term.slug == "llm_knowledge").one()
    finally:
        db.close()
    blocked_attempt = client.post(
        "/api/attempts",
        json={
            "participant_id": pid,
            "question_id": final_question.id,
            "phase": "final_test",
            "selected_option_ids": [],
        },
    )
    assert blocked_attempt.status_code == 409


def test_retest_non_mastery_returns_failed_terms_in_pretest_order():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    _submit_phase_questions_by_term(
        pid,
        "retest",
        {
            "llm_knowledge": ["J"],
            "multi_agent": ["G", "H", "I"],
            "memory_process": ["D", "E", "F"],
        },
    )

    score = client.post(f"/api/participants/{pid}/score-retest")
    assert score.status_code == 200, score.text
    payload = score.json()
    assert payload["next_step"] == "learning_targets"
    assert payload["next_url"] == "/learning/llm_knowledge"
    assert payload["learning_target_slugs"] == list(ACTIVE_TERM_SLUGS)
    targets = client.get(f"/api/participants/{pid}/learning-targets")
    assert targets.status_code == 200, targets.text
    assert targets.json()["current_step"] == "learning_targets"
    assert [target["term_slug"] for target in targets.json()["targets"]] == list(ACTIVE_TERM_SLUGS)


def test_incomplete_retest_keeps_unanswered_term_as_learning_target():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    questions = client.get(f"/api/experiment/{pid}/retest").json()["questions"]
    for question in questions:
        if question["term_slug"] == "memory_process":
            continue
        response = client.post(
            "/api/attempts",
            json={
                "participant_id": pid,
                "question_id": question["question_id"],
                "phase": "retest",
                "selected_option_ids": _ids_for_labels(question, ["A", "B", "C"]),
            },
        )
        assert response.status_code == 200, response.text

    score = client.post(f"/api/participants/{pid}/score-retest")
    assert score.status_code == 200, score.text
    payload = score.json()
    assert payload["next_step"] == "learning_targets"
    assert payload["next_url"] == "/learning/memory_process"
    assert payload["learning_target_slugs"] == ["memory_process"]

    result_payload = client.get(f"/api/participants/{pid}/learning-targets").json()["test_results"]
    assert result_payload["test_round"] == "retest_1"
    unanswered = next(result for result in result_payload["results"] if result["term_slug"] == "memory_process")
    assert unanswered["is_correct"] is None
    assert unanswered["result_label"] == "未回答"
    assert unanswered["question_body"]
    assert unanswered["selected_options"] == []


def test_learning_give_up_routes_to_retest_and_closes_current_session():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    session_response = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "llm_knowledge"})
    assert session_response.status_code == 200, session_response.text
    session_id = session_response.json()["tutor_session_id"]
    turn_response = client.post(f"/api/tutor-sessions/{session_id}/turns", json={})
    assert turn_response.status_code == 200, turn_response.text
    turn_id = turn_response.json()["turn_id"]

    give_up = client.post(f"/api/participants/{pid}/give-up-learning")
    assert give_up.status_code == 200, give_up.text
    assert give_up.json()["next_step"] == "retest"
    assert give_up.json()["next_url"] == "/retest"
    assert client.get(f"/api/participants/{pid}/current-step").json() == {"step": "retest", "next_url": "/retest"}
    assert client.get(f"/api/experiment/{pid}/retest").status_code == 200
    participant_logs = client.get(f"/api/admin/participants/{pid}/logs")
    assert participant_logs.status_code == 200, participant_logs.text
    participant_logs_payload = participant_logs.json()
    assert participant_logs_payload["participant"]["completion_reason"] is None
    assert participant_logs_payload["participant"]["give_up_learning_count"] == 1
    assert any(event["action"] == "give_up_learning" for event in participant_logs_payload["audit_events"])

    admin_row = next(row for row in client.get("/api/admin/participants").json()["participants"] if row["participant_id"] == pid)
    assert admin_row["completion_reason"] is None
    assert admin_row["give_up_learning_count"] == 1
    overview = client.get("/api/admin/logs/overview").json()
    assert any(event["display_code"] == admin_row["display_code"] and event["action"] == "give_up_learning" for event in overview["recent_audit_events"])

    assert client.post(f"/api/tutor-sessions/{session_id}/turns", json={}).status_code == 409
    assert client.post(f"/api/tutor-turns/{turn_id}/respond", json={"selected_option_ids": []}).status_code == 409
    assert client.post(
        "/api/tutor-sessions",
        json={"participant_id": pid, "term_slug": "llm_knowledge"},
    ).status_code == 409

    db = SessionLocal()
    try:
        session = db.get(TutorSession, session_id)
        assert session is not None
        assert session.ended_at is not None
        audit = db.query(AuditEvent).filter_by(entity_type="participant", entity_id=pid, action="give_up_learning").first()
        assert audit is not None
        assert audit.before_json == {"current_step": "learning_targets"}
        assert audit.after_json["current_step"] == "retest"
    finally:
        db.close()


def test_experiment_give_up_during_retest_routes_to_survey_and_blocks_retest_actions():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    give_up_learning = client.post(f"/api/participants/{pid}/give-up-learning")
    assert give_up_learning.status_code == 200, give_up_learning.text
    assert give_up_learning.json()["next_step"] == "retest"
    questions = client.get(f"/api/experiment/{pid}/retest")
    assert questions.status_code == 200, questions.text
    first_question = questions.json()["questions"][0]

    give_up = client.post(f"/api/participants/{pid}/give-up")
    assert give_up.status_code == 200, give_up.text
    assert give_up.json()["next_step"] == "survey"
    assert give_up.json()["next_url"] == "/survey"
    current = client.get(f"/api/participants/{pid}/current-step")
    assert current.status_code == 200
    assert current.json() == {"step": "survey", "next_url": "/survey"}

    assert client.get(f"/api/experiment/{pid}/retest").status_code == 409
    assert client.post(f"/api/participants/{pid}/score-retest").status_code == 409
    blocked_attempt = client.post(
        "/api/attempts",
        json={
            "participant_id": pid,
            "question_id": first_question["question_id"],
            "phase": "retest",
            "selected_option_ids": _ids_for_labels(first_question, ["A", "B", "C"]),
        },
    )
    assert blocked_attempt.status_code == 409

    db = SessionLocal()
    try:
        participant = db.get(Participant, pid)
        assert participant is not None
        assert participant.current_step == "survey"
        assert participant.completed_at is not None
        assert participant.completion_reason == "give_up"
        completed_at_at_give_up = participant.completed_at
        audit = db.query(AuditEvent).filter_by(entity_type="participant", entity_id=pid, action="give_up_experiment").first()
        assert audit is not None
        assert audit.after_json["current_step"] == "survey"
        assert audit.after_json["completion_reason"] == "give_up"
    finally:
        db.close()

    survey_payload = {
        "ai_experience_level": 3,
        "programming_experience_level": 2,
        "llm_usage_level": 4,
        "self_rated_ai_knowledge": 3,
        "usability_rating": 5,
        "helpfulness_rating": 4,
        "perceived_hint_amount": 3,
        "free_comment": "再テストギブアップ後アンケートの確認",
    }
    survey_key = f"survey-after-retest-give-up:{pid}"
    survey = client.post(
        f"/api/participants/{pid}/survey",
        json=survey_payload,
        headers={"Idempotency-Key": survey_key},
    )
    assert survey.status_code == 200, survey.text
    assert survey.json()["next_step"] == "finish"
    assert survey.json()["next_url"] == "/finish"
    repeated_survey = client.post(
        f"/api/participants/{pid}/survey",
        json=survey_payload,
        headers={"Idempotency-Key": survey_key},
    )
    assert repeated_survey.status_code == 200, repeated_survey.text
    assert repeated_survey.json()["survey_id"] == survey.json()["survey_id"]

    db = SessionLocal()
    try:
        participant = db.get(Participant, pid)
        surveys = db.query(ParticipantSurvey).filter_by(participant_id=pid).all()
        assert participant is not None
        assert participant.current_step == "finish"
        assert participant.completed_at == completed_at_at_give_up
        assert participant.completion_reason == "give_up"
        assert len(surveys) == 1
    finally:
        db.close()

    repeated = client.post(f"/api/participants/{pid}/give-up")
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["next_url"] == "/finish"
    admin_row = next(row for row in client.get("/api/admin/participants").json()["participants"] if row["participant_id"] == pid)
    assert admin_row["completion_reason"] == "give_up"
    assert admin_row["give_up_experiment_count"] == 1
    summary_response = client.post(f"/api/participants/{pid}/evaluation-summary/recalculate")
    assert summary_response.status_code == 200, summary_response.text
    db = SessionLocal()
    try:
        summary = db.query(EvaluationSummary).filter_by(participant_id=pid).order_by(EvaluationSummary.created_at.desc()).first()
        assert summary is not None
        assert summary.completed is False
    finally:
        db.close()
    participant_csv = client.get(f"/api/admin/participants/{pid}/logs.csv")
    assert participant_csv.status_code == 200
    assert "give_up_experiment" in participant_csv.text
    assert "post-experiment survey" in participant_csv.text


def test_experiment_give_up_during_final_test_routes_to_survey_and_blocks_final_test_actions():
    pid = _create_participant_with_pretest(labels=["A", "B", "C"])
    questions = client.get(f"/api/experiment/{pid}/final-test")
    assert questions.status_code == 200, questions.text
    first_question = questions.json()["questions"][0]

    give_up = client.post(f"/api/participants/{pid}/give-up")
    assert give_up.status_code == 200, give_up.text
    assert give_up.json()["next_step"] == "survey"
    assert give_up.json()["next_url"] == "/survey"
    current = client.get(f"/api/participants/{pid}/current-step")
    assert current.status_code == 200
    assert current.json() == {"step": "survey", "next_url": "/survey"}
    assert client.get(f"/api/experiment/{pid}/final-test").status_code == 409
    assert client.post(f"/api/participants/{pid}/score-final-test").status_code == 409
    blocked_attempt = client.post(
        "/api/attempts",
        json={
            "participant_id": pid,
            "question_id": first_question["question_id"],
            "phase": "final_test",
            "selected_option_ids": _ids_for_labels(first_question, ["A", "B", "C"]),
        },
    )
    assert blocked_attempt.status_code == 409

    db = SessionLocal()
    try:
        participant = db.get(Participant, pid)
        assert participant is not None
        assert participant.current_step == "survey"
        assert participant.completed_at is not None
        assert participant.completion_reason == "give_up"
        completed_at_at_give_up = participant.completed_at
        audit = db.query(AuditEvent).filter_by(entity_type="participant", entity_id=pid, action="give_up_experiment").one()
        assert audit.after_json["current_step"] == "survey"
        assert audit.after_json["completion_reason"] == "give_up"
    finally:
        db.close()

    survey_payload = {
        "ai_experience_level": 3,
        "programming_experience_level": 2,
        "llm_usage_level": 4,
        "self_rated_ai_knowledge": 3,
        "usability_rating": 5,
        "helpfulness_rating": 4,
        "perceived_hint_amount": 3,
        "free_comment": "ギブアップ後アンケートの確認",
    }
    survey_key = f"survey-after-give-up:{pid}"
    survey = client.post(
        f"/api/participants/{pid}/survey",
        json=survey_payload,
        headers={"Idempotency-Key": survey_key},
    )
    assert survey.status_code == 200, survey.text
    assert survey.json()["next_step"] == "finish"
    assert survey.json()["next_url"] == "/finish"
    repeated = client.post(
        f"/api/participants/{pid}/survey",
        json=survey_payload,
        headers={"Idempotency-Key": survey_key},
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["survey_id"] == survey.json()["survey_id"]

    db = SessionLocal()
    try:
        participant = db.get(Participant, pid)
        surveys = db.query(ParticipantSurvey).filter_by(participant_id=pid).all()
        assert participant is not None
        assert participant.current_step == "finish"
        assert participant.completed_at == completed_at_at_give_up
        assert participant.completion_reason == "give_up"
        assert len(surveys) == 1
        assert surveys[0].phase == "posttest"
    finally:
        db.close()

    logs = client.get(f"/api/admin/participants/{pid}/logs")
    assert logs.status_code == 200, logs.text
    assert any(event["action"] == "give_up_experiment" for event in logs.json()["audit_events"])
    assert any(event["action"] == "submit_survey" for event in logs.json()["audit_events"])
    assert len(logs.json()["surveys"]) == 1
    exported = client.get(f"/api/admin/participants/{pid}/logs.csv")
    assert exported.status_code == 200, exported.text
    assert "give_up_experiment" in exported.text
    assert "post-experiment survey" in exported.text


def test_experiment_give_up_is_available_after_retest_result_confirmation():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    _submit_phase_questions(pid, "retest", ["D", "E", "F"])
    score = client.post(f"/api/participants/{pid}/score-retest")
    assert score.status_code == 200, score.text
    assert score.json()["next_step"] == "learning_targets"

    confirmation = client.get(f"/api/participants/{pid}/learning-targets")
    assert confirmation.status_code == 200, confirmation.text
    assert confirmation.json()["test_results"]["test_round"] == "retest_1"

    give_up = client.post(f"/api/participants/{pid}/give-up")
    assert give_up.status_code == 200, give_up.text
    assert give_up.json()["next_step"] == "finish"
    assert client.get(f"/api/participants/{pid}/current-step").json()["step"] == "finish"
    participant_logs = client.get(f"/api/admin/participants/{pid}/logs")
    assert participant_logs.status_code == 200, participant_logs.text
    assert any(event["action"] == "give_up_experiment" for event in participant_logs.json()["audit_events"])


def test_retest_mastery_skips_final_test_and_uses_retest_score():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    _submit_phase_questions(pid, "retest", ["A", "B", "C"])

    score = client.post(f"/api/participants/{pid}/score-retest")
    assert score.status_code == 200, score.text
    assert score.json()["next_step"] == "survey"
    assert score.json()["next_url"] == "/survey"
    assert client.get(f"/api/participants/{pid}/current-step").json()["step"] == "survey"

    final_response = client.get(f"/api/experiment/{pid}/final-test")
    assert final_response.status_code == 409
    final_score_response = client.post(f"/api/participants/{pid}/score-final-test")
    assert final_score_response.status_code == 409

    db = SessionLocal()
    try:
        final_question = (
            db.query(Question)
            .join(Term, Question.term_id == Term.id)
            .filter(Question.phase == "final_test", Question.is_active.is_(True), Term.slug == ACTIVE_TERM_SLUGS[0])
            .one()
        )
        correct_option_ids = [
            option.id
            for option in db.query(QuestionOption)
            .filter(QuestionOption.question_id == final_question.id, QuestionOption.option_label.in_(["A", "B", "C"]))
            .order_by(QuestionOption.default_order)
            .all()
        ]
    finally:
        db.close()

    blocked_attempt = client.post(
        "/api/attempts",
        json={
            "participant_id": pid,
            "question_id": final_question.id,
            "phase": "final_test",
            "selected_option_ids": correct_option_ids,
        },
    )
    assert blocked_attempt.status_code == 409

    recalculate = client.post(f"/api/participants/{pid}/evaluation-summary/recalculate")
    assert recalculate.status_code == 200, recalculate.text
    db = SessionLocal()
    try:
        summary = db.query(EvaluationSummary).filter_by(participant_id=pid).order_by(EvaluationSummary.created_at.desc()).first()
        assert summary is not None
        assert summary.l0_correct_rate == pytest.approx(1.0)
        assert summary.score_timeline_json["final_test_skipped_after_retest_mastery"] is True
        assert summary.score_timeline_json["final_score_source"] == "retest_mastery"
        assert summary.condition_check_json["final_test_skipped_after_retest_mastery"] is True
        assert summary.condition_check_json["final_score_source"] == "retest_mastery"
        assert db.query(Attempt).filter_by(participant_id=pid, phase="final_test").count() == 0
    finally:
        db.close()


def test_survey_submission_saves_and_finishes_participant():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    _submit_phase_questions(pid, "retest", ["A", "B", "C"])
    score = client.post(f"/api/participants/{pid}/score-retest")
    assert score.status_code == 200, score.text
    assert score.json()["next_step"] == "survey"

    payload = {
        "ai_experience_level": 3,
        "programming_experience_level": 2,
        "llm_usage_level": 4,
        "self_rated_ai_knowledge": 3,
        "usability_rating": 5,
        "helpfulness_rating": 4,
        "perceived_hint_amount": 3,
        "free_comment": "仮アンケートの確認",
    }
    missing_required_background = {key: value for key, value in payload.items() if key != "ai_experience_level"}
    invalid = client.post(f"/api/participants/{pid}/survey", json=missing_required_background)
    assert invalid.status_code == 422

    response = client.post(f"/api/participants/{pid}/survey", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["next_step"] == "finish"
    assert response.json()["next_url"] == "/finish"
    assert client.get(f"/api/participants/{pid}/current-step").json()["step"] == "finish"

    repeated = client.post(f"/api/participants/{pid}/survey", json=payload)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["survey_id"] == response.json()["survey_id"]

    db = SessionLocal()
    try:
        participant = db.get(Participant, pid)
        surveys = db.query(ParticipantSurvey).filter_by(participant_id=pid).all()
        assert participant is not None
        assert participant.completion_reason == "completed"
        assert len(surveys) == 1
        assert surveys[0].phase == "posttest"
        assert surveys[0].usability_rating == 5
        assert surveys[0].free_comment == "仮アンケートの確認"
    finally:
        db.close()

    logs = client.get(f"/api/admin/participants/{pid}/logs")
    assert logs.status_code == 200, logs.text
    assert logs.json()["surveys"][0]["helpfulness_rating"] == 4
    exported = client.get(f"/api/admin/participants/{pid}/logs_excel.csv")
    assert exported.status_code == 200, exported.text
    assert "post-experiment survey" in exported.text


def test_final_test_has_one_question_per_active_term():
    pid = _create_participant_with_pretest(labels=["A", "B", "C"])
    final_questions = client.get(f"/api/experiment/{pid}/final-test").json()["questions"]
    assert [question["term_slug"] for question in final_questions] == list(ACTIVE_TERM_SLUGS)
    assert all(question["question_type"] == "final_multi_select" for question in final_questions)
    assert all(len(question["options"]) == 10 for question in final_questions)
    assert {question["test_round"] for question in final_questions} == {"retest_1"}
    assert {question["test_round_label"] for question in final_questions} == {"再テスト1"}


def test_attempts_store_test_round_one_and_two_for_repeated_retests():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    db = SessionLocal()
    try:
        assert {attempt.test_round for attempt in db.query(Attempt).filter_by(participant_id=pid, phase="pretest").all()} == {"test"}
    finally:
        db.close()

    first_questions = client.get(f"/api/experiment/{pid}/retest").json()["questions"]
    assert {question["test_round"] for question in first_questions} == {"retest_1"}
    _submit_phase_questions(pid, "retest", ["D", "E", "F"])
    first_score = client.post(f"/api/participants/{pid}/score-retest")
    assert first_score.status_code == 200, first_score.text

    second_questions = client.get(f"/api/experiment/{pid}/retest").json()["questions"]
    assert {question["test_round"] for question in second_questions} == {"retest_2"}
    assert {question["test_round_label"] for question in second_questions} == {"再テスト2"}
    _submit_phase_questions(pid, "retest", ["D", "E", "F"])

    db = SessionLocal()
    try:
        rounds = {attempt.test_round for attempt in db.query(Attempt).filter_by(participant_id=pid, phase="retest").all()}
        assert rounds == {"retest_1", "retest_2"}
    finally:
        db.close()


def test_incorrect_final_test_routes_to_learning_session():
    pid = _create_participant_with_pretest(labels=["A", "B", "C"])
    _submit_phase_questions(pid, "final_test", ["D", "E", "F"])

    score = client.post(f"/api/participants/{pid}/score-final-test")
    assert score.status_code == 200, score.text
    payload = score.json()
    assert payload["next_step"] == "learning_targets"
    assert payload["next_url"] == "/learning/llm_knowledge"
    assert payload["learning_target_slugs"] == list(ACTIVE_TERM_SLUGS)
    db = SessionLocal()
    try:
        assert {attempt.test_round for attempt in db.query(Attempt).filter_by(participant_id=pid, phase="final_test").all()} == {"retest_1"}
    finally:
        db.close()
    assert client.get(f"/api/participants/{pid}/current-step").json()["step"] == "learning_targets"
    assert client.get(f"/api/experiment/{pid}/final-test").status_code == 409
    assert client.post(f"/api/participants/{pid}/score-final-test").status_code == 409


def test_correct_final_test_still_routes_to_survey():
    pid = _create_participant_with_pretest(labels=["A", "B", "C"])
    _submit_phase_questions(pid, "final_test", ["A", "B", "C"])

    score = client.post(f"/api/participants/{pid}/score-final-test")
    assert score.status_code == 200, score.text
    assert score.json()["next_step"] == "survey"
    assert score.json()["next_url"] == "/survey"


def test_learning_session_moves_to_next_target_after_three_incorrect_turns():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "llm_knowledge"}).json()
    for attempt_index in range(3):
        turn_response = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={})
        assert turn_response.status_code == 200, turn_response.text
        turn = turn_response.json()
        assert turn["turn_index"] == attempt_index + 1
        response = client.post(
            f"/api/tutor-turns/{turn['turn_id']}/respond",
            json={"selected_option_ids": _ids_for_labels(turn["practice_question"], ["D", "E", "F"])},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        if attempt_index < 2:
            assert payload["session_completed"] is False
            assert payload["next_url"] is None
        else:
            assert payload["session_completed"] is True
            assert payload["is_sufficient"] is False
            assert payload["session_ended_by_attempt_limit"] is True
            assert payload["remaining_attempts"] == 0
            assert payload["next_url"] == "/learning/multi_agent"

    ended_session_turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={})
    assert ended_session_turn.status_code == 409

    next_session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "multi_agent"})
    assert next_session.status_code == 200, next_session.text
    next_session_id = next_session.json()["tutor_session_id"]
    for attempt_index in range(3):
        next_turn = client.post(f"/api/tutor-sessions/{next_session_id}/turns", json={})
        assert next_turn.status_code == 200, next_turn.text
        next_turn_payload = next_turn.json()
        assert next_turn_payload["term_slug"] == "multi_agent"
        assert next_turn_payload["turn_index"] == attempt_index + 1
        next_response = client.post(
            f"/api/tutor-turns/{next_turn_payload['turn_id']}/respond",
            json={"selected_option_ids": _ids_for_labels(next_turn_payload["practice_question"], ["D", "E", "F"])},
        )
        assert next_response.status_code == 200, next_response.text
        if attempt_index == 2:
            assert next_response.json()["next_url"] == "/learning/memory_process"


def test_learning_session_skips_exhausted_prior_targets_and_retests_after_last_success():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])

    first_session = client.post(
        "/api/tutor-sessions",
        json={"participant_id": pid, "term_slug": "llm_knowledge"},
    ).json()
    for _ in range(3):
        turn = client.post(f"/api/tutor-sessions/{first_session['tutor_session_id']}/turns", json={}).json()
        response = client.post(
            f"/api/tutor-turns/{turn['turn_id']}/respond",
            json={"selected_option_ids": _ids_for_labels(turn["practice_question"], ["D", "E", "F"])},
        )
        assert response.status_code == 200, response.text

    second_session = client.post(
        "/api/tutor-sessions",
        json={"participant_id": pid, "term_slug": "multi_agent"},
    ).json()
    second_turn = client.post(f"/api/tutor-sessions/{second_session['tutor_session_id']}/turns", json={}).json()
    second_response = client.post(
        f"/api/tutor-turns/{second_turn['turn_id']}/respond",
        json={"selected_option_ids": _ids_for_labels(second_turn["practice_question"], ["A", "B", "C"])},
    )
    assert second_response.status_code == 200, second_response.text
    second_payload = second_response.json()
    assert second_payload["is_sufficient"] is True
    assert second_payload["remaining_attempts"] == 0
    assert second_payload["next_url"] == "/learning/memory_process"

    third_session = client.post(
        "/api/tutor-sessions",
        json={"participant_id": pid, "term_slug": "memory_process"},
    ).json()
    third_turn = client.post(f"/api/tutor-sessions/{third_session['tutor_session_id']}/turns", json={}).json()
    third_response = client.post(
        f"/api/tutor-turns/{third_turn['turn_id']}/respond",
        json={"selected_option_ids": _ids_for_labels(third_turn["practice_question"], ["A", "B", "C"])},
    )
    assert third_response.status_code == 200, third_response.text
    third_payload = third_response.json()
    assert third_payload["is_sufficient"] is True
    assert third_payload["remaining_attempts"] == 0
    assert third_payload["next_url"] == "/retest"


def test_learning_question_order_stays_fixed_when_adaptive_stage_changes():
    pid = _create_participant_with_pretest(labels=["J"])
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "llm_knowledge"}).json()

    first = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={})
    assert first.status_code == 200, first.text
    first_payload = first.json()
    assert first_payload["practice_question"]["variant_key"] == "learning_enrichment_v1"
    assert first_payload["turn_index"] == 1

    wrong = client.post(
        f"/api/tutor-turns/{first_payload['turn_id']}/respond",
        json={"selected_option_ids": _ids_for_labels(first_payload["practice_question"], ["A", "D", "G"])},
    )
    assert wrong.status_code == 200, wrong.text
    wrong_payload = wrong.json()
    # A wrong answer is feedback for the current problem, not a new problem.
    assert wrong_payload["turn_index"] == first_payload["turn_index"]

    second = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={})
    assert second.status_code == 200, second.text
    second_payload = second.json()
    assert second_payload["learning_stage"] == "conceptual_change"
    assert second_payload["practice_question"]["variant_key"] == "learning_conceptual_change_v2"
    assert second_payload["turn_index"] == first_payload["turn_index"] + 1


def test_proposed_payload_contains_taxonomy_and_control_payload_does_not():
    proposed_pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    proposed_session = client.post("/api/tutor-sessions", json={"participant_id": proposed_pid, "term_slug": "llm_knowledge"}).json()
    proposed_turn = client.post(f"/api/tutor-sessions/{proposed_session['tutor_session_id']}/turns", json={}).json()
    assert proposed_turn["turn_id"]

    control_pid = _create_participant_with_pretest(group="control", labels=["D", "E", "F"])
    control_session = client.post("/api/tutor-sessions", json={"participant_id": control_pid, "term_slug": "llm_knowledge"}).json()
    control_turn = client.post(f"/api/tutor-sessions/{control_session['tutor_session_id']}/turns", json={}).json()
    assert control_turn["turn_id"]

    db = SessionLocal()
    try:
        tutoring_logs = db.query(AICallLog).filter_by(purpose="generate_tutoring_turn").all()
        proposed_log = next(log for log in reversed(tutoring_logs) if log.request_payload.get("participant_id") == proposed_pid)
        control_log = next(log for log in reversed(tutoring_logs) if log.request_payload.get("participant_id") == control_pid)
        assert proposed_log.request_payload["misconception_taxonomy"] == MISCONCEPTION_TAXONOMY
        assert proposed_log.request_payload["taxonomy_version"] == TAXONOMY_VERSION
        assert proposed_log.request_payload["prompt_contract_version"] == PROMPT_CONTRACT_VERSION
        assert {target["claim_id"] for target in proposed_log.request_payload["pretest_targets"]} == {
            "llm_knowledge:pretest:D",
            "llm_knowledge:pretest:E",
            "llm_knowledge:pretest:F",
        }
        e_target = next(target for target in proposed_log.request_payload["pretest_targets"] if target["option_label"] == "E")
        assert "プロンプトエンジニアリングは入力文脈や指示を工夫する方法" in e_target["corrected_claim"]
        assert "session_misconception_history" in proposed_log.request_payload
        assert "misconception_taxonomy" not in control_log.request_payload
        assert "taxonomy_version" not in control_log.request_payload
        assert "pretest_targets" not in control_log.request_payload
        assert "learner_state" not in control_log.request_payload
        assert "session_misconception_history" not in control_log.request_payload
        assert "learning_stage" not in control_log.request_payload
        assert "expected_answer" not in control_log.request_payload["fixed_practice_question"]
        assert "expected_answer" not in proposed_log.request_payload["fixed_practice_question"]
        assert proposed_log.request_payload["rag_context"] == control_log.request_payload["rag_context"]
        proposed_turn_row = db.get(TutorTurn, proposed_turn["turn_id"])
        assert proposed_turn_row.diagnosis_json["taxonomy_version"] == TAXONOMY_VERSION
        assert proposed_turn_row.diagnosis_json["prompt_contract_version"] == PROMPT_CONTRACT_VERSION
        assert proposed_turn_row.diagnosis_json["teaching_contract"]["target_claim_id"]
        assert proposed_turn_row.diagnosis_json["teaching_contract_validation"]["valid"] is True
        participant_log = client.get(f"/api/admin/participants/{proposed_pid}/logs")
        assert participant_log.status_code == 200, participant_log.text
        logged_turn = participant_log.json()["tutor_sessions"][0]["turns"][0]
        assert logged_turn["taxonomy_version"] == TAXONOMY_VERSION
        assert logged_turn["prompt_contract_version"] == PROMPT_CONTRACT_VERSION
        assert logged_turn["teaching_contract"]["target_claim_id"] == "llm_knowledge:pretest:D"
        assert logged_turn["teaching_contract_validation"]["valid"] is True
    finally:
        db.close()


def test_next_tutoring_material_excludes_previous_check_feedback():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "multi_agent"}).json()
    first_turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    wrong_response = client.post(
        f"/api/tutor-turns/{first_turn['turn_id']}/respond",
        json={"selected_option_ids": _ids_for_labels(first_turn["practice_question"], ["A", "D", "G"])},
    )
    assert wrong_response.status_code == 200, wrong_response.text
    previous_feedback = wrong_response.json()["feedback"]
    assert previous_feedback

    next_turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={})
    assert next_turn.status_code == 200, next_turn.text
    assert previous_feedback not in next_turn.json()["tutor_message"]

    db = SessionLocal()
    try:
        tutoring_log = (
            db.query(AICallLog)
            .filter_by(purpose="generate_tutoring_turn")
            .order_by(AICallLog.created_at.desc())
            .first()
        )
        assert tutoring_log is not None
        assert "previous_feedback_for_learner" not in tutoring_log.request_payload
    finally:
        db.close()


def test_admin_logs_and_csv_show_multiple_selection_labels():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    logs = client.get(f"/api/admin/participants/{pid}/logs").json()
    assert len(logs["attempts"]) == 3
    assert all(row["selected_option_body"] == "D / E / F" for row in logs["attempts"])
    assert all(row["misconception_type"] == "M1" for row in logs["attempts"])

    overview = client.get("/api/admin/logs/overview").json()
    assert any(row.get("selected_option_body") == "D / E / F" for row in overview["recent_answer_history"])
    assert any(row.get("group_condition") == "proposed" for row in overview["recent_ai_call_logs"])

    recalculate = client.post(f"/api/participants/{pid}/evaluation-summary/recalculate")
    assert recalculate.status_code == 200
    participant_summary = client.get(f"/api/admin/participants/{pid}/logs").json()["latest_evaluation_summary"]
    assert participant_summary["condition_check"] is not None

    participant_csv = client.get(f"/api/admin/participants/{pid}/logs.csv")
    assert participant_csv.status_code == 200
    assert "D / E / F" in participant_csv.text
    assert "answer,test_attempt" in participant_csv.text


def test_group_misconception_transition_summary_uses_term_pretest_denominator():
    transition_types = ["resolved", "same_type_recurred", "changed_type", "unknown_persisted", "regressed", "unclassified"]
    control_pids = [
        client.post("/api/participants", json={"assignment_code": "B", "consent_checked": True}).json()["participant_id"]
        for _ in transition_types
    ]
    missing_pid = client.post("/api/participants", json={"assignment_code": "B", "consent_checked": True}).json()["participant_id"]
    proposed_pid = client.post("/api/participants", json={"assignment_code": "A", "consent_checked": True}).json()["participant_id"]

    db = SessionLocal()
    try:
        control_participants = [db.get(experiment_service.Participant, pid) for pid in control_pids + [missing_pid]]
        proposed_participant = db.get(experiment_service.Participant, proposed_pid)
        terms = experiment_service._term_map(db)
        control_summaries = [
            SimpleNamespace(
                participant_id=pid,
                misconception_timeline_json={
                    "terms": [
                        {
                            "term_slug": "llm_knowledge",
                            "change_type": transition_type,
                            "events": [{"phase": "pretest"}],
                        }
                    ]
                },
            )
            for pid, transition_type in zip(control_pids, transition_types)
        ]
        control_result = experiment_service._group_misconception_transition_summary(control_participants, control_summaries, terms)
        control_term = next(row for row in control_result["terms"] if row["term_slug"] == "llm_knowledge")
        assert control_term["eligible_count"] == len(transition_types)
        assert control_term["missing_count"] == 1
        assert control_term["counts"] == {transition_type: 1 for transition_type in transition_types}
        assert all(rate == 1 / len(transition_types) for rate in control_term["rates"].values())

        proposed_result = experiment_service._group_misconception_transition_summary(
            [proposed_participant],
            [SimpleNamespace(participant_id=proposed_pid, misconception_timeline_json={"terms": [{"term_slug": "llm_knowledge", "change_type": "resolved", "events": [{"phase": "pretest"}]}]})],
            terms,
        )
        proposed_term = next(row for row in proposed_result["terms"] if row["term_slug"] == "llm_knowledge")
        assert proposed_term["counts"]["resolved"] == 1
        assert sum(proposed_term["counts"].values()) == 1
    finally:
        db.close()

    api_groups = client.get("/api/admin/evaluation-summary").json()["groups"]
    assert all("misconception_transition_summary" in group for group in api_groups)
    assert all(len(group["misconception_transition_summary"]["terms"]) == 3 for group in api_groups)


def test_admin_summary_auto_calculates_participant_without_manual_recalculate():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])

    db = SessionLocal()
    try:
        assert db.query(EvaluationSummary).filter_by(participant_id=pid).count() == 0
    finally:
        db.close()

    response = client.get("/api/admin/evaluation-summary")
    assert response.status_code == 200, response.text
    proposed_group = next(group for group in response.json()["groups"] if group["group_condition"] == "proposed")
    llm_summary = next(
        term for term in proposed_group["misconception_transition_summary"]["terms"] if term["term_slug"] == "llm_knowledge"
    )
    assert llm_summary["eligible_count"] >= 1
    assert llm_summary["counts"]["unclassified"] >= 1

    db = SessionLocal()
    try:
        summary = db.query(EvaluationSummary).filter_by(participant_id=pid).order_by(EvaluationSummary.created_at.desc()).first()
        assert summary is not None
        assert summary.pretest_score == 0
    finally:
        db.close()

    participant_logs = client.get(f"/api/admin/participants/{pid}/logs")
    assert participant_logs.status_code == 200, participant_logs.text
    assert participant_logs.json()["latest_evaluation_summary"] is not None

    overview = client.get("/api/admin/logs/overview")
    assert overview.status_code == 200, overview.text
    assert any(row["participant_id"] == pid for row in overview.json()["evaluation_summaries"])

    exported = client.get(f"/api/admin/participants/{pid}/logs_excel.csv")
    assert exported.status_code == 200, exported.text
    assert "evaluation_summary" in exported.text


def test_admin_can_delete_participant_and_related_data():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    session_response = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "llm_knowledge"})
    assert session_response.status_code == 200
    assert client.post(f"/api/participants/{pid}/evaluation-summary/recalculate").status_code == 200

    db = SessionLocal()
    try:
        attempts = db.query(Attempt).filter_by(participant_id=pid).order_by(Attempt.created_at).all()
        db.add(ParticipantSurvey(participant_id=pid, phase="posttest"))
        db.add(
            RecurrenceEvent(
                participant_id=pid,
                term_id=attempts[0].term_id,
                previous_attempt_id=attempts[0].id,
                current_attempt_id=attempts[1].id,
                previous_misconception_type="M1",
                current_misconception_type="M1",
                is_same_type=True,
                phase="retest",
            )
        )
        db.commit()
    finally:
        db.close()

    deleted = client.delete(f"/api/admin/participants/{pid}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] is True
    assert client.get(f"/api/admin/participants/{pid}/logs").status_code == 404
    assert pid not in {row["participant_id"] for row in client.get("/api/admin/participants").json()["participants"]}

    db = SessionLocal()
    try:
        assert db.query(Participant).filter_by(id=pid).count() == 0
        assert db.query(ParticipantSurvey).filter_by(participant_id=pid).count() == 0
        assert db.query(TermAssignment).filter_by(participant_id=pid).count() == 0
        assert db.query(QuestionDisplayOrder).filter_by(participant_id=pid).count() == 0
        assert db.query(RecurrenceEvent).filter_by(participant_id=pid).count() == 0
        assert db.query(TutorSession).filter_by(participant_id=pid).count() == 0
        assert db.query(LearnerState).filter_by(participant_id=pid).count() == 0
        assert db.query(EvaluationSummary).filter_by(participant_id=pid).count() == 0
        assert db.query(Attempt).filter_by(participant_id=pid).count() == 0
        assert not any((log.request_payload or {}).get("participant_id") == pid for log in db.query(AICallLog).all())
        audit = db.query(AuditEvent).filter_by(entity_type="participant", entity_id=pid, action="delete_participant").first()
        assert audit is not None
        assert audit.after_json == {"deleted": True}
    finally:
        db.close()

    assert client.delete(f"/api/admin/participants/{pid}").status_code == 404


def test_participant_creation_uses_next_unused_display_code_after_deletion():
    original = client.post("/api/participants", json={"assignment_code": "B", "consent_checked": True}).json()
    successor = client.post("/api/participants", json={"assignment_code": "B", "consent_checked": True}).json()
    assert client.delete(f"/api/admin/participants/{original['participant_id']}").status_code == 200

    recreated = client.post("/api/participants", json={"assignment_code": "B", "consent_checked": True})
    assert recreated.status_code == 200, recreated.text
    assert recreated.json()["display_code"] != original["display_code"]
    assert int(recreated.json()["display_code"][1:]) > int(successor["display_code"][1:])


def test_admin_participant_delete_rolls_back_on_commit_failure(monkeypatch):
    participant = client.post("/api/participants", json={"assignment_code": "B", "consent_checked": True}).json()
    pid = participant["participant_id"]
    db = SessionLocal()
    try:
        def fail_commit():
            raise RuntimeError("commit failed")

        monkeypatch.setattr(db, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="commit failed"):
            experiment_service.delete_participant(db, pid)
    finally:
        db.close()

    assert client.get(f"/api/admin/participants/{pid}/logs").status_code == 200


def test_tutoring_prompt_contract_mentions_three_topic_design_and_latest_taxonomy():
    prompt_source = Path(__file__).resolve().parents[1] / "app" / "ai" / "codex_app_server_backend.py"
    text = prompt_source.read_text(encoding="utf-8")
    assert "learning_stage が enrichment" in text
    assert "learning_stage が conceptual_change" in text
    assert "misconception_taxonomy" in text
    assert "M4なら不足スキーマの構築" in text
    assert "fixed_practice_question" in text
    assert "### 要点" in text
    assert "### 具体例" in text
    assert "### 注意点" in text
    assert "feedback は安全なMarkdownとして返す" in text
    assert "前の確認問題に対する採点結果・解説・振り返りは教材本文へ再掲せず" in text
    assert "previous_feedback_for_learner" not in text
    assert "generate_correct_answer_summary" in text
    assert "explain_selected_distractor" in text
    assert "正答の選択肢本文、正答位置、正答そのものを直接示さない" in text


def test_tutoring_prompt_keeps_previous_context_but_excludes_feedback(monkeypatch):
    backend = CodexAppServerBackend()
    captured_prompt: dict[str, str] = {}

    async def capture_prompt(purpose, prompt, output_schema):
        captured_prompt["text"] = prompt
        return {
            "tutor_message": "## マルチエージェント\n\n### 要点\n- 役割を分担して課題を処理します。\n\n### 具体例\n- 複数の担当が連携します。\n\n### 注意点\n- 単なる複数AIの集合ではありません。",
            "teaching_strategy": "foundational_explanation",
            "scaffolding_level": "L3",
            "requires_learner_response": True,
            "learner_prompt": "説明してください。",
            "practice_question": {"body": "確認問題", "expected_answer": "説明", "question_type": "learning_multi_select"},
            "forbidden_help_given": False,
        }

    monkeypatch.setattr(backend, "_run_structured_turn", capture_prompt)
    result = asyncio.run(
        backend.generate_tutoring_turn(
            {
                "group_condition": "proposed",
                "term": {"slug": "multi_agent", "label": "マルチエージェント", "description": "複数のエージェントが役割を分担する方式。"},
                "learning_stage": "conceptual_change",
                "fixed_practice_question": {"body": "確認問題", "expected_answer": "説明"},
                "learner_state": {"teaching_strategy": "foundational_explanation", "scaffolding_level": "L3"},
                "previous_practice_question": "前回の確認問題の内容",
                "previous_learner_response": "前回の学習者の回答",
                "previous_learning_misconception": {"misconception_type": "M3"},
                "session_misconception_history": [{"misconception_type": "M3"}],
            }
        )
    )

    prompt = captured_prompt["text"]
    assert "previous_practice_question と previous_learner_response" in prompt
    assert "AI生成の tutor_message へ転載しない" in prompt
    assert "backend が教材本文の前に別途表示する" in prompt
    assert "前回の確認問題の内容" in prompt
    assert "前回の学習者の回答" in prompt
    assert "前の確認問題に対する採点結果・解説・振り返りは教材本文へ再掲せず" in prompt
    assert "previous_feedback_for_learner" not in prompt
    assert result["tutor_message"].startswith("## マルチエージェント")


def test_mock_tutoring_and_feedback_use_markdown_contract():
    backend = MockAIBackend()
    payload = {
        "term": {
            "label": "マルチエージェント",
            "description": "複数のエージェントが役割分担して課題を処理する設計です。",
            "keywords": ["役割"],
        },
        "learning_stage": "enrichment",
        "group_condition": "proposed",
        "fixed_practice_question": {"body": "説明してください。"},
    }

    turn = asyncio.run(backend.generate_tutoring_turn(payload))
    for heading in (
        "## マルチエージェント",
        "### 定義",
        "### 構成要素",
        "### 役割",
        "### 判断基準",
        "### 正例",
        "### 非例",
    ):
        assert heading in turn["tutor_message"]
    for heading in ("### 要点", "### 具体例", "### 注意点"):
        assert heading not in turn["tutor_message"]

    correct_feedback = asyncio.run(
        backend.generate_feedback({**payload, "learner_response": "役割を分担します。"})
    )
    incorrect_feedback = asyncio.run(
        backend.generate_feedback({**payload, "learner_response": "わからない"})
    )
    assert "### 要点" in correct_feedback["feedback"]
    assert "### 見直しポイント" in incorrect_feedback["feedback"]

    correct_summary = asyncio.run(backend.generate_correct_answer_summary(payload))
    distractor_feedback = asyncio.run(
        backend.explain_selected_distractor({**payload, "selected_option_bodies": ["誤った説明"]})
    )
    assert "## 今回の要点" in correct_summary["summary"]
    assert "## どこが違うか" in distractor_feedback["feedback"]
    assert "## 見直す観点" in distractor_feedback["feedback"]


def test_latest_taxonomy_and_strategy_cover_m1_to_m4():
    assert {"M1", "M2", "M3", "M4", "unknown"}.issubset(MISCONCEPTION_TAXONOMY)
    assert strategy_for("M1", "misconception", "proposed") == "belief_revision"
    assert strategy_for("M2", "misconception", "proposed") == "deep_structure_focus"
    assert strategy_for("M3", "misconception", "proposed") == "category_reorientation"
    assert strategy_for("M4", "misconception", "proposed") == "context_transfer_training"
    assert strategy_for("M4", "misconception", "control") == "general_explanation"


def test_rag_is_limited_by_topic_and_excludes_langgraph():
    llm_context = retrieve_rag_context(
        "LLM 事前学習 RAG プロンプトエンジニアリング",
        allowed_sections=content_term("llm_knowledge")["rag_sections"],
        topic_slug="llm_knowledge",
    )
    multi_context = retrieve_rag_context(
        "マルチエージェント 役割分担",
        allowed_sections=content_term("multi_agent")["rag_sections"],
        topic_slug="multi_agent",
    )
    memory_context = retrieve_rag_context(
        "記憶プロセス 保存 検索 更新",
        allowed_sections=content_term("memory_process")["rag_sections"],
        topic_slug="memory_process",
    )
    assert llm_context["topic_slug"] == "llm_knowledge"
    assert multi_context["topic_slug"] == "multi_agent"
    assert memory_context["topic_slug"] == "memory_process"
    assert llm_context["chunks"]
    assert multi_context["chunks"]
    assert memory_context["chunks"]
    assert all("langgraph" not in (chunk.get("text") or "").lower() for context in (llm_context, multi_context, memory_context) for chunk in context["chunks"])
    assert all("第3章" in " ".join(chunk.get("section_path") or []) for chunk in llm_context["chunks"])
    assert all("4.1" in " ".join(chunk.get("section_path") or []) for chunk in multi_context["chunks"])
    assert all("第5章" in " ".join(chunk.get("section_path") or []) for chunk in memory_context["chunks"])


def test_model_and_reasoning_settings_are_updated():
    settings = get_settings()
    assert settings.codex_model == "gpt-5.6-luna"
    assert settings.codex_reasoning_effort == "medium"
    backend = CodexAppServerBackend()
    assert backend.settings.codex_model == "gpt-5.6-luna"
    assert backend.settings.codex_reasoning_effort == "medium"


def test_admin_reasoning_effort_status_and_updates():
    reset_reasoning_effort_override()
    try:
        status = client.get("/api/admin/ai/status")
        assert status.status_code == 200, status.text
        assert status.json()["reasoning_effort"] == "medium"
        assert status.json()["allowed_reasoning_efforts"] == ["low", "medium", "high"]
        assert status.json()["can_change_reasoning_effort"] is True

        for effort in ("low", "medium", "high"):
            response = client.post("/api/admin/ai/reasoning-effort", json={"reasoning_effort": effort})
            assert response.status_code == 200, response.text
            assert response.json()["reasoning_effort"] == effort

        invalid = client.post("/api/admin/ai/reasoning-effort", json={"reasoning_effort": "xhigh"})
        assert invalid.status_code == 422, invalid.text
    finally:
        reset_reasoning_effort_override()


def test_admin_reasoning_effort_update_is_allowed_while_participant_is_active():
    reset_reasoning_effort_override()
    participant = client.post("/api/participants", json={"assignment_code": "A", "consent_checked": True}).json()
    try:
        status = client.get("/api/admin/ai/status")
        assert status.status_code == 200, status.text
        assert status.json()["can_change_reasoning_effort"] is True
        assert status.json()["reasoning_effort_change_block_reason"] is None

        response = client.post("/api/admin/ai/reasoning-effort", json={"reasoning_effort": "high"})
        assert response.status_code == 200, response.text
        assert response.json()["reasoning_effort"] == "high"
    finally:
        db = SessionLocal()
        try:
            row = db.get(Participant, participant["participant_id"])
            assert row is not None
            row.current_step = "finish"
            row.completed_at = row.started_at
            row.completion_reason = "give_up"
            db.commit()
        finally:
            db.close()
            reset_reasoning_effort_override()


def test_codex_turn_start_uses_requested_reasoning_effort(monkeypatch):
    backend = CodexAppServerBackend(reasoning_effort="low")

    class FakeRpc:
        def __init__(self):
            self.calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def call(self, method, params=None, notification_handler=None):
            self.calls.append((method, params))
            if method == "account/read":
                return {"account": {"id": "test-account"}}
            if method == "thread/start":
                return {"thread": {"id": "thread-id"}}
            if method == "turn/start":
                notification_handler(
                    {
                        "method": "item/completed",
                        "params": {
                            "turnId": "turn-id",
                            "item": {"type": "agentMessage", "text": '\n{"ok": true}\n'},
                        },
                    }
                )
                return {"turn": {"id": "turn-id"}}
            return {}

        async def recv(self, _notification_handler=None):
            return {"method": "turn/completed", "params": {"turn": {"id": "turn-id", "status": "completed"}}}

    rpc = FakeRpc()
    monkeypatch.setattr(backend, "_client", lambda: rpc)
    result = asyncio.run(backend._run_structured_turn("test", "prompt", {"type": "object"}))

    assert result == {"ok": True}
    assert result.raw_text == '\n{"ok": true}\n'
    turn_start = next(params for method, params in rpc.calls if method == "turn/start")
    assert turn_start["model"] == "gpt-5.6-luna"
    assert turn_start["effort"] == "low"


def test_ai_call_logs_effective_reasoning_effort(monkeypatch):
    reset_reasoning_effort_override()
    set_reasoning_effort("high")

    class FakeBackend:
        provider = "test_backend"

        async def test_reasoning_effort_logging(self, payload):
            assert payload["marker"] == "runtime-effort-test"
            return {"ok": True}

    monkeypatch.setattr(experiment_service, "get_ai_backend", lambda reasoning_effort=None: FakeBackend())
    db = SessionLocal()
    try:
        result = asyncio.run(
            experiment_service._ai_call(
                db,
                "test_reasoning_effort_logging",
                {"marker": "runtime-effort-test"},
            )
        )
        log = (
            db.query(AICallLog)
            .filter_by(purpose="test_reasoning_effort_logging")
            .order_by(AICallLog.created_at.desc())
            .first()
        )
        assert result == {"ok": True}
        assert log is not None
        assert log.request_payload["reasoning_effort"] == "high"
    finally:
        db.close()
        reset_reasoning_effort_override()


def test_codex_ai_call_logs_raw_and_reconciled_model_responses(monkeypatch):
    participant = client.post(
        "/api/participants",
        json={"assignment_code": "A", "consent_checked": True},
    ).json()
    pid = participant["participant_id"]
    payload = {
        "participant_id": pid,
        "group_condition": "proposed",
        "active_misconception_type": "M1",
        "learning_stage": "conceptual_change",
        "term": {
            "slug": "memory_process",
            "label": "記憶プロセス",
            "description": "情報を保存し、検索して現在の処理へ渡し、必要に応じて更新する仕組みです。",
        },
        "fixed_practice_question": {"body": "適切な説明を選びなさい。"},
    }
    raw_model_response = asyncio.run(MockAIBackend().generate_tutoring_turn(payload))
    raw_model_response["teaching_contract"]["corrected_claim"] = "生出力にだけ含まれた未検証の訂正文です。"
    raw_text = json.dumps(raw_model_response, ensure_ascii=False)
    backend = CodexAppServerBackend()

    class FakeRpc:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def call(self, method, params=None, notification_handler=None):
            if method == "account/read":
                return {"account": {"id": "test-account"}}
            if method == "thread/start":
                return {"thread": {"id": "thread-id"}}
            if method == "turn/start":
                notification_handler(
                    {
                        "method": "item/completed",
                        "params": {
                            "turnId": "turn-id",
                            "item": {"type": "agentMessage", "text": raw_text},
                        },
                    }
                )
                return {"turn": {"id": "turn-id"}}
            return {}

        async def recv(self, _notification_handler=None):
            return {"method": "turn/completed", "params": {"turn": {"id": "turn-id", "status": "completed"}}}

    monkeypatch.setattr(backend, "_client", lambda: FakeRpc())
    monkeypatch.setattr(experiment_service, "get_ai_backend", lambda reasoning_effort=None: backend)

    db = SessionLocal()
    try:
        normalized_response = asyncio.run(
            experiment_service._ai_call(db, "generate_tutoring_turn", payload)
        )
        log = (
            db.query(AICallLog)
            .filter_by(purpose="generate_tutoring_turn")
            .order_by(AICallLog.created_at.desc())
            .first()
        )
        assert log is not None
        assert log.raw_text == raw_text
        assert "未検証の訂正文" in log.raw_text
        assert log.response_payload == normalized_response
        assert log.response_payload["teaching_contract"]["corrected_claim"] == log.response_payload[
            "mandatory_elements"
        ]["correct_belief"]
        assert "未検証の訂正文" not in log.response_payload["teaching_contract"]["corrected_claim"]

        participant_logs = client.get(f"/api/admin/participants/{pid}/logs")
        assert participant_logs.status_code == 200, participant_logs.text
        logged_ai_call = next(
            row
            for row in participant_logs.json()["ai_call_logs"]
            if row["id"] == log.id
        )
        assert logged_ai_call["raw_text"] == raw_text
        assert logged_ai_call["response_payload"] == normalized_response

        participant_csv = client.get(f"/api/admin/participants/{pid}/logs.csv")
        assert participant_csv.status_code == 200, participant_csv.text
        assert "未検証の訂正文" in participant_csv.text
    finally:
        db.close()


def test_codex_json_parse_failure_keeps_raw_response_in_ai_log(monkeypatch):
    raw_text = "モデル出力はJSONではありません。"

    class FakeBackend:
        provider = "codex_app_server"

        async def invalid_output(self, _payload):
            raise CodexAppServerError(
                "schema_validation_failed",
                "AI応答を解析できませんでした。",
                raw_text,
                raw_text=raw_text,
            )

    monkeypatch.setattr(experiment_service, "get_ai_backend", lambda reasoning_effort=None: FakeBackend())
    db = SessionLocal()
    try:
        with pytest.raises(HTTPException):
            asyncio.run(experiment_service._ai_call(db, "invalid_output", {"marker": "raw-error-test"}))
        log = (
            db.query(AICallLog)
            .filter_by(purpose="invalid_output")
            .order_by(AICallLog.created_at.desc())
            .first()
        )
        assert log is not None
        assert log.status == "failed"
        assert log.raw_text == raw_text
    finally:
        db.close()
