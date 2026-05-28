from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_full_mock_experiment_flow():
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    participant = client.post("/api/participants", json={"group_condition": "proposed", "consent_checked": True}).json()
    pid = participant["participant_id"]
    assert participant["group_condition"] == "proposed"

    survey = client.post(
        f"/api/participants/{pid}/survey",
        json={
            "phase": "pre_survey",
            "ai_experience_level": 2,
            "programming_experience_level": 2,
            "llm_usage_level": 3,
            "self_rated_ai_knowledge": 2,
        },
    )
    assert survey.status_code == 200

    pretest = client.get(f"/api/experiment/{pid}/pretest").json()["questions"]
    assert len(pretest) == 8
    for question in pretest:
        wrong = next(option for option in question["options"] if "わからない" not in option["body"])
        response = client.post(
            "/api/attempts",
            json={
                "participant_id": pid,
                "question_id": question["question_id"],
                "phase": "pretest",
                "selected_option_id": wrong["option_id"],
                "reason_text": "言葉の印象で選びました",
                "confidence": 4,
            },
        )
        assert response.status_code == 200

    diagnosis = client.post(f"/api/participants/{pid}/diagnose-pretest")
    assert diagnosis.status_code == 200
    assert diagnosis.json()["learning_target_count"] == 4

    targets = client.get(f"/api/participants/{pid}/learning-targets").json()["targets"]
    assert len(targets) == 4
    assert "term_slug" in targets[0]
    assert "M1" not in targets[0]["summary_for_learner"]

    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": targets[0]["term_slug"]}).json()
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert turn["requires_learner_response"] is True
    feedback = client.post(
        f"/api/tutor-turns/{turn['turn_id']}/respond",
        json={"learner_response": "判断基準を自分の言葉で説明します", "confidence": 4},
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
                "confidence": 4,
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
    option = next(o for o in question["options"] if "わからない" not in o["body"])
    client.post(
        "/api/attempts",
        json={
            "participant_id": pid,
            "question_id": question["question_id"],
            "phase": "pretest",
            "selected_option_id": option["option_id"],
            "reason_text": "言葉で判断しました",
            "confidence": 4,
        },
    )
    client.post(f"/api/participants/{pid}/diagnose-pretest")
    target = client.get(f"/api/participants/{pid}/learning-targets").json()["targets"][0]
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": target["term_slug"]}).json()
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert "一般" in turn["tutor_message"] or "定義" in turn["tutor_message"]
