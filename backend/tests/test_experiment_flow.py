from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models import (
    AICallLog,
    ContentVersion,
    LearningChoiceAttempt,
    LearningQuestion,
    LearningQuestionDisplayOrder,
    LearningQuestionOption,
    LearningQuestionSlot,
    Participant,
    Question,
    QuestionDisplayOrder,
    QuestionOption,
)
from app.rag import retrieve_rag_context
from app.services.fixed_learning import _answer_leak


client = TestClient(app)


def option_for_test(question: dict, misconception_type: str | None) -> dict:
    db = SessionLocal()
    try:
        option_ids = [option["option_id"] for option in question["options"]]
        rows = db.query(QuestionOption).filter(QuestionOption.id.in_(option_ids)).all()
        by_id = {row.id: row for row in rows}
        return next(
            option
            for option in question["options"]
            if by_id[option["option_id"]].misconception_type == misconception_type
        )
    finally:
        db.close()


def learning_option(session: dict, misconception_type: str | None) -> dict:
    db = SessionLocal()
    try:
        question_id = session["question"]["question_id"]
        rows = db.query(LearningQuestionOption).filter_by(learning_question_id=question_id).all()
        by_id = {row.id: row for row in rows}
        return next(
            option
            for option in session["question"]["options"]
            if by_id[option["option_id"]].misconception_type == misconception_type
        )
    finally:
        db.close()


def create_participant(group: str, pretest_choice: str | None = "unknown") -> tuple[str, list[dict]]:
    participant = client.post(
        "/api/participants",
        json={"group_condition": group, "consent_checked": True},
    ).json()
    pid = participant["participant_id"]
    questions = client.get(f"/api/experiment/{pid}/initial-test").json()["questions"]
    for question in questions:
        option = option_for_test(question, pretest_choice)
        response = client.post(
            "/api/attempts",
            json={
                "participant_id": pid,
                "question_id": question["question_id"],
                "phase": "initial_test",
                "selected_option_id": option["option_id"],
            },
        )
        assert response.status_code == 200
    diagnosis = client.post(f"/api/participants/{pid}/diagnose-initial-test")
    assert diagnosis.status_code == 200
    return pid, questions


def start_session(pid: str, term_slug: str | None = None) -> dict:
    targets = client.get(f"/api/participants/{pid}/learning-targets").json()["targets"]
    slug = term_slug or targets[0]["term_slug"]
    response = client.post(
        "/api/learning-sessions",
        json={"participant_id": pid, "term_slug": slug},
    )
    assert response.status_code == 200, response.text
    return response.json()


def answer(session: dict, misconception_type: str | None, key: str | None = None) -> dict:
    option = learning_option(session, misconception_type)
    endpoint = {
        "concept_phase1": "concept-phase1-attempts",
        "concept_phase2": "concept-phase2-attempts",
    }.get(session["stage"], "prerequisite-attempts")
    response = client.post(
        f"/api/learning-sessions/{session['learning_session_id']}/{endpoint}",
        headers={"Idempotency-Key": key or str(uuid4())},
        json={
            "question_id": session["question"]["question_id"],
            "selected_option_id": option["option_id"],
            "response_time_sec": 2.5,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def pass_prerequisites(session: dict) -> dict:
    current = session
    while current["stage"] in {"prerequisite", "prerequisite_review"}:
        current = answer(current, None)["session"]
    return current


def pass_phase1(session: dict) -> dict:
    current = session
    while current["stage"] == "concept_phase1":
        current = answer(current, None)["session"]
    return current


def test_content_import_has_fixed_release_and_255_questions():
    db = SessionLocal()
    try:
        release = db.query(ContentVersion).filter_by(is_active=True).one()
        assert release.version_key == "experiment_content_v1"
        assert release.validation_status == "provisional"
        assert db.query(LearningQuestion).count() == 255
        assert db.query(LearningQuestionSlot).count() == 85
        for question in db.query(LearningQuestion).all():
            options = db.query(LearningQuestionOption).filter_by(learning_question_id=question.id).all()
            assert len(options) == 5
            assert sum(option.is_correct for option in options) == 1
            assert {option.misconception_type for option in options} == {None, "M1", "M2", "M3", "unknown"}
    finally:
        db.close()


def test_initial_retest_and_final_are_all_five_mcq_with_saved_order():
    pid, initial = create_participant("proposed", "unknown")
    assert len(initial) == 5
    assert {question["requires_reason"] for question in initial} == {False}
    db = SessionLocal()
    try:
        participant = db.get(Participant, pid)
        assert participant.content_version_id is not None
        assert db.query(QuestionDisplayOrder).filter_by(participant_id=pid).count() == 5
        assert {question.variant_key for question in db.query(Question).filter_by(phase="initial_test", is_active=True)} == {"initial_test_v1"}
    finally:
        db.close()
    retest = client.get(f"/api/experiment/{pid}/retest").json()["questions"]
    assert len(retest) == 5
    final = client.get(f"/api/experiment/{pid}/final-test").json()["questions"]
    assert len(final) == 5
    db = SessionLocal()
    try:
        assert {question.variant_key for question in db.query(Question).filter_by(phase="retest", is_active=True)} == {"retest_v1"}
        assert {question.variant_key for question in db.query(Question).filter_by(phase="final_test", is_active=True)} == {"final_test_v1"}
    finally:
        db.close()


def test_proposed_flow_uses_fixed_prerequisites_and_adaptive_returns():
    pid, _ = create_participant("proposed", "M1")
    session = start_session(pid)
    assert session["stage"] == "prerequisite"
    assert len(session["prerequisites"]) == 5
    db = SessionLocal()
    try:
        log = db.query(AICallLog).filter_by(purpose="generate_prerequisite_material").order_by(AICallLog.created_at.desc()).first()
        assert log.request_payload["diagnosis_context"]["initial_test_diagnosis"]["misconception_type"] == "M1"
        assert log.request_payload["rag_context"]["source"] == "rag_ready_教材"
    finally:
        db.close()

    session = pass_prerequisites(session)
    assert session["stage"] == "concept_phase1"
    db = SessionLocal()
    try:
        prereq_attempts = (
            db.query(LearningChoiceAttempt)
            .filter_by(learning_session_id=session["learning_session_id"], stage="prerequisite")
            .count()
        )
        assert prereq_attempts == 5
    finally:
        db.close()
    wrong = answer(session, "M1")
    assert wrong["is_correct"] is False
    assert wrong["correct_answer"] is None
    assert wrong["session"]["stage"] == "prerequisite_review"
    reviewed = answer(wrong["session"], None)
    assert reviewed["session"]["stage"] == "concept_phase1"
    assert reviewed["session"]["progress"]["attempt_index"] == 2
    completed = pass_phase1(reviewed["session"])
    assert completed["status"] == "completed"


def test_control_uses_same_questions_without_adaptive_history():
    proposed_pid, _ = create_participant("proposed", "M1")
    control_pid, _ = create_participant("control", "M1")
    proposed = start_session(proposed_pid, "transformer")
    control = start_session(control_pid, "transformer")
    assert proposed["question"]["body"] == control["question"]["body"]
    assert {item["body"] for item in proposed["question"]["options"]} == {
        item["body"] for item in control["question"]["options"]
    }
    db = SessionLocal()
    try:
        log = (
            db.query(AICallLog)
            .filter_by(purpose="generate_prerequisite_material")
            .order_by(AICallLog.created_at.desc())
            .first()
        )
        assert log.request_payload["group_condition"] == "control"
        assert "diagnosis_context" not in log.request_payload
        assert "learning_history" not in log.request_payload
    finally:
        db.close()
    control = pass_prerequisites(control)
    wrong = answer(control, "M1")
    assert wrong["session"]["stage"] == "concept_phase1"
    assert wrong["session"]["progress"]["attempt_index"] == 2
    completed = pass_phase1(wrong["session"])
    assert completed["status"] == "completed"


def test_third_wrong_forces_resolution_without_blocking():
    pid, _ = create_participant("proposed", "unknown")
    session = start_session(pid)
    first = answer(session, "M1")
    second = answer(first["session"], "M2")
    third = answer(second["session"], "M3")
    assert third["forced_answer_shown"] is True
    assert third["result_status"] == "forced_resolved"
    assert third["correct_answer"]["body"]
    assert third["session"]["status"] == "prerequisite"
    assert third["session"]["progress"]["prerequisite_index"] == 2
    assert third["session"]["progress"]["required_question_index"] == 1
    assert third["session"]["progress"]["required_question_total"] == 1
    db = SessionLocal()
    try:
        attempts = db.query(LearningChoiceAttempt).filter_by(learning_session_id=session["learning_session_id"]).all()
        assert attempts[-1].result_status == "forced_resolved"
    finally:
        db.close()


def test_display_order_is_stable_and_internal_metadata_is_hidden():
    pid, _ = create_participant("proposed", "unknown")
    session = start_session(pid)
    repeated = client.get(f"/api/learning-sessions/{session['learning_session_id']}").json()
    assert [item["option_id"] for item in session["question"]["options"]] == [
        item["option_id"] for item in repeated["question"]["options"]
    ]
    assert "misconception_type" not in session["question"]["options"][0]
    db = SessionLocal()
    try:
        assert db.query(LearningQuestionDisplayOrder).filter_by(participant_id=pid).count() == 1
    finally:
        db.close()


def test_all_correct_initial_test_skips_learning_but_retest_still_has_five():
    pid, _ = create_participant("proposed", None)
    targets = client.get(f"/api/participants/{pid}/learning-targets").json()["targets"]
    assert targets == []
    assert len(client.get(f"/api/experiment/{pid}/retest").json()["questions"]) == 5


def test_retest_scoring_metrics_and_exports():
    pid, _ = create_participant("proposed", "M1")
    retest = client.get(f"/api/experiment/{pid}/retest").json()["questions"]
    for question in retest:
        option = option_for_test(question, "M1")
        assert client.post(
            "/api/attempts",
            json={
                "participant_id": pid,
                "question_id": question["question_id"],
                "phase": "retest",
                "selected_option_id": option["option_id"],
            },
        ).status_code == 200
    scored = client.post(f"/api/participants/{pid}/score-retest")
    assert scored.status_code == 200
    assert scored.json()["next_step"] == "learning_targets"
    assert scored.json()["relearning_target_count"] == 5
    assert client.post(f"/api/participants/{pid}/evaluation-summary/recalculate").status_code == 200
    summary = client.get("/api/admin/export/evaluation_summary.csv")
    assert summary.status_code == 200
    assert "first_retest_score_all_terms" in summary.text
    assert "initial_to_first_retest_gain" in summary.text
    choices = client.get("/api/admin/export/learning_choice_attempts.csv")
    assert choices.status_code == 200


def test_rag_and_answer_leak_detection():
    for query in ("Transformer", "事前学習", "事後学習"):
        context = retrieve_rag_context(query)
        assert context["source"] == "rag_ready_教材"
        assert len(context["chunks"]) == 3
    pid, _ = create_participant("proposed", "unknown")
    session_payload = start_session(pid)
    db = SessionLocal()
    try:
        from app.models import LearningSession

        session = db.get(LearningSession, session_payload["learning_session_id"])
        question = db.get(LearningQuestion, session_payload["question"]["question_id"])
        correct = db.query(LearningQuestionOption).filter_by(learning_question_id=question.id, is_correct=True).one()
        assert _answer_leak(db, session, correct.body) is True
    finally:
        db.close()
