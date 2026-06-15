from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _option_containing(question: dict, marker: str) -> dict:
    return next(option for option in question["options"] if marker in option["body"])


def _create_participant_with_pretest(group: str = "proposed", *, correct: bool = False) -> str:
    participant = client.post("/api/participants", json={"group_condition": group, "consent_checked": True}).json()
    pid = participant["participant_id"]
    markers = {
        "transfer_learning": "あるデータやタスク" if correct else "保存場所",
        "llm_training_process": "事前学習、インストラクション" if correct else "人間の学習段階",
    }
    for question in client.get(f"/api/experiment/{pid}/pretest").json()["questions"]:
        option = _option_containing(question, markers[question["term_slug"]])
        response = client.post(
            "/api/attempts",
            json={
                "participant_id": pid,
                "question_id": question["question_id"],
                "phase": "pretest",
                "selected_option_id": option["option_id"],
            },
        )
        assert response.status_code == 200
    diagnosis = client.post(f"/api/participants/{pid}/diagnose-pretest")
    assert diagnosis.status_code == 200
    return pid


def test_pretest_returns_only_transfer_learning_and_llm_training_process():
    participant = client.post("/api/participants", json={"group_condition": "proposed", "consent_checked": True}).json()
    questions = client.get(f"/api/experiment/{participant['participant_id']}/pretest").json()["questions"]

    assert [question["term_slug"] for question in questions] == ["transfer_learning", "llm_training_process"]
    assert len(questions) == 2
    assert all(question["options"] for question in questions)
    assert all(question["requires_reason"] is False for question in questions)


def test_final_test_is_choice_only_and_scores_without_reason():
    pid = _create_participant_with_pretest(correct=True)
    final_questions = client.get(f"/api/experiment/{pid}/final-test").json()["questions"]

    assert [question["term_slug"] for question in final_questions] == ["transfer_learning", "llm_training_process"]
    assert all(question["question_type"] == "final_choice" for question in final_questions)
    assert all(question["requires_reason"] is False for question in final_questions)
    assert all(question["options"] for question in final_questions)

    for question in final_questions:
        correct = next(option for option in question["options"] if option["body"] != "わからない。" and option["label"])
        # Pick the actual correct option by stable text markers because option display order is randomized.
        if question["term_slug"] == "transfer_learning":
            correct = _option_containing(question, "転移学習。学習済みモデル")
        else:
            correct = _option_containing(question, "事前学習、インストラクションチューニング、事後学習")
        response = client.post(
            "/api/attempts",
            json={
                "participant_id": pid,
                "question_id": question["question_id"],
                "phase": "final_test",
                "selected_option_id": correct["option_id"],
            },
        )
        assert response.status_code == 200

    score = client.post(f"/api/participants/{pid}/score-final-test")
    assert score.status_code == 200
    assert score.json()["next_url"] == "/survey"

    summary = client.post(f"/api/participants/{pid}/evaluation-summary/recalculate")
    assert summary.status_code == 200
    export = client.get("/api/admin/export/evaluation_summary.csv")
    assert export.status_code == 200
    assert "l0_correct_rate" in export.text


def test_control_group_gets_l3_l2_material_but_only_l2_question():
    pid = _create_participant_with_pretest(group="control")
    target = client.get(f"/api/participants/{pid}/learning-targets").json()["targets"][0]
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": target["term_slug"]}).json()
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()

    assert turn["teaching_strategy"] == "general_explanation"
    assert turn["learning_stage"] == "concept_understanding"
    assert "L3" not in turn["practice_question"]["question_type"]
    assert turn["practice_question"]["question_type"] == "control_l2_check"
    assert "転移学習は" in turn["tutor_message"] or "LLMの学習段階" in turn["tutor_message"]
    assert "重要" in turn["tutor_message"]

    learner_response = (
        "学習済みモデルを関連する別タスクへ活用する点が重要です。"
        if target["term_slug"] == "transfer_learning"
        else "事前学習、インストラクションチューニング、事後学習の目的が違います。"
    )
    response = client.post(
        f"/api/tutor-turns/{turn['turn_id']}/respond",
        json={"learner_response": learner_response},
    ).json()
    assert response["next_learning_stage"] == "final_feedback"
    assert response["session_completed"] is True


def test_proposed_group_progresses_l3_question_then_l2_question():
    pid = _create_participant_with_pretest(group="proposed")
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "transfer_learning"}).json()

    first = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert first["learning_stage"] == "term_understanding"
    assert first["component_term"] == "L3基礎確認"
    assert first["practice_question"]["question_type"] == "proposed_l3_check"

    first_feedback = client.post(
        f"/api/tutor-turns/{first['turn_id']}/respond",
        json={"learner_response": "転移学習は学習済みモデルを関連する別タスクへ活用する方法です。"},
    ).json()
    assert first_feedback["is_sufficient"] is True
    assert first_feedback["session_completed"] is False
    assert first_feedback["next_learning_stage"] == "concept_understanding"

    second = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert second["learning_stage"] == "concept_understanding"
    assert second["practice_question"]["body"] == "転移学習を単なるデータ移動やゼロからの事前学習と説明すると、どの点が不足しますか？"

    second_feedback = client.post(
        f"/api/tutor-turns/{second['turn_id']}/respond",
        json={"learner_response": "学習済みモデルを別タスクへ活用する点が不足しています。"},
    ).json()
    assert second_feedback["is_sufficient"] is True
    assert second_feedback["session_completed"] is True
    assert second_feedback["next_learning_stage"] == "final_feedback"


def test_retest_removes_correct_terms_and_final_test_stays_two_items():
    pid = _create_participant_with_pretest(group="proposed")
    retest = client.get(f"/api/experiment/{pid}/retest").json()["questions"]
    assert [question["term_slug"] for question in retest] == ["transfer_learning", "llm_training_process"]
    assert all(question["requires_reason"] is False for question in retest)

    answers = {
        "transfer_learning": "関連するタスクで学習済み",
        "llm_training_process": "人間の学習段階",
    }
    for question in retest:
        option = _option_containing(question, answers[question["term_slug"]])
        assert client.post(
            "/api/attempts",
            json={
                "participant_id": pid,
                "question_id": question["question_id"],
                "phase": "retest",
                "selected_option_id": option["option_id"],
            },
        ).status_code == 200

    score = client.post(f"/api/participants/{pid}/score-retest").json()
    assert score["next_url"] == "/learning-targets"
    targets = client.get(f"/api/participants/{pid}/learning-targets").json()["targets"]
    assert [target["term_slug"] for target in targets] == ["llm_training_process"]

    final_questions = client.get(f"/api/experiment/{pid}/final-test").json()["questions"]
    assert len(final_questions) == 2
    assert all(question["requires_reason"] is False for question in final_questions)


def test_admin_overview_and_participant_logs_have_json_and_csv():
    pid = _create_participant_with_pretest(group="proposed")

    overview = client.get("/api/admin/logs/overview")
    assert overview.status_code == 200
    overview_json = overview.json()
    assert "participants" in overview_json
    assert "recent_attempts" in overview_json
    assert any(row["participant_id"] == pid for row in overview_json["participants"])

    participant_logs = client.get(f"/api/admin/participants/{pid}/logs")
    assert participant_logs.status_code == 200
    logs_json = participant_logs.json()
    assert logs_json["participant"]["participant_id"] == pid
    assert len(logs_json["attempts"]) == 2
    assert "learner_states" in logs_json
    assert "ai_call_logs" in logs_json

    overview_csv = client.get("/api/admin/logs/overview.csv")
    assert overview_csv.status_code == 200
    assert "record_type,participant_id,display_code,phase,term_slug,event_time,summary,value_json" in overview_csv.text
    assert "attempt" in overview_csv.text

    participant_csv = client.get(f"/api/admin/participants/{pid}/logs.csv")
    assert participant_csv.status_code == 200
    assert "record_type,participant_id,display_code,phase,term_slug,event_time,summary,value_json" in participant_csv.text
    assert "attempt" in participant_csv.text


def test_tutoring_prompt_contract_mentions_new_group_design():
    prompt_source = Path(__file__).resolve().parents[1] / "app" / "ai" / "codex_app_server_backend.py"
    text = prompt_source.read_text()
    assert "L3相当の基礎教材とL2相当の観点教材を両方" in text
    assert "質問はL2相当の1問だけ" in text
    assert "L3教材+L3質問、concept_understandingをL2教材+L2質問" in text


def test_m4_does_not_select_context_transfer_strategy():
    from app.ai.backend import strategy_for

    assert strategy_for("M4", "misconception", "proposed") != "context_transfer_training"
    assert strategy_for("M4", "misconception", "control") == "general_explanation"
