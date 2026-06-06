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
    assert participant["current_step"] == "pretest"

    pretest = client.get(f"/api/experiment/{pid}/pretest").json()["questions"]
    assert len(pretest) == 4
    assert [question["term_slug"] for question in pretest] == ["overfitting", "generalization", "attention", "embedding"]
    assert all(question["requires_reason"] is False for question in pretest)
    for question in pretest:
        wrong = next(option for option in question["options"] if "わからない" not in option["body"])
        response = client.post(
            "/api/attempts",
            json={
                "participant_id": pid,
                "question_id": question["question_id"],
                "phase": "pretest",
                "selected_option_id": wrong["option_id"],
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
        json={"learner_response": "判断基準を自分の言葉で説明します"},
    )
    assert feedback.status_code == 200

    for phase, get_path, score_path in [
        ("retest", f"/api/experiment/{pid}/retest", f"/api/participants/{pid}/score-retest"),
        ("l0_check", f"/api/experiment/{pid}/l0-check", f"/api/participants/{pid}/score-l0-check"),
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
        },
    )
    client.post(f"/api/participants/{pid}/diagnose-pretest")
    target = client.get(f"/api/participants/{pid}/learning-targets").json()["targets"][0]
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": target["term_slug"]}).json()
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert "一般" in turn["tutor_message"] or "定義" in turn["tutor_message"]

from app.db.session import SessionLocal
from app.models import LearnerState, Term


def _create_diagnosed_participant_with_all_targets():
    participant = client.post("/api/participants", json={"group_condition": "proposed", "consent_checked": True}).json()
    pid = participant["participant_id"]
    wrong_markers = {
        "overfitting": "疲れ",
        "generalization": "一般常識",
        "attention": "集中",
        "embedding": "保存場所",
    }
    for question in client.get(f"/api/experiment/{pid}/pretest").json()["questions"]:
        marker = wrong_markers[question["term_slug"]]
        option = next(option for option in question["options"] if marker in option["body"])
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


def _set_scaffolding_level(participant_id: str, term_slug: str, level: str) -> None:
    db = SessionLocal()
    try:
        term = db.query(Term).filter_by(slug=term_slug).one()
        state = db.query(LearnerState).filter_by(participant_id=participant_id, term_id=term.id).one()
        state.scaffolding_level = level
        db.commit()
    finally:
        db.close()


def test_learning_response_sufficiency_controls_scaffolding_level():
    pid = _create_diagnosed_participant_with_all_targets()
    _set_scaffolding_level(pid, "attention", "L1")
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "attention"}).json()
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    insufficient = client.post(f"/api/tutor-turns/{turn['turn_id']}/respond", json={"learner_response": "まだよくわかりません"}).json()
    assert insufficient["is_sufficient"] is False
    assert insufficient["next_scaffolding_level"] == "L2"

    _set_scaffolding_level(pid, "embedding", "L3")
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "embedding"}).json()
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    sufficient = client.post(
        f"/api/tutor-turns/{turn['turn_id']}/respond",
        json={"learner_response": "単語や文を数値ベクトルにして意味の近さを扱います"},
    ).json()
    assert sufficient["is_sufficient"] is True
    assert sufficient["next_scaffolding_level"] == "L2"


def test_move_next_does_not_lower_level_when_response_is_insufficient(monkeypatch):
    pid = _create_diagnosed_participant_with_all_targets()
    _set_scaffolding_level(pid, "attention", "L1")
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "attention"}).json()
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()

    async def fake_feedback(db, purpose, payload):
        assert purpose == "generate_feedback"
        return {
            "feedback": "まだ判断基準が足りません。",
            "is_sufficient": False,
            "next_action": "move_next",
            "next_scaffolding_level": "L1",
            "strategy_changed": False,
            "state_update_reason": "forced test feedback",
        }

    monkeypatch.setattr("app.services.experiment._ai_call", fake_feedback)
    response = client.post(f"/api/tutor-turns/{turn['turn_id']}/respond", json={"learner_response": "不十分"}).json()
    assert response["next_action"] == "move_next"
    assert response["is_sufficient"] is False
    assert response["next_scaffolding_level"] == "L2"
    assert response["session_completed"] is False


def test_tutoring_turns_match_current_term_and_hide_internal_labels():
    pid = _create_diagnosed_participant_with_all_targets()
    expected_markers = {
        "attention": ["Attention", "関係", "重み"],
        "embedding": ["Embedding", "数値", "ベクトル"],
        "overfitting": ["過学習", "訓練", "未知"],
        "generalization": ["汎化", "未知", "適用"],
    }
    forbidden_by_term = {
        "attention": ["過学習", "Embeddingは"],
        "embedding": ["過学習", "Attentionは"],
        "overfitting": ["Embedding", "Attention"],
        "generalization": ["Embedding", "Attention"],
    }
    for term_slug, markers in expected_markers.items():
        session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": term_slug}).json()
        turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
        combined = f"{turn['tutor_message']} {turn['learner_prompt']} {turn['practice_question']['body']}"
        assert any(marker in combined for marker in markers)
        assert all(marker not in combined for marker in forbidden_by_term[term_slug])
        assert all(label not in combined for label in ["M1", "M2", "M3", "M4"])
        assert turn["misconception_type"] in {"M1", "M2", "M3", "M4", "unknown", None}
        assert turn["scaffolding_level"] in {"L1", "L2", "L3"}
        assert turn["teaching_strategy"]


def test_tutor_turn_uses_state_scaffolding_level_even_if_ai_returns_different_level(monkeypatch):
    pid = _create_diagnosed_participant_with_all_targets()
    _set_scaffolding_level(pid, "attention", "L2")
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "attention"}).json()

    async def fake_generate(db, purpose, payload):
        assert purpose == "generate_tutoring_turn"
        assert payload["learner_state"]["scaffolding_level"] == "L2"
        return {
            "tutor_message": "Attentionの教材です。",
            "teaching_strategy": "category_reorientation",
            "scaffolding_level": "L3",
            "requires_learner_response": True,
            "learner_prompt": "Attentionを説明してください。",
            "practice_question": {
                "body": "Attentionを説明してください。",
                "expected_answer": "関係を重み付けする仕組み",
                "question_type": "practice",
            },
            "forbidden_help_given": False,
        }

    monkeypatch.setattr("app.services.experiment._ai_call", fake_generate)
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert turn["scaffolding_level"] == "L2"


def test_second_turn_material_includes_previous_question_and_response():
    pid = _create_diagnosed_participant_with_all_targets()
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "generalization"}).json()
    first = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    answer = "まだ一般常識のことだと思っています"
    feedback = client.post(f"/api/tutor-turns/{first['turn_id']}/respond", json={"learner_response": answer}).json()
    assert feedback["is_sufficient"] is False
    second = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert "前の問題:" in second["tutor_message"]
    assert first["practice_question"]["body"] in second["tutor_message"]
    assert "あなたの回答:" in second["tutor_message"]
    assert answer in second["tutor_message"]
