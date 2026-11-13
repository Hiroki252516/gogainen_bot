import pytest
from admin_client import AuthenticatedTestClient
from app.main import app
from app.db.session import SessionLocal
from app.models import QuestionOption, TutorTurn, Participant, Attempt
from app.seed.seed_questions import seed_database
from app.services.hypothesis_metrics import participant_metrics
from split_api_support import acknowledge_all_question_reviews, complete_presurvey, create_trial, answer_test, new_research_code, select_roles


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(autouse=True)
def restore_option_order():
    client = AuthenticatedTestClient(app)
    ok(client.put("/api/admin/option-order", json={"mode": "debug_fixed"}))
    try:
        yield
    finally:
        current_mode = ok(client.get("/api/admin/option-order"))["mode"]
        if current_mode != "debug_fixed":
            ok(client.put("/api/admin/option-order", json={"mode": "debug_fixed"}))


@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
@pytest.mark.parametrize("first_role", ["unknown", "M1"])
@pytest.mark.parametrize("target_slug", ["llm_knowledge", "multi_agent", "memory_process"])
def test_split_flow(group, layout, first_role, target_slug):
    client = AuthenticatedTestClient(app)
    ok(client.put("/api/admin/option-order", json={"mode": layout}))
    pid = ok(client.post("/api/registrations", json={"assignment_code": group, "consent_checked": True, "research_code": new_research_code()}))["participant_id"]
    # Keep this paired-assessment integration test on its explicit legacy fixture.
    with SessionLocal() as db:
        participant = db.get(Participant, pid)
        participant.test_content_mode = "application"
        participant.first_question_only = False
        db.commit()
    complete_presurvey(client, pid)
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
    assert reviewed["test_results"]["results"] == []
    with SessionLocal() as db:
        metrics = participant_metrics(db, db.get(Participant, pid))
        assert metrics["questions_per_test"] == 6
        assert metrics["h1"]["pretest_score"] == 4 / 6


@pytest.mark.parametrize("pretest_perfect", [False, True])
def test_split_maximum_rounds_and_mastery(pretest_perfect):
    client = AuthenticatedTestClient(app)
    pid = ok(client.post("/api/registrations", json={"assignment_code": "B", "consent_checked": True, "research_code": new_research_code()}))["participant_id"]
    complete_presurvey(client, pid)
    def answer(phase, correct):
        questions = ok(client.get(f"/api/experiment/{pid}/{phase}"))["questions"]
        for q in questions:
            with SessionLocal() as db:
                correct_options = db.query(QuestionOption).filter_by(question_id=q["question_id"], is_correct=True).all()
                selected = [option.id for option in correct_options] if correct else [q["options"][-1]["option_id"]]
            ok(client.post("/api/attempts", json={"participant_id": pid, "question_id": q["question_id"], "phase": phase.replace("-", "_"), "selected_option_ids": selected}))
        acknowledge_all_question_reviews(client, pid, phase.replace("-", "_"))
    answer("pretest", pretest_perfect)
    diagnosed = ok(client.post(f"/api/participants/{pid}/diagnose-pretest", json={}))
    if pretest_perfect:
        assert diagnosed["next_step"] == "survey"
        assert diagnosed["next_url"] == "/survey"
        assert ok(client.get(f"/api/participants/{pid}/current-step"))["next_url"] == "/survey"
        assert client.get(f"/api/experiment/{pid}/final-test").status_code == 409
        assert client.get(f"/api/experiment/{pid}/retest").status_code == 409
        return
    ok(client.post(f"/api/participants/{pid}/give-up-learning", json={}))
    phase = "retest"
    answer(phase, False)
    result = ok(client.post(f"/api/participants/{pid}/score-{phase}", json={}))
    assert result["next_step"] == "learning_targets"
    ok(client.post(f"/api/participants/{pid}/give-up-learning", json={}))
    answer("retest", True)
    result = ok(client.post(f"/api/participants/{pid}/score-retest", json={}))
    assert result["next_step"] == "survey"
    assert result["post_pretest_tests_completed"] == 2
    assert client.get(f"/api/experiment/{pid}/retest").status_code == 409


@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
@pytest.mark.parametrize("slug", ["llm_knowledge", "multi_agent", "memory_process"])
def test_pretest_perfect_skips_learning_and_post_pretest_tests(group, layout, slug):
    with create_trial(group, layout, test_content_mode="application") as (client, pid):
        _questions, scored = answer_test(client, pid, "pretest", slug, (None, None))
        assert scored["next_step"] == "survey"
        assert ok(client.get(f"/api/participants/{pid}/current-step"))["next_url"] == "/survey"
        assert client.get(f"/api/experiment/{pid}/final-test").status_code == 409
        assert client.get(f"/api/experiment/{pid}/retest").status_code == 409
        assert client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": slug}).status_code == 409
