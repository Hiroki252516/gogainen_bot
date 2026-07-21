from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models import Attempt, EvaluationSummary, TutorTurn


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


def _create_participant_with_pretest(group: str = "proposed", labels: list[str] | None = None) -> str:
    participant = client.post("/api/participants", json={"group_condition": group, "consent_checked": True}).json()
    pid = participant["participant_id"]
    question = client.get(f"/api/experiment/{pid}/pretest").json()["questions"][0]
    selected = _ids_for_labels(question, labels or ["D", "E", "F"])
    response = client.post(
        "/api/attempts",
        json={
            "participant_id": pid,
            "question_id": question["question_id"],
            "phase": "pretest",
            "selected_option_ids": selected,
            "response_time_sec": 1.25,
            "question_shown_at": QUESTION_SHOWN_AT,
            "answered_at": ANSWERED_AT,
        },
    )
    assert response.status_code == 200, response.text
    diagnosis = client.post(f"/api/participants/{pid}/diagnose-pretest")
    assert diagnosis.status_code == 200, diagnosis.text
    return pid


def test_pretest_returns_only_transformer_multi_select_question():
    participant = client.post("/api/participants", json={"group_condition": "proposed", "consent_checked": True}).json()
    questions = client.get(f"/api/experiment/{participant['participant_id']}/pretest").json()["questions"]

    assert [question["term_slug"] for question in questions] == ["transformer"]
    question = questions[0]
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

    one_non_unknown = client.post(
        "/api/attempts",
        json={"participant_id": pid, "question_id": question["question_id"], "phase": "pretest", "selected_option_ids": _ids_for_labels(question, ["A"])},
    )
    assert one_non_unknown.status_code == 400

    four_normal = client.post(
        "/api/attempts",
        json={"participant_id": pid, "question_id": question["question_id"], "phase": "pretest", "selected_option_ids": _ids_for_labels(question, ["A", "B", "C", "D"])},
    )
    assert four_normal.status_code == 400

    mixed_unknown = client.post(
        "/api/attempts",
        json={"participant_id": pid, "question_id": question["question_id"], "phase": "pretest", "selected_option_ids": _ids_for_labels(question, ["A", "D", "J"])},
    )
    assert mixed_unknown.status_code == 400

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
            attempt = db.query(Attempt).filter_by(participant_id=pid, phase="pretest").one()
            assert attempt.is_correct is is_correct
            assert attempt.misconception_type == misconception_type
            assert attempt.diagnosed_status == status
            assert attempt.selected_option_ids
            assert attempt.question_shown_at.isoformat() == QUESTION_SHOWN_AT
            assert attempt.answered_at.isoformat() == ANSWERED_AT
            assert len(attempt.option_order_snapshot) == 10
        finally:
            db.close()


def test_learning_routes_m1_to_conceptual_change_and_unknown_to_enrichment():
    m1_pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    m1_target = client.get(f"/api/participants/{m1_pid}/learning-targets").json()["targets"][0]
    m1_session = client.post("/api/tutor-sessions", json={"participant_id": m1_pid, "term_slug": m1_target["term_slug"]}).json()
    m1_turn = client.post(f"/api/tutor-sessions/{m1_session['tutor_session_id']}/turns", json={}).json()
    assert m1_turn["learning_stage"] == "conceptual_change"
    assert m1_turn["learning_stage_label"] == "概念変化"
    assert m1_turn["practice_question"]["selection_mode"] == "multiple"

    unknown_pid = _create_participant_with_pretest(labels=["J"])
    unknown_target = client.get(f"/api/participants/{unknown_pid}/learning-targets").json()["targets"][0]
    unknown_session = client.post("/api/tutor-sessions", json={"participant_id": unknown_pid, "term_slug": unknown_target["term_slug"]}).json()
    unknown_turn = client.post(f"/api/tutor-sessions/{unknown_session['tutor_session_id']}/turns", json={}).json()
    assert unknown_turn["learning_stage"] == "enrichment"
    assert unknown_turn["learning_stage_label"] == "豊富化"


def test_learning_answer_correct_completes_and_incorrect_routes_by_type():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "transformer"}).json()
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
    assert saved_turn.response_time_sec == 2.5
    assert saved_turn.grading_json["selected_option_ids"] == ["A", "B", "C"]


def test_control_group_logs_same_stage_but_uses_general_explanation():
    pid = _create_participant_with_pretest(group="control", labels=["G", "H", "I"])
    target = client.get(f"/api/participants/{pid}/learning-targets").json()["targets"][0]
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": target["term_slug"]}).json()
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()

    assert turn["learning_stage"] == "conceptual_change"
    assert turn["teaching_strategy"] == "general_explanation"
    assert turn["practice_question"]["selection_mode"] == "multiple"


def test_retest_and_final_test_use_same_transformer_question_set():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    retest = client.get(f"/api/experiment/{pid}/retest").json()["questions"]
    assert [question["term_slug"] for question in retest] == ["transformer"]
    assert retest[0]["selection_mode"] == "multiple"

    response = client.post(
        "/api/attempts",
        json={"participant_id": pid, "question_id": retest[0]["question_id"], "phase": "retest", "selected_option_ids": _ids_for_labels(retest[0], ["A", "B", "C"])},
    )
    assert response.status_code == 200
    score = client.post(f"/api/participants/{pid}/score-retest").json()
    assert score["next_url"] == "/final-test"

    final_questions = client.get(f"/api/experiment/{pid}/final-test").json()["questions"]
    assert len(final_questions) == 1
    assert retest[0]["body"] == final_questions[0]["body"]
    assert [option["body"] for option in retest[0]["options"]] == [option["body"] for option in final_questions[0]["options"]]


def test_final_test_scoring_and_evaluation_summary_focus_on_m1_m3_unknown():
    pid = _create_participant_with_pretest(labels=["A", "B", "C"])
    final_question = client.get(f"/api/experiment/{pid}/final-test").json()["questions"][0]
    assert client.post(
        "/api/attempts",
        json={"participant_id": pid, "question_id": final_question["question_id"], "phase": "final_test", "selected_option_ids": _ids_for_labels(final_question, ["A", "B", "C"])},
    ).status_code == 200
    assert client.post(f"/api/participants/{pid}/score-final-test").json()["next_url"] == "/survey"
    assert client.post(f"/api/participants/{pid}/evaluation-summary/recalculate").status_code == 200

    db = SessionLocal()
    try:
        latest = db.query(EvaluationSummary).filter_by(participant_id=pid).order_by(EvaluationSummary.created_at.desc()).first()
        assert latest is not None
        assert latest.score_timeline_json["rounds"][-1]["round"] == "final_test"
        assert latest.m2_recurrence_rate is None
        assert latest.m4_failure_rate is None
    finally:
        db.close()


def test_admin_logs_and_csv_show_multiple_selection_labels():
    pid = _create_participant_with_pretest(labels=["D", "E", "F"])
    logs = client.get(f"/api/admin/participants/{pid}/logs").json()
    assert len(logs["attempts"]) == 1
    assert logs["attempts"][0]["selected_option_body"] == "D / E / F"
    assert logs["attempts"][0]["misconception_type"] == "M1"

    overview = client.get("/api/admin/logs/overview").json()
    assert any(row.get("selected_option_body") == "D / E / F" for row in overview["recent_answer_history"])

    participant_csv = client.get(f"/api/admin/participants/{pid}/logs.csv")
    assert participant_csv.status_code == 200
    assert "D / E / F" in participant_csv.text
    assert "answer,test_attempt" in participant_csv.text


def test_tutoring_prompt_contract_mentions_new_group_design():
    prompt_source = Path(__file__).resolve().parents[1] / "app" / "ai" / "codex_app_server_backend.py"
    text = prompt_source.read_text(encoding="utf-8")
    assert "learning_stage が enrichment" in text
    assert "learning_stage が conceptual_change" in text
    assert "M2/M4は今回のMVPでは使わない" in text
    assert "fixed_practice_question" in text


def test_m4_does_not_select_context_transfer_strategy():
    from app.ai.backend import strategy_for

    assert strategy_for("M4", "misconception", "proposed") != "context_transfer_training"
    assert strategy_for("M4", "misconception", "control") == "general_explanation"


def test_rag_retrieves_transformer_material_chunks():
    from app.rag.retriever import retrieve_rag_context

    transformer_context = retrieve_rag_context("Transformer Attention FFN トークン間の関係性")
    assert transformer_context["status"] == "ok"
    assert any("Transformer" in chunk["section"] or "Transformer" in chunk["text"] for chunk in transformer_context["chunks"])
