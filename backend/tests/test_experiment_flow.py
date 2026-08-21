from pathlib import Path

from fastapi.testclient import TestClient

from app.ai.backend import strategy_for
from app.ai.codex_app_server_backend import CodexAppServerBackend
from app.ai.misconception_taxonomy import MISCONCEPTION_TAXONOMY
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models import AICallLog, Attempt, TutorTurn
from app.rag.retriever import retrieve_rag_context
from app.seed.content_loader import ACTIVE_TERM_SLUGS, content_term, load_content


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

    participant_csv = client.get(f"/api/admin/participants/{pid}/logs.csv")
    assert participant_csv.status_code == 200
    assert "D / E / F" in participant_csv.text
    assert "answer,test_attempt" in participant_csv.text


def test_tutoring_prompt_contract_mentions_three_topic_design_and_latest_taxonomy():
    prompt_source = Path(__file__).resolve().parents[1] / "app" / "ai" / "codex_app_server_backend.py"
    text = prompt_source.read_text(encoding="utf-8")
    assert "learning_stage が enrichment" in text
    assert "learning_stage が conceptual_change" in text
    assert "misconception_taxonomy" in text
    assert "M4なら不足スキーマの構築" in text
    assert "fixed_practice_question" in text


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
