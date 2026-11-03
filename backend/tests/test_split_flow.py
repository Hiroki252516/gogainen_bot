import pytest
from admin_client import AuthenticatedTestClient
from app.main import app
from app.db.session import SessionLocal
from app.models import QuestionOption, TutorTurn, Participant, Attempt
from app.seed.seed_questions import seed_database
from app.services.hypothesis_metrics import participant_metrics
from split_api_support import acknowledge_all_question_reviews, create_trial, answer_test, select_roles


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
@pytest.mark.parametrize("first_role", ["unknown", "M1"])
@pytest.mark.parametrize("target_slug", ["llm_knowledge", "multi_agent", "memory_process"])
def test_split_flow(group, layout, first_role, target_slug):
    client = AuthenticatedTestClient(app)
    ok(client.put("/api/admin/question-set", json={"mode": "standard"}))
    ok(client.put("/api/admin/option-order", json={"mode": layout}))
    pid = ok(client.post("/api/registrations", json={"assignment_code": group, "consent_checked": True, "student_number": "SPLIT-SYNTHETIC"}))["participant_id"]
    questions = ok(client.get(f"/api/experiment/{pid}/pretest"))["questions"]
    assert len(questions) == 6
    assert all(len(q["options"]) == 6 and q["selection_mode"] == "single" for q in questions)
    assert all(set(o) == {"option_id", "label", "body", "exclusive"} for q in questions for o in q["options"])
    assert client.post(f"/api/participants/{pid}/diagnose-pretest", json={}).status_code == 400
    target_index = 0
    for i, q in enumerate(questions):
        with SessionLocal() as db:
            role = None
            if q["term_slug"] == target_slug:
                role = first_role if target_index == 0 else "M3"
                target_index += 1
            option = db.query(QuestionOption).filter_by(question_id=q["question_id"], misconception_type=role).first()
            option_id = option.id
        ok(client.post("/api/attempts", json={"participant_id": pid, "question_id": q["question_id"], "selected_option_ids": [option_id]}))
    acknowledge_all_question_reviews(client, pid, "pretest")
    ok(client.post(f"/api/participants/{pid}/diagnose-pretest", json={}))
    session = ok(client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": target_slug}))
    turn = ok(client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}))
    practice = turn["practice_question"]
    assert len(practice["questions"]) == 2
    assert "source_spec" not in practice
    assert all("is_correct" not in o for q in practice["questions"] for o in q["options"])
    with SessionLocal() as db:
        saved = db.get(TutorTurn, turn["turn_id"])
        assert saved.practice_question_json["source_spec"]
        actual = saved.diagnosis_json["instruction_audit"]["actual_ai_input"]
        assert len(actual["learning_scope"]["topics"]) == 2
        if first_role == "unknown":
            assert not actual["learning_scope"]["selected_errors"]
            assert not actual["interaction_history"]
        else:
            assert len(actual["learning_scope"]["selected_errors"]) == 2
        if group == "B":
            assert "pretest_targets" not in actual
    response = ok(client.post(f"/api/tutor-turns/{turn['turn_id']}/respond", json={"selected_option_ids": [q["options"][0]["option_id"] for q in practice["questions"]]}))
    assert response["session_completed"]
    assert response["next_url"] == "/retest"
    retest = ok(client.get(f"/api/experiment/{pid}/retest"))["questions"]
    assert len(retest) == 6
    for q in retest:
        ok(client.post("/api/attempts", json={"participant_id": pid, "question_id": q["question_id"], "selected_option_ids": [q["options"][-1]["option_id"]]}))
    acknowledge_all_question_reviews(client, pid, "retest")
    ok(client.post(f"/api/participants/{pid}/score-retest", json={}))
    reviewed = ok(client.get(f"/api/participants/{pid}/learning-targets"))
    assert len(reviewed["test_results"]["results"]) == 6
    with SessionLocal() as db:
        metrics = participant_metrics(db, db.get(Participant, pid))
        assert metrics["questions_per_test"] == 6
        assert metrics["h1"]["pretest_score"] == 4 / 6


@pytest.mark.parametrize("pretest_perfect", [False, True])
def test_split_maximum_rounds_and_mastery(pretest_perfect):
    client = AuthenticatedTestClient(app)
    ok(client.put("/api/admin/question-set", json={"mode": "standard"}))
    pid = ok(client.post("/api/registrations", json={"assignment_code": "B", "consent_checked": True, "student_number": "SPLIT-LIMIT"}))["participant_id"]
    def answer(phase, correct):
        questions = ok(client.get(f"/api/experiment/{pid}/{phase}"))["questions"]
        for q in questions:
            with SessionLocal() as db:
                option = db.query(QuestionOption).filter_by(question_id=q["question_id"], is_correct=True).one() if correct else None
                selected = option.id if option else q["options"][-1]["option_id"]
            ok(client.post("/api/attempts", json={"participant_id": pid, "question_id": q["question_id"], "phase": phase.replace("-", "_"), "selected_option_ids": [selected]}))
        acknowledge_all_question_reviews(client, pid, phase.replace("-", "_"))
    answer("pretest", pretest_perfect)
    ok(client.post(f"/api/participants/{pid}/diagnose-pretest", json={}))
    if not pretest_perfect:
        ok(client.post(f"/api/participants/{pid}/give-up-learning", json={}))
    phase = "final-test" if pretest_perfect else "retest"
    answer(phase, False)
    result = ok(client.post(f"/api/participants/{pid}/score-{phase}", json={}))
    assert result["next_step"] == "learning_targets"
    ok(client.post(f"/api/participants/{pid}/give-up-learning", json={}))
    answer("retest", True)
    result = ok(client.post(f"/api/participants/{pid}/score-retest", json={}))
    assert result["next_step"] == "survey"
    assert result["post_pretest_tests_completed"] == 2
    assert client.get(f"/api/experiment/{pid}/retest").status_code == 409


def test_easy_bank_is_preserved_and_easy_participant_records_are_read_only():
    from app.seed.content_loader import assessment_question_spec

    client = AuthenticatedTestClient(app)
    assert client.put("/api/admin/question-set", json={"mode": "easy"}).status_code == 422
    ok(client.put("/api/admin/option-order", json={"mode": "debug_fixed"}))
    for slug in ("llm_knowledge", "multi_agent", "memory_process"):
        historical = assessment_question_spec(slug, "pretest", mode="easy")
        assert len(historical["options"]) == 10
        assert historical["variant_key"] == "pretest_v1"

    pid = ok(client.post("/api/registrations", json={"assignment_code": "B", "consent_checked": True, "student_number": "EASY-UNCHANGED"}))["participant_id"]
    questions = ok(client.get(f"/api/experiment/{pid}/pretest"))["questions"]
    assert len(questions) == 6
    q = questions[0]
    ok(client.post("/api/attempts", json={"participant_id": pid, "question_id": q["question_id"], "selected_option_ids": [q["options"][-1]["option_id"]]}))
    with SessionLocal() as db:
        participant = db.get(Participant, pid)
        participant.question_set_mode = "easy"
        db.commit()
        before = [(a.id, a.question_body_snapshot, a.option_order_snapshot) for a in db.query(Attempt).filter_by(participant_id=pid).all()]
        seed_database(db)
        assert before == [(a.id, a.question_body_snapshot, a.option_order_snapshot) for a in db.query(Attempt).filter_by(participant_id=pid).all()]
    assert client.get(f"/api/participants/{pid}/current-step").json()["can_resume"] is False
    assert client.get(f"/api/experiment/{pid}/pretest").status_code == 409
    assert client.post(f"/api/participants/{pid}/diagnose-pretest", json={}).status_code == 409
    log = ok(client.get(f"/api/admin/participants/{pid}/logs"))
    assert log["participant"]["question_set_mode"] == "easy"
    assert log["participant"]["can_resume"] is False


@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
@pytest.mark.parametrize("slug", ["llm_knowledge", "multi_agent", "memory_process"])
@pytest.mark.parametrize("role", ["M3", "unknown"])
def test_initial_perfect_confirms_only_failed_final_item(group, layout, slug, role):
    with create_trial(group, layout) as (client, pid):
        answer_test(client, pid, "pretest", slug, (None, None))
        questions, scored = answer_test(client, pid, "final_test", slug, (None, role))
        assert scored["post_pretest_tests_completed"] == 1
        target = [q for q in questions if q["term_slug"] == slug][1]
        session = ok(client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": slug}))
        turn = ok(client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}))
        practice = turn["practice_question"]
        assert practice["learning_variant_index"] == 1
        assert practice["questions"] == [{"question_id": target["question_id"], "body": target["body"], "options": target["options"]}]
        assert "source_spec" not in practice
        with SessionLocal() as db:
            saved = db.get(TutorTurn, turn["turn_id"])
            actual = saved.diagnosis_json["instruction_audit"]["actual_ai_input"]
            assert len(actual["learning_scope"]["topics"]) == 1
            assert len(actual["learning_scope"]["selected_errors"]) == (0 if role == "unknown" else 1)
            assert len(saved.practice_question_json["source_spec"]["options"]) == 6
        url = f"/api/tutor-turns/{turn['turn_id']}/respond"
        assert client.post(url, json={"selected_option_ids": [o["option_id"] for o in target["options"][:2]]}).status_code == 400
        payload = {"selected_option_ids": select_roles(target, [None])}
        headers = {"Idempotency-Key": "one-failed-final-item"}
        result = ok(client.post(url, json=payload, headers=headers))
        assert result["is_sufficient"] and result["session_completed"]
        assert ok(client.post(url, json=payload, headers=headers)) == result
        with SessionLocal() as db:
            grades = db.get(TutorTurn, turn["turn_id"]).grading_json["question_results"]
            assert len(grades) == 1 and grades[0]["question_id"] == target["question_id"]
        _, last = answer_test(client, pid, "retest", slug, (None, None))
        assert last["post_pretest_tests_completed"] == 2 and last["next_step"] == "survey"
