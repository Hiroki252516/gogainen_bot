from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models import AICallLog
from app.rag import retrieve_rag_context


client = TestClient(app)


CORRECT_MARKERS = [
    "AttentionレイヤーとFFNレイヤー",
    "入力中のトークン同士の関係の強さ",
    "各トークンが他のトークンとの関係の強さ",
    "事前学習、インストラクションチューニング、事後学習",
    "大規模で多様なテキストデータなどから",
    "人間の価値観や安全性・有用性により合うよう",
]


def unknown_option(question: dict) -> dict:
    return next(option for option in question["options"] if "わからない" in option["body"])


def correct_option(question: dict) -> dict:
    return next(
        option
        for option in question["options"]
        if any(marker in option["body"] for marker in CORRECT_MARKERS)
    )


def test_full_mock_experiment_flow():
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    participant = client.post("/api/participants", json={"group_condition": "proposed", "consent_checked": True}).json()
    pid = participant["participant_id"]
    assert participant["group_condition"] == "proposed"
    assert participant["current_step"] == "pretest"

    pretest = client.get(f"/api/experiment/{pid}/pretest").json()["questions"]
    assert len(pretest) == 5
    assert pretest[0]["requires_reason"] is False
    assert pretest[0]["requires_confidence"] is False
    for question in pretest:
        wrong = unknown_option(question)
        response = client.post(
            "/api/attempts",
            json={
                "participant_id": pid,
                "question_id": question["question_id"],
                "phase": "pretest",
                "selected_option_id": wrong["option_id"],
                "reason_text": None,
                "confidence": None,
            },
        )
        assert response.status_code == 200

    diagnosis = client.post(f"/api/participants/{pid}/diagnose-pretest")
    assert diagnosis.status_code == 200
    assert diagnosis.json()["learning_target_count"] == 5

    targets = client.get(f"/api/participants/{pid}/learning-targets").json()["targets"]
    assert len(targets) == 5
    assert "term_slug" in targets[0]
    assert "M1" not in targets[0]["summary_for_learner"]

    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": targets[0]["term_slug"]}).json()
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert turn["requires_learner_response"] is True
    db = SessionLocal()
    try:
        log = (
            db.query(AICallLog)
            .filter(AICallLog.purpose == "generate_tutoring_turn")
            .order_by(AICallLog.created_at.desc())
            .first()
        )
        assert log is not None
        assert log.request_payload["rag_context"]["source"] == "rag_ready_教材"
        assert len(log.request_payload["rag_context"]["chunks"]) == 3
    finally:
        db.close()

    feedback = client.post(
        f"/api/tutor-turns/{turn['turn_id']}/respond",
        json={"learner_response": "判断基準を自分の言葉で説明します"},
    )
    assert feedback.status_code == 200

    for phase, get_path, score_path in [
        ("retest", f"/api/experiment/{pid}/retest", f"/api/participants/{pid}/score-retest"),
        ("l0_check", f"/api/experiment/{pid}/l0-check", f"/api/participants/{pid}/score-l0-check"),
        ("transfer", f"/api/experiment/{pid}/transfer-test", f"/api/participants/{pid}/score-transfer-test"),
    ]:
        questions = client.get(get_path).json()["questions"]
        assert questions
        for question in questions:
            payload = {
                "participant_id": pid,
                "question_id": question["question_id"],
                "phase": phase,
                "reason_text": "関係 重み 重要度 などの判断基準で説明します",
            }
            if question["options"]:
                payload["selected_option_id"] = question["options"][0]["option_id"]
            else:
                payload["free_text_answer"] = payload["reason_text"]
            assert client.post("/api/attempts", json=payload).status_code == 200
        assert client.post(score_path).status_code == 200

    client.post(
        f"/api/participants/{pid}/survey",
        json={"phase": "post_survey", "usability_rating": 4, "helpfulness_rating": 4, "perceived_hint_amount": 3},
    )
    summary = client.post(f"/api/participants/{pid}/evaluation-summary/recalculate")
    assert summary.status_code == 200

    export = client.get("/api/admin/export/evaluation_summary.csv")
    assert export.status_code == 200
    assert "same_misconception_recurrence_rate" in export.text


def test_control_group_uses_general_strategy():
    participant = client.post("/api/participants", json={"group_condition": "control", "consent_checked": True}).json()
    pid = participant["participant_id"]
    question = client.get(f"/api/experiment/{pid}/pretest").json()["questions"][0]
    option = unknown_option(question)
    client.post(
        "/api/attempts",
        json={
            "participant_id": pid,
            "question_id": question["question_id"],
            "phase": "pretest",
            "selected_option_id": option["option_id"],
            "reason_text": None,
            "confidence": None,
        },
    )
    client.post(f"/api/participants/{pid}/diagnose-pretest")
    target = client.get(f"/api/participants/{pid}/learning-targets").json()["targets"][0]
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": target["term_slug"]}).json()
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert "一般" in turn["tutor_message"] or "定義" in turn["tutor_message"]


def test_all_correct_pretest_has_no_learning_targets():
    participant = client.post("/api/participants", json={"group_condition": "proposed", "consent_checked": True}).json()
    pid = participant["participant_id"]
    pretest = client.get(f"/api/experiment/{pid}/pretest").json()["questions"]
    assert len(pretest) == 5

    for question in pretest:
        option = correct_option(question)
        assert client.post(
            "/api/attempts",
            json={
                "participant_id": pid,
                "question_id": question["question_id"],
                "phase": "pretest",
                "selected_option_id": option["option_id"],
                "reason_text": None,
                "confidence": None,
            },
        ).status_code == 200

    diagnosis = client.post(f"/api/participants/{pid}/diagnose-pretest")
    assert diagnosis.status_code == 200
    assert diagnosis.json()["learning_target_count"] == 0
    assert client.get(f"/api/participants/{pid}/learning-targets").json()["targets"] == []


def test_rag_retriever_returns_local_chunks():
    for query in ["Transformer", "事前学習", "事後学習"]:
        context = retrieve_rag_context(query)
        assert context["source"] == "rag_ready_教材"
        assert len(context["chunks"]) == 3
        assert all(chunk["text"] for chunk in context["chunks"])
