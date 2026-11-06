"""Shared assertions for the current six-item API contract.

Historical revision fixtures keep their original text checks. Their live-flow
cases use these helpers because confirmation now repeats failed test items.
"""

from contextlib import contextmanager

from admin_client import AuthenticatedTestClient

from app.db.session import SessionLocal
from app.main import app
from app.models import Attempt, Question, QuestionOption, TutorSession, TutorTurn
from app.services.interaction_history import build_interaction_history
from app.services.prefetch import wait_for_prefetch_tasks


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def complete_presurvey(client, pid):
    payload = {
        "survey_version": "presurvey-baseline-v2",
        "prior_term_knowledge": {
            "pretraining": "unknown",
            "fine_tuning": "unknown",
            "rag": "unknown",
            "prompt_engineering": "unknown",
            "multi_agent": "unknown",
            "memory_process": "unknown",
        },
        "general_ratings": {"ai_usage_frequency": 1, "self_rated_ai_proficiency": 1},
    }
    return ok(client.post(f"/api/participants/{pid}/presurvey", json=payload))


def acknowledge_all_question_reviews(client, pid, phase):
    """Complete the in-page reviews before exercising phase scoring or learning."""
    path = f"/api/experiment/{pid}/{phase.replace('_', '-')}"
    for _ in range(3):
        pending = ok(client.get(path)).get("pending_question_review")
        if pending is None:
            return
        ok(client.post(
            f"/api/participants/{pid}/question-review-acknowledgements",
            json={"phase": phase, "term_slug": pending["term_slug"]},
        ))
    assert ok(client.get(path)).get("pending_question_review") is None, "all three term reviews must be acknowledged"


def case_roles(labels):
    # Old revision case names describe outcomes, not new four-choice labels.
    if labels == "ABC":
        return (None, None)
    if labels == "J":
        return ("unknown", "unknown")
    if labels == "DEF":
        return ("M1", "M1")
    if labels == "GHI":
        return ("M3", "M3")
    if set(labels) & set("GHI"):
        return ("M1", "M3") if set(labels) & set("DEF") else (None, "M3")
    assert set(labels) & set("DEF"), labels
    return (None, "M1")


def select_roles(question, roles):
    """Select from internal DB metadata, never assume displayed correct labels."""
    with SessionLocal() as db:
        rows = db.query(QuestionOption).filter_by(question_id=question["question_id"]).order_by(QuestionOption.option_label).all()
        if question.get("selection_mode") == "single" or len(question["options"]) in {4, 6}:
            assert len(roles) == 1
            role = roles[0]
            row = next(row for row in rows if row.is_correct) if role is None else next(row for row in rows if row.misconception_type == role)
            rows = [row]
        else:
            available = list(rows)
            rows = []
            for role in roles:
                row = next(row for row in available if row.misconception_type == role)
                rows.append(row)
                available.remove(row)
        ids = {row.id for row in rows}
        assert len(ids) == len(roles)
    return [option["option_id"] for option in question["options"] if option["option_id"] in ids]


@contextmanager
def create_trial(group, layout):
    client = AuthenticatedTestClient(app)
    previous = ok(client.get("/api/admin/option-order"))["mode"]
    ok(client.put("/api/admin/option-order", json={"mode": layout}))
    pid = ok(client.post("/api/registrations", json={"assignment_code": group, "consent_checked": True, "student_number": "SPLIT-CI-SYNTHETIC"}))["participant_id"]
    complete_presurvey(client, pid)
    try:
        yield client, pid
    finally:
        wait_for_prefetch_tasks()
        ok(client.delete(f"/api/admin/participants/{pid}"))
        ok(client.put("/api/admin/option-order", json={"mode": previous}))


def answer_test(client, pid, phase, slug, roles):
    questions = ok(client.get(f"/api/experiment/{pid}/{phase.replace('_', '-')}"))["questions"]
    assert len(questions) == 6
    indexes = {}
    for question in questions:
        assert len(question["options"]) == 6
        assert question["selection_mode"] == "single"
        assert question["options"][-1]["label"] == "F"
        assert question["options"][-1]["exclusive"]
        assert all(set(option) == {"option_id", "label", "body", "exclusive"} for option in question["options"])
        index = indexes.get(question["term_slug"], 0)
        indexes[question["term_slug"]] = index + 1
        selected = select_roles(question, [roles[index] if question["term_slug"] == slug else None])
        payload = {"participant_id": pid, "question_id": question["question_id"], "phase": phase, "selected_option_ids": selected}
        headers = {"Idempotency-Key": f"{phase}-{question['question_id']}"}
        response = ok(client.post("/api/attempts", json=payload, headers=headers))
        assert ok(client.post("/api/attempts", json=payload, headers=headers)) == response
    acknowledge_all_question_reviews(client, pid, phase)
    endpoint = "diagnose-pretest" if phase == "pretest" else f"score-{phase.replace('_', '-')}"
    scored = ok(client.post(f"/api/participants/{pid}/{endpoint}", json={}))
    return questions, scored


def confirm(client, pid, slug, questions, roles, expected_type, index):
    session = ok(client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": slug}))
    sid = session["tutor_session_id"]
    if index == 3:
        # Isolated synthetic session only; the normal route still stops at two.
        with SessionLocal() as db:
            db.get(TutorSession, sid).session_index = index
            db.commit()
    current = ok(client.post(f"/api/tutor-sessions/{sid}/turns", json={}))
    question = current["practice_question"]
    assert question["variant_key"] == "split_confirmation"
    assert question["learning_variant_index"] == index
    expected = [q for q in questions if q["term_slug"] == slug]
    assert question["questions"] == [{"question_id": q["question_id"], "body": q["body"], "options": q["options"]} for q in expected]
    assert "source_spec" not in question
    assert ok(client.post(f"/api/tutor-sessions/{sid}/turns", json={}))["practice_question"] == question
    assert client.post(f"/api/tutor-turns/{current['turn_id']}/respond", json={"selected_option_ids": []}).status_code == 400
    selected = [select_roles(q, [role])[0] for q, role in zip(expected, roles, strict=True)]
    payload = {"selected_option_ids": selected}
    headers = {"Idempotency-Key": f"confirm-{current['turn_id']}"}
    result = ok(client.post(f"/api/tutor-turns/{current['turn_id']}/respond", json=payload, headers=headers))
    assert result["is_sufficient"] == (expected_type is None)
    assert result["learning_misconception_type"] == expected_type
    assert result["feedback"] and result["session_completed"]
    assert result["max_turns"] == 1
    assert result["session_ended_by_attempt_limit"] == (expected_type is not None)
    assert ok(client.post(f"/api/tutor-turns/{current['turn_id']}/respond", json=payload, headers=headers)) == result
    wait_for_prefetch_tasks()
    with SessionLocal() as db:
        saved = db.get(TutorTurn, current["turn_id"])
        assert len(saved.grading_json["question_results"]) == 2
        assert [row["is_correct"] for row in saved.grading_json["question_results"]] == [role is None for role in roles]
        assert saved.practice_question_json["options"] == question["options"]
        assert saved.practice_question_json["source_spec"]["questions"] == question["questions"]
        history = build_interaction_history(db, pid, db.get(TutorSession, sid).term_id)
        record = next(row for row in history if row["source_type"] == "learning_turn" and row["session_index"] == index)
        assert record["question_body"] == question["body"]
        assert {o["body"] for o in record["selected_options"]} == {o["body"] for q in expected for o in q["options"] if o["option_id"] in selected}
    assert client.post(f"/api/tutor-sessions/{sid}/turns", json={}).status_code == 409
    return result


def assert_learning_flow(slug, group, layout, initial, labels, expected_type, index=1):
    with create_trial(group, layout) as (client, pid):
        initial_role = {"J": "unknown", "DEF": "M1", "GHI": "M3"}.get(initial, initial)
        questions, _ = answer_test(client, pid, "pretest", slug, (initial_role, initial_role))
        if index == 2:
            confirm(client, pid, slug, questions, (None, None), None, 1)
            questions, result = answer_test(client, pid, "retest", slug, (initial_role, initial_role))
            assert result["next_step"] == "learning_targets"
        return confirm(client, pid, slug, questions, case_roles(labels), expected_type, index)


def assert_retest_flow(slug, group, layout, phase, labels, expected_type, *, round_two=False, stop_after_first=False):
    with create_trial(group, layout) as (client, pid):
        initial = (None, None) if phase == "final_test" else ("unknown", "unknown")
        answer_test(client, pid, "pretest", slug, initial)
        if phase != "final_test":
            ok(client.post(f"/api/participants/{pid}/give-up-learning", json={}))
        if round_two:
            answer_test(client, pid, phase, slug, ("unknown", "unknown"))
            ok(client.post(f"/api/participants/{pid}/give-up-learning", json={}))
            phase = "retest"
        questions, scored = answer_test(client, pid, phase, slug, case_roles(labels))
        with SessionLocal() as db:
            attempts = db.query(Attempt).filter_by(participant_id=pid, phase=phase).all()
            latest_round = "retest_2" if round_two else "retest_1"
            attempts = [a for a in attempts if a.test_round == latest_round]
            assert len(attempts) == 6
            for q in questions:
                attempt = next(a for a in attempts if a.question_id == q["question_id"])
                assert attempt.question_body_snapshot == q["body"]
                assert attempt.option_order_snapshot == q["options"]
                source = db.get(Question, q["question_id"])
                assert source.variant_key.startswith("retest_v2_" if round_two else "retest_v1_")
                role = case_roles(labels)[int(source.variant_key[-1]) - 1] if q["term_slug"] == slug else None
                assert attempt.is_correct == (role is None)
                assert attempt.misconception_type == role
        review = ok(client.get(f"/api/participants/{pid}/learning-targets"))["test_results"]["results"]
        assert len(review) == 6
        assert {row["question_id"] for row in review} == {q["question_id"] for q in questions}
        assert all(row["question_body"] == next(q["body"] for q in questions if q["question_id"] == row["question_id"]) for row in review)
        assert scored["post_pretest_tests_completed"] == (2 if round_two else 1)
        assert scored["next_step"] == ("survey" if round_two or expected_type is None else "learning_targets")
        if not round_two and not stop_after_first and expected_type is not None:
            ok(client.post(f"/api/participants/{pid}/give-up-learning", json={}))
            _, second = answer_test(client, pid, "retest", slug, ("M1", "M1"))
            assert second["next_step"] == "survey" and second["post_pretest_tests_completed"] == 2
        if round_two or expected_type is None or not stop_after_first:
            assert client.get(f"/api/experiment/{pid}/retest").status_code == 409
