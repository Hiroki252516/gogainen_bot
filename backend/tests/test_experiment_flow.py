from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models import AICallLog, Attempt, Question, QuestionOption
from app.rag import retrieve_rag_context


client = TestClient(app)


def option_with_internal_label(question: dict, misconception_type: str | None) -> dict:
    db = SessionLocal()
    try:
        option_ids = [option["option_id"] for option in question["options"]]
        options = db.query(QuestionOption).filter(QuestionOption.id.in_(option_ids)).all()
        option_by_id = {option.id: option for option in options}
        for public_option in question["options"]:
            option = option_by_id[public_option["option_id"]]
            if option.misconception_type == misconception_type:
                return public_option
    finally:
        db.close()
    raise AssertionError(f"option with misconception_type={misconception_type!r} not found")


def unknown_option(question: dict) -> dict:
    return option_with_internal_label(question, "unknown")


def correct_option(question: dict) -> dict:
    return option_with_internal_label(question, None)


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
        if phase == "retest":
            assert len(questions) == 5
            assert {question["requires_reason"] for question in questions} == {False}
            assert {question["requires_confidence"] for question in questions} == {False}
            db = SessionLocal()
            try:
                db_questions = db.query(Question).filter(Question.id.in_([question["question_id"] for question in questions])).all()
                assert {question.variant_key for question in db_questions} == {"retest_v1"}
                assert all(question.is_active for question in db_questions)
                assert not db.query(Question).filter(
                    Question.phase == "retest",
                    Question.variant_key == "retest_temporary_v1",
                    Question.is_active.is_(True),
                ).first()
                for db_question in db_questions:
                    options = db.query(QuestionOption).filter(QuestionOption.question_id == db_question.id).all()
                    assert sum(1 for option in options if option.is_correct) == 1
                    assert {option.misconception_type for option in options if not option.is_correct} == {"M1", "M2", "M3", "unknown"}
            finally:
                db.close()
        for question in questions:
            payload = {
                "participant_id": pid,
                "question_id": question["question_id"],
                "phase": phase,
                "reason_text": None if phase == "retest" else "関係 重み 重要度 などの判断基準で説明します",
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


def test_retest_same_misconception_sets_recurrence_flag():
    participant = client.post("/api/participants", json={"group_condition": "proposed", "consent_checked": True}).json()
    pid = participant["participant_id"]
    pretest = client.get(f"/api/experiment/{pid}/pretest").json()["questions"]
    attention_pretest = next(question for question in pretest if question["term_slug"] == "attention")
    pretest_m1 = option_with_internal_label(attention_pretest, "M1")
    assert client.post(
        "/api/attempts",
        json={
            "participant_id": pid,
            "question_id": attention_pretest["question_id"],
            "phase": "pretest",
            "selected_option_id": pretest_m1["option_id"],
            "reason_text": None,
            "confidence": None,
        },
    ).status_code == 200

    assert client.post(f"/api/participants/{pid}/diagnose-pretest").status_code == 200
    retest = client.get(f"/api/experiment/{pid}/retest").json()["questions"]
    assert len(retest) == 1
    attention_retest = retest[0]
    assert attention_retest["term_slug"] == "attention"
    assert attention_retest["requires_reason"] is False
    assert attention_retest["requires_confidence"] is False
    retest_m1 = option_with_internal_label(attention_retest, "M1")
    assert client.post(
        "/api/attempts",
        json={
            "participant_id": pid,
            "question_id": attention_retest["question_id"],
            "phase": "retest",
            "selected_option_id": retest_m1["option_id"],
            "reason_text": None,
            "confidence": None,
        },
    ).status_code == 200
    assert client.post(f"/api/participants/{pid}/score-retest").status_code == 200

    db = SessionLocal()
    try:
        attempt = db.query(Attempt).filter(Attempt.participant_id == pid, Attempt.phase == "retest").one()
        assert attempt.misconception_type == "M1"
        assert attempt.recurrence_flag is True
    finally:
        db.close()
