import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.ai.backend import strategy_for
from app.ai.codex_app_server_backend import CodexAppServerBackend, CodexAppServerError
from app.ai.mock_backend import MockAIBackend
from app.ai.misconception_taxonomy import MISCONCEPTION_TAXONOMY
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    AICallLog,
    AuditEvent,
    Attempt,
    EvaluationSummary,
    LearnerState,
    Participant,
    ParticipantSurvey,
    QuestionDisplayOrder,
    RecurrenceEvent,
    TermAssignment,
    TutorSession,
    TutorTurn,
)
from app.rag.retriever import retrieve_rag_context
from app.seed.content_loader import ACTIVE_TERM_SLUGS, content_term, load_content
import app.services.experiment as experiment_service


client = TestClient(app)
QUESTION_SHOWN_AT = "2026-06-22T06:00:00"
ANSWERED_AT = "2026-06-22T06:00:05"


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
    questions = client.get(f"/api/experiment/{pid}/{phase}").json()["questions"]
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


def _create_participant_with_pretest(group: str = "proposed", labels: list[str] | None = None) -> str:
    participant = client.post("/api/participants", json={"group_condition": group, "consent_checked": True}).json()
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
    participant = client.post("/api/participants", json={"group_condition": "proposed", "consent_checked": True}).json()
    questions = client.get(f"/api/experiment/{participant['participant_id']}/pretest").json()["questions"]

    assert [question["term_slug"] for question in questions] == list(ACTIVE_TERM_SLUGS)
    for question in questions:
        assert question["selection_mode"] == "multiple"
        assert question["min_selections"] == 3
        assert question["max_selections"] == 3
        assert [option["label"] for option in question["options"]] == list("ABCDEFGHIJ")
        assert len(question["options"]) == 10
        assert question["requires_reason"] is False


def test_attempt_requires_three_from_a_to_i_or_unknown_j_only():
    participant = client.post("/api/participants", json={"group_condition": "proposed", "consent_checked": True}).json()
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


def test_learning_answer_does_not_commit_turn_when_explanation_fails(monkeypatch):
    class FailingBackend:
        provider = "codex_app_server"

        async def explain_selected_distractor(self, payload):
            raise CodexAppServerError("turn_failed", "解説生成に失敗しました。")

    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "llm_knowledge"}).json()
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    monkeypatch.setattr(experiment_service, "get_ai_backend", lambda: FailingBackend())
    response = client.post(
        f"/api/tutor-turns/{turn['turn_id']}/respond",
        json={"selected_option_ids": _ids_for_labels(turn["practice_question"], ["A", "D", "G"])},
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
    finally:
        db.close()


def test_control_group_logs_same_stage_but_uses_general_explanation():
    pid = _create_participant_with_pretest(group="control", labels=["G", "H", "I"])
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "llm_knowledge"}).json()
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()

    assert turn["learning_stage"] == "conceptual_change"
    assert turn["teaching_strategy"] == "general_explanation"
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
    assert len(set(observed[:4])) == 4
    assert observed[4] == observed[3]


def test_final_test_has_one_question_per_active_term():
    pid = _create_participant_with_pretest(labels=["A", "B", "C"])
    final_questions = client.get(f"/api/experiment/{pid}/final-test").json()["questions"]
    assert [question["term_slug"] for question in final_questions] == list(ACTIVE_TERM_SLUGS)
    assert all(question["question_type"] == "final_multi_select" for question in final_questions)
    assert all(len(question["options"]) == 10 for question in final_questions)


def test_learning_confirmation_uses_five_variants_then_reuses_variant_five():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "multi_agent"}).json()
    observed: list[str] = []
    for _ in range(6):
        turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
        observed.append(turn["practice_question"]["variant_key"])
        response = client.post(
            f"/api/tutor-turns/{turn['turn_id']}/respond",
            json={"selected_option_ids": _ids_for_labels(turn["practice_question"], ["D", "E", "F"])},
        )
        assert response.status_code == 200, response.text
    assert observed == [
        "learning_conceptual_change_v1",
        "learning_conceptual_change_v2",
        "learning_conceptual_change_v3",
        "learning_conceptual_change_v4",
        "learning_conceptual_change_v5",
        "learning_conceptual_change_v5",
    ]


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
        assert "session_misconception_history" in proposed_log.request_payload
        assert "misconception_taxonomy" not in control_log.request_payload
        assert "learner_state" not in control_log.request_payload
        assert "session_misconception_history" not in control_log.request_payload
        assert proposed_log.request_payload["rag_context"] == control_log.request_payload["rag_context"]
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
        client.post("/api/participants", json={"group_condition": "control", "consent_checked": True}).json()["participant_id"]
        for _ in transition_types
    ]
    missing_pid = client.post("/api/participants", json={"group_condition": "control", "consent_checked": True}).json()["participant_id"]
    proposed_pid = client.post("/api/participants", json={"group_condition": "proposed", "consent_checked": True}).json()["participant_id"]

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


def test_admin_participant_delete_rolls_back_on_commit_failure(monkeypatch):
    participant = client.post("/api/participants", json={"group_condition": "control", "consent_checked": True}).json()
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
    assert "generate_correct_answer_summary" in text
    assert "explain_selected_distractor" in text
    assert "正答の選択肢本文、正答位置、正答そのものを直接示さない" in text


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
    for heading in ("## マルチエージェント", "### 要点", "### 具体例", "### 注意点"):
        assert heading in turn["tutor_message"]

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
