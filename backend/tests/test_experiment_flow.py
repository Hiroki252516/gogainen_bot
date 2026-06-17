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


def create_participant(group: str = "proposed") -> tuple[str, list[dict]]:
    participant = client.post("/api/participants", json={"group_condition": group, "consent_checked": True}).json()
    pid = participant["participant_id"]
    pretest = client.get(f"/api/experiment/{pid}/pretest").json()["questions"]
    assert len(pretest) == 5
    assert {question["requires_reason"] for question in pretest} == {False}
    assert {question["requires_confidence"] for question in pretest} == {False}
    return pid, pretest


def submit_pretest(pid: str, questions: list[dict], misconception_type: str | None = "unknown") -> None:
    for question in questions:
        option = option_with_internal_label(question, misconception_type)
        response = client.post(
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
        assert response.status_code == 200


def pass_all_prerequisites(session: dict) -> dict:
    current = session
    for item in current["prerequisites"]:
        result = client.post(
            f"/api/learning-sessions/{current['learning_session_id']}/prerequisites/{item['prerequisite_id']}/attempts",
            json={"learner_answer": f"{item['term_label']} の役割と関係を説明します。pass"},
        ).json()
        current = result["session"]
    return current


def test_proposed_3phase_flow_and_final_retest():
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    pid, pretest = create_participant("proposed")
    submit_pretest(pid, pretest, "unknown")

    diagnosis = client.post(f"/api/participants/{pid}/diagnose-pretest")
    assert diagnosis.status_code == 200
    assert diagnosis.json()["learning_target_count"] == 5

    targets = client.get(f"/api/participants/{pid}/learning-targets").json()["targets"]
    assert len(targets) == 5
    assert targets[0]["learning_mode"] == "proposed_3phase"
    assert "M1" not in targets[0]["summary_for_learner"]

    session = client.post("/api/learning-sessions", json={"participant_id": pid, "term_slug": targets[0]["term_slug"]}).json()
    assert session["group_condition"] == "proposed"
    assert session["status"] == "prerequisite"
    assert len(session["prerequisites"]) == 3

    db = SessionLocal()
    try:
        log = db.query(AICallLog).filter(AICallLog.purpose == "generate_prerequisite_plan").order_by(AICallLog.created_at.desc()).first()
        assert log is not None
        assert log.request_payload["rag_context"]["source"] == "rag_ready_教材"
        assert log.request_payload["pretest_diagnosis"]["misconception_type"] == "unknown"
    finally:
        db.close()

    prereq = session["prerequisites"][0]
    fail_one = client.post(
        f"/api/learning-sessions/{session['learning_session_id']}/prerequisites/{prereq['prerequisite_id']}/attempts",
        json={"learner_answer": "短い"},
    ).json()
    assert fail_one["is_passed"] is False
    assert fail_one["session"]["status"] == "prerequisite"
    fail_two = client.post(
        f"/api/learning-sessions/{session['learning_session_id']}/prerequisites/{prereq['prerequisite_id']}/attempts",
        json={"learner_answer": "まだ短い"},
    ).json()
    assert fail_two["is_passed"] is False
    assert fail_two["session"]["status"] == "blocked"
    remaining_targets = client.get(f"/api/participants/{pid}/learning-targets").json()["targets"]
    assert len(remaining_targets) == 4

    second = client.post("/api/learning-sessions", json={"participant_id": pid, "term_slug": targets[1]["term_slug"]}).json()
    second = pass_all_prerequisites(second)
    assert second["status"] == "concept_phase1"

    failed_phase1 = client.post(
        f"/api/learning-sessions/{second['learning_session_id']}/concept-phase1-attempts",
        json={"learner_answer": "まだうまく説明できません。"},
    ).json()
    assert failed_phase1["is_passed"] is False
    assert failed_phase1["review_prerequisite_ids"]
    assert failed_phase1["session"]["status"] == "prerequisite"

    review_item = next(item for item in failed_phase1["session"]["prerequisites"] if item["status"] == "review")
    reviewed = client.post(
        f"/api/learning-sessions/{second['learning_session_id']}/prerequisites/{review_item['prerequisite_id']}/attempts",
        json={"learner_answer": f"{review_item['term_label']} の役割と関係を説明します。pass"},
    ).json()
    assert reviewed["is_passed"] is True
    assert reviewed["session"]["status"] == "concept_phase1"

    labels = [item["term_label"] for item in reviewed["session"]["prerequisites"][:2]]
    phase1 = client.post(
        f"/api/learning-sessions/{second['learning_session_id']}/concept-phase1-attempts",
        json={"learner_answer": f"{labels[0]} と {labels[1]} の関係を使って対象概念を説明します。"},
    ).json()
    assert phase1["is_passed"] is True
    assert phase1["session"]["status"] == "concept_phase2"

    phase2_fail = client.post(
        f"/api/learning-sessions/{second['learning_session_id']}/concept-phase2-attempts",
        json={"learner_answer": "短い"},
    ).json()
    assert phase2_fail["is_passed"] is False
    assert phase2_fail["return_to_phase1"] is True
    assert phase2_fail["session"]["status"] == "concept_phase1"

    phase1_retry = client.post(
        f"/api/learning-sessions/{second['learning_session_id']}/concept-phase1-attempts",
        json={"learner_answer": f"{labels[0]} と {labels[1]} の関係を使って対象概念を説明します。pass"},
    ).json()
    assert phase1_retry["session"]["status"] == "concept_phase2"

    phase2_pass = client.post(
        f"/api/learning-sessions/{second['learning_session_id']}/concept-phase2-attempts",
        json={"learner_answer": f"phase2pass {labels[0]} と {labels[1]} を使って教材なしで自力説明します。"},
    ).json()
    assert phase2_pass["is_passed"] is True
    assert phase2_pass["session"]["status"] == "completed"

    retest = client.get(f"/api/experiment/{pid}/retest").json()["questions"]
    assert len(retest) == 5
    assert {question["requires_reason"] for question in retest} == {False}
    assert {question["requires_confidence"] for question in retest} == {False}
    db = SessionLocal()
    try:
        db_questions = db.query(Question).filter(Question.id.in_([question["question_id"] for question in retest])).all()
        assert {question.variant_key for question in db_questions} == {"retest_v1"}
        assert not db.query(Question).filter(Question.phase.in_(("l0_check", "transfer")), Question.is_active.is_(True)).first()
    finally:
        db.close()

    for question in retest:
        option = unknown_option(question)
        assert client.post(
            "/api/attempts",
            json={"participant_id": pid, "question_id": question["question_id"], "phase": "retest", "selected_option_id": option["option_id"]},
        ).status_code == 200
    scored = client.post(f"/api/participants/{pid}/score-retest")
    assert scored.status_code == 200
    assert scored.json()["next_step"] == "post_survey"
    assert client.get(f"/api/experiment/{pid}/l0-check").json()["questions"] == []
    assert client.get(f"/api/experiment/{pid}/transfer-test").json()["questions"] == []

    summary = client.post(f"/api/participants/{pid}/evaluation-summary/recalculate")
    assert summary.status_code == 200
    export = client.get("/api/admin/export/evaluation_summary.csv")
    assert export.status_code == 200
    assert "concept_phase2_success_rate" in export.text
    concept_export = client.get("/api/admin/export/concept_understanding_attempts.csv")
    assert "concept_phase" in concept_export.text
    assert "return_to_phase1" in concept_export.text


def test_proposed_phase2_third_fail_sets_failed_phase2():
    pid, pretest = create_participant("proposed")
    submit_pretest(pid, pretest[:1], "unknown")
    assert client.post(f"/api/participants/{pid}/diagnose-pretest").status_code == 200
    target = client.get(f"/api/participants/{pid}/learning-targets").json()["targets"][0]
    session = client.post("/api/learning-sessions", json={"participant_id": pid, "term_slug": target["term_slug"]}).json()
    session = pass_all_prerequisites(session)
    labels = [item["term_label"] for item in session["prerequisites"][:2]]

    for i in range(3):
        phase1 = client.post(
            f"/api/learning-sessions/{session['learning_session_id']}/concept-phase1-attempts",
            json={"learner_answer": f"{labels[0]} と {labels[1]} の関係を使って対象概念を説明します。pass {i}"},
        ).json()
        assert phase1["session"]["status"] == "concept_phase2"
        phase2 = client.post(
            f"/api/learning-sessions/{session['learning_session_id']}/concept-phase2-attempts",
            json={"learner_answer": "短い"},
        ).json()
        session = phase2["session"]

    assert phase2["is_passed"] is False
    assert session["status"] == "failed_phase2"


def test_control_group_3phase_payload_is_not_personalized():
    pid, pretest = create_participant("control")
    submit_pretest(pid, pretest[:1], "M1")
    assert client.post(f"/api/participants/{pid}/diagnose-pretest").status_code == 200
    target = client.get(f"/api/participants/{pid}/learning-targets").json()["targets"][0]
    assert target["learning_mode"] == "control_3phase"

    session = client.post("/api/learning-sessions", json={"participant_id": pid, "term_slug": target["term_slug"]}).json()
    assert session["status"] == "prerequisite"
    assert len(session["prerequisites"]) == 3
    db = SessionLocal()
    try:
        log = db.query(AICallLog).filter(AICallLog.purpose == "generate_control_prerequisite_plan").order_by(AICallLog.created_at.desc()).first()
        assert log is not None
        assert log.request_payload["rag_context"]["source"] == "rag_ready_教材"
        assert "pretest_diagnosis" not in log.request_payload
        assert "selected_option_body" not in log.request_payload
        assert "learner_state" not in log.request_payload
        assert "learning_history" not in log.request_payload
    finally:
        db.close()

    current = session
    first = current["prerequisites"][0]
    first_result = client.post(
        f"/api/learning-sessions/{current['learning_session_id']}/prerequisites/{first['prerequisite_id']}/attempts",
        json={"learner_answer": "短い"},
    ).json()
    assert first_result["is_passed"] is False
    assert first_result["session"]["status"] == "prerequisite"
    current = first_result["session"]
    for item in current["prerequisites"][1:]:
        current = client.post(
            f"/api/learning-sessions/{current['learning_session_id']}/prerequisites/{item['prerequisite_id']}/attempts",
            json={"learner_answer": f"{item['term_label']} の役割を説明します。pass"},
        ).json()["session"]
    assert current["status"] == "concept_phase1"

    phase1 = client.post(
        f"/api/learning-sessions/{current['learning_session_id']}/concept-phase1-attempts",
        json={"learner_answer": "短い"},
    ).json()
    assert phase1["is_passed"] is False
    assert phase1["session"]["status"] == "concept_phase2"
    db = SessionLocal()
    try:
        log = db.query(AICallLog).filter(AICallLog.purpose == "grade_concept_phase1_answer").order_by(AICallLog.created_at.desc()).first()
        assert log is not None
        assert log.request_payload["group_condition"] == "control"
        assert "pretest_diagnosis" not in log.request_payload
        assert "selected_option_body" not in log.request_payload
        assert "learning_history" not in log.request_payload
    finally:
        db.close()

    phase2 = client.post(
        f"/api/learning-sessions/{current['learning_session_id']}/concept-phase2-attempts",
        json={"learner_answer": "短い"},
    ).json()
    assert phase2["is_passed"] is False
    assert phase2["session"]["status"] == "completed"


def test_all_correct_pretest_has_no_learning_targets():
    pid, pretest = create_participant("proposed")
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
    pid, pretest = create_participant("proposed")
    attention_pretest = next(question for question in pretest if question["term_slug"] == "attention")
    pretest_m1 = option_with_internal_label(attention_pretest, "M1")
    assert client.post(
        "/api/attempts",
        json={"participant_id": pid, "question_id": attention_pretest["question_id"], "phase": "pretest", "selected_option_id": pretest_m1["option_id"]},
    ).status_code == 200

    assert client.post(f"/api/participants/{pid}/diagnose-pretest").status_code == 200
    retest = client.get(f"/api/experiment/{pid}/retest").json()["questions"]
    assert len(retest) == 1
    attention_retest = retest[0]
    assert attention_retest["term_slug"] == "attention"
    retest_m1 = option_with_internal_label(attention_retest, "M1")
    assert client.post(
        "/api/attempts",
        json={"participant_id": pid, "question_id": attention_retest["question_id"], "phase": "retest", "selected_option_id": retest_m1["option_id"]},
    ).status_code == 200
    assert client.post(f"/api/participants/{pid}/score-retest").status_code == 200

    db = SessionLocal()
    try:
        attempt = db.query(Attempt).filter(Attempt.participant_id == pid, Attempt.phase == "retest").one()
        assert attempt.misconception_type == "M1"
        assert attempt.recurrence_flag is True
    finally:
        db.close()
