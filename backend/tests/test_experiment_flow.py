from pathlib import Path

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
    assert len(pretest) == 5
    assert [question["term_slug"] for question in pretest] == ["transformer", "attention", "llm_training_process", "pretraining", "post_training"]
    assert all(question["requires_reason"] is False for question in pretest)
    wrong_markers = {
        "transformer": "意識",
        "attention": "集中",
        "llm_training_process": "人間の学習段階",
        "pretraining": "性格",
        "post_training": "反省",
    }
    for question in pretest:
        wrong = next(option for option in question["options"] if wrong_markers[question["term_slug"]] in option["body"])
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
    assert diagnosis.json()["learning_target_count"] == 5

    targets = client.get(f"/api/participants/{pid}/learning-targets").json()["targets"]
    assert len(targets) == 5
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
    option = next(o for o in question["options"] if "意識" in o["body"])
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
    assert turn["teaching_strategy"] == "general_explanation"

from app.db.session import SessionLocal
from app.models import LearnerState, Term, TutorTurn


def _create_diagnosed_participant_with_all_targets():
    participant = client.post("/api/participants", json={"group_condition": "proposed", "consent_checked": True}).json()
    pid = participant["participant_id"]
    wrong_markers = {
        "transformer": "意識",
        "attention": "集中",
        "llm_training_process": "人間の学習段階",
        "pretraining": "性格",
        "post_training": "反省",
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

    _set_scaffolding_level(pid, "pretraining", "L3")
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "pretraining"}).json()
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    sufficient = client.post(
        f"/api/tutor-turns/{turn['turn_id']}/respond",
        json={"learner_response": "大規模で多様なデータから基盤能力を獲得します"},
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
    assert response["next_action"] == "continue"
    assert response["is_sufficient"] is False
    assert response["next_scaffolding_level"] == "L2"
    assert response["session_completed"] is False


def test_tutoring_turns_match_current_term_and_hide_internal_labels():
    pid = _create_diagnosed_participant_with_all_targets()
    expected_markers = {
        "transformer": ["Transformer", "Attention", "FFN"],
        "attention": ["Attention", "トークン", "重み"],
        "llm_training_process": ["事前学習", "インストラクション", "事後学習"],
        "pretraining": ["事前学習", "大規模", "基盤"],
        "post_training": ["事後学習", "人間評価", "安全"],
    }
    forbidden_by_term = {
        "transformer": ["過学習", "Embedding"],
        "attention": ["過学習", "Embedding"],
        "llm_training_process": ["Embedding", "過学習"],
        "pretraining": ["Embedding", "過学習"],
        "post_training": ["Embedding", "過学習"],
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
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "pretraining"}).json()
    first = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    answer = "まだ使う前の注意書きのことだと思っています"
    feedback = client.post(f"/api/tutor-turns/{first['turn_id']}/respond", json={"learner_response": answer}).json()
    assert feedback["is_sufficient"] is False
    second = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert "前の問題:" in second["tutor_message"]
    assert first["practice_question"]["body"] in second["tutor_message"]
    assert "あなたの回答:" in second["tutor_message"]
    assert answer in second["tutor_message"]


def test_rag_retriever_returns_chunks():
    from app.rag.retriever import retrieve_rag_context

    context = retrieve_rag_context("Transformer Attention FFN", top_k=2)
    assert context["source"] == "rag_ready_教材"
    assert context["retrieval_method"] == "local_sparse_tfidf"
    assert context["status"] == "ok"
    assert len(context["chunks"]) == 2
    assert all("text" in chunk for chunk in context["chunks"])


def test_tutor_and_feedback_payload_include_rag_context(monkeypatch):
    pid = _create_diagnosed_participant_with_all_targets()
    _set_scaffolding_level(pid, "transformer", "L2")
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "transformer"}).json()

    async def fake_generate(db, purpose, payload):
        assert purpose == "generate_tutoring_turn"
        assert payload["rag_context"]["source"] == "rag_ready_教材"
        assert "chunks" in payload["rag_context"]
        return {
            "tutor_message": "Transformerの教材です。",
            "teaching_strategy": "category_reorientation",
            "scaffolding_level": "L3",
            "requires_learner_response": True,
            "learner_prompt": "Transformerを説明してください。",
            "practice_question": {
                "body": "Transformerを説明してください。",
                "expected_answer": "AttentionとFFNを重ねる構造",
                "question_type": "practice",
            },
            "forbidden_help_given": False,
        }

    monkeypatch.setattr("app.services.experiment._ai_call", fake_generate)
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()

    async def fake_feedback(db, purpose, payload):
        assert purpose == "generate_feedback"
        assert payload["rag_context"]["source"] == "rag_ready_教材"
        assert "chunks" in payload["rag_context"]
        return {
            "feedback": "十分です。",
            "is_sufficient": True,
            "next_action": "move_next",
            "next_scaffolding_level": "L1",
            "strategy_changed": False,
            "state_update_reason": "test",
        }

    monkeypatch.setattr("app.services.experiment._ai_call", fake_feedback)
    response = client.post(
        f"/api/tutor-turns/{turn['turn_id']}/respond",
        json={"learner_response": "AttentionとFFNで関係と特徴変換を扱います"},
    ).json()
    assert response["is_sufficient"] is True



def test_stage_based_learning_progresses_terms_then_concept():
    pid = _create_diagnosed_participant_with_all_targets()
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "transformer"}).json()

    first = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert first["term_label"] == "Transformer"
    assert first["learning_stage"] == "term_understanding"
    assert first["component_term"] == "Attention"
    first_feedback = client.post(
        f"/api/tutor-turns/{first['turn_id']}/respond",
        json={"learner_response": "Attentionはトークン間の関係を扱います"},
    ).json()
    assert first_feedback["is_sufficient"] is True
    assert first_feedback["session_completed"] is False
    assert first_feedback["next_learning_stage"] == "term_understanding"
    assert first_feedback["next_component_index"] == 1

    second = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert second["component_term"] == "FFN"
    second_feedback = client.post(
        f"/api/tutor-turns/{second['turn_id']}/respond",
        json={"learner_response": "FFNは各トークンの特徴を変換します"},
    ).json()
    assert second_feedback["session_completed"] is False
    assert second_feedback["next_component_index"] == 2

    third = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert third["component_term"] == "トークン間の関係性"
    third_feedback = client.post(
        f"/api/tutor-turns/{third['turn_id']}/respond",
        json={"learner_response": "トークン間の関係性は語同士の関係を表します"},
    ).json()
    assert third_feedback["session_completed"] is False
    assert third_feedback["stage_completed"] is True
    assert third_feedback["next_learning_stage"] == "concept_understanding"

    concept = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert concept["learning_stage"] == "concept_understanding"
    assert concept["component_term"] is None
    final_feedback = client.post(
        f"/api/tutor-turns/{concept['turn_id']}/respond",
        json={"learner_response": "TransformerはAttentionとFFNを重ね、トークン間の関係と特徴変換を扱う構造です"},
    ).json()
    assert final_feedback["is_sufficient"] is True
    assert final_feedback["session_completed"] is True
    assert final_feedback["next_learning_stage"] == "final_feedback"


def test_concept_insufficient_returns_to_term_understanding():
    pid = _create_diagnosed_participant_with_all_targets()
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "attention"}).json()
    for answer in [
        "トークンは入力を分けた単位です",
        "関係はトークン同士の関係です",
        "重み付けは関係に重みをつけることです",
        "重要度は重みによってどれを重要に扱うかです",
    ]:
        turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
        feedback = client.post(f"/api/tutor-turns/{turn['turn_id']}/respond", json={"learner_response": answer}).json()
        assert feedback["session_completed"] is False
    concept = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert concept["learning_stage"] == "concept_understanding"
    insufficient = client.post(f"/api/tutor-turns/{concept['turn_id']}/respond", json={"learner_response": "重要な単語を探します"}).json()
    assert insufficient["is_sufficient"] is False
    assert insufficient["session_completed"] is False
    assert insufficient["next_learning_stage"] == "term_understanding"
    assert insufficient["next_component_index"] == 0
    restart = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert restart["learning_stage"] == "term_understanding"
    assert restart["component_term"] == "トークン"



def test_tutoring_prompt_no_longer_reduces_explanation_by_scaffolding_level():
    prompt_source = Path(__file__).resolve().parents[1] / "app" / "ai" / "codex_app_server_backend.py"
    text = prompt_source.read_text()
    assert "L2では現在の用語を判断する観点を1〜2個に絞って示し" not in text
    assert "L1では詳しい説明を避け" not in text
    assert "説明量を L1/L2/L3 で減らさない" in text
    assert "定義、対象概念の中での役割、よくある誤解との違い" in text


def test_initial_component_material_is_complete_explanation():
    pid = _create_diagnosed_participant_with_all_targets()
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "post_training"}).json()
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert turn["learning_stage"] == "term_understanding"
    assert turn["component_term"] == "人間評価"
    material = turn["tutor_message"]
    for expected in ["人間評価とは", "役割", "よくある誤解", "判断基準", "人間", "安全性", "有用性"]:
        assert expected in material



def test_learning_session_misconception_is_saved_and_returned_separately():
    pid = _create_diagnosed_participant_with_all_targets()
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "post_training"}).json()
    first = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert first["initial_misconception_type"] == "M1"
    assert first["latest_learning_misconception_type"] is None
    response = client.post(f"/api/tutor-turns/{first['turn_id']}/respond", json={"learner_response": "わかんない"}).json()
    assert response["learning_misconception_type"] == "unknown"
    assert response["learning_misconception_reason"]

    db = SessionLocal()
    try:
        saved_turn = db.get(TutorTurn, first["turn_id"])
        assert saved_turn.grading_json["learning_misconception_type"] == "unknown"
        state = db.query(LearnerState).join(Term, LearnerState.term_id == Term.id).filter(LearnerState.participant_id == pid, Term.slug == "post_training").one()
        assert state.primary_misconception == "M1"
    finally:
        db.close()

    second = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert second["initial_misconception_type"] == "M1"
    assert second["latest_learning_misconception_type"] == "unknown"
    assert second["session_misconception_history"][0]["label"] == "人間評価"
    assert second["session_misconception_history"][0]["misconception_type"] == "unknown"
    assert second["teaching_strategy"] == "foundational_explanation"


def test_control_group_keeps_general_strategy_with_learning_misconception():
    participant = client.post("/api/participants", json={"group_condition": "control", "consent_checked": True}).json()
    pid = participant["participant_id"]
    question = client.get(f"/api/experiment/{pid}/pretest").json()["questions"][0]
    option = next(o for o in question["options"] if "意識" in o["body"])
    client.post("/api/attempts", json={"participant_id": pid, "question_id": question["question_id"], "phase": "pretest", "selected_option_id": option["option_id"]})
    client.post(f"/api/participants/{pid}/diagnose-pretest")
    target = client.get(f"/api/participants/{pid}/learning-targets").json()["targets"][0]
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": target["term_slug"]}).json()
    first = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    response = client.post(f"/api/tutor-turns/{first['turn_id']}/respond", json={"learner_response": "わかんない"}).json()
    assert response["learning_misconception_type"] == "unknown"
    second = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert second["latest_learning_misconception_type"] == "unknown"
    assert second["teaching_strategy"] == "general_explanation"


def _option_containing(question: dict, marker: str) -> dict:
    return next(option for option in question["options"] if marker in option["body"])


def test_iterative_retest_removes_correct_terms_and_routes_to_final_test():
    participant = client.post("/api/participants", json={"group_condition": "proposed", "consent_checked": True}).json()
    pid = participant["participant_id"]
    pretest_answers = {
        "transformer": "Attentionレイヤー",
        "attention": "入力中のトークン",
        "llm_training_process": "人間の学習段階",
        "pretraining": "わからない",
        "post_training": "事前学習と同じ",
    }
    for question in client.get(f"/api/experiment/{pid}/pretest").json()["questions"]:
        option = _option_containing(question, pretest_answers[question["term_slug"]])
        assert client.post(
            "/api/attempts",
            json={"participant_id": pid, "question_id": question["question_id"], "phase": "pretest", "selected_option_id": option["option_id"]},
        ).status_code == 200

    diagnosis = client.post(f"/api/participants/{pid}/diagnose-pretest").json()
    assert diagnosis["learning_target_count"] == 3
    assert diagnosis["next_url"] == "/learning-targets"
    targets = client.get(f"/api/participants/{pid}/learning-targets").json()["targets"]
    assert {target["term_slug"] for target in targets} == {"llm_training_process", "post_training", "pretraining"}

    retest = client.get(f"/api/experiment/{pid}/retest").json()["questions"]
    assert [question["term_slug"] for question in retest] == ["llm_training_process", "pretraining", "post_training"]
    retest_answers = {
        "llm_training_process": "事前学習で基盤能力",
        "pretraining": "わからない",
        "post_training": "人間評価や報酬モデル",
    }
    for question in retest:
        option = _option_containing(question, retest_answers[question["term_slug"]])
        assert client.post(
            "/api/attempts",
            json={"participant_id": pid, "question_id": question["question_id"], "phase": "retest", "selected_option_id": option["option_id"], "reason_text": "確認"},
        ).status_code == 200
    score = client.post(f"/api/participants/{pid}/score-retest").json()
    assert score["next_url"] == "/learning-targets"

    targets = client.get(f"/api/participants/{pid}/learning-targets").json()["targets"]
    assert [target["term_slug"] for target in targets] == ["pretraining"]
    second_retest = client.get(f"/api/experiment/{pid}/retest").json()["questions"]
    assert len(second_retest) == 1
    assert second_retest[0]["term_slug"] == "pretraining"
    assert second_retest[0]["body"].startswith("別の言い方で確認します。")
    option = _option_containing(second_retest[0], "大規模で多様なデータ")
    assert client.post(
        "/api/attempts",
        json={"participant_id": pid, "question_id": second_retest[0]["question_id"], "phase": "retest", "selected_option_id": option["option_id"], "reason_text": "大規模で多様なデータから基盤能力を得る"},
    ).status_code == 200
    score = client.post(f"/api/participants/{pid}/score-retest").json()
    assert score["next_url"] == "/final-test"
    assert client.get(f"/api/participants/{pid}/learning-targets").json()["targets"] == []

    final_questions = client.get(f"/api/experiment/{pid}/final-test").json()["questions"]
    assert len(final_questions) == 5


def test_m4_does_not_select_context_transfer_strategy():
    from app.ai.backend import strategy_for

    assert strategy_for("M4", "misconception", "proposed") != "context_transfer_training"
    assert strategy_for("M4", "misconception", "control") == "general_explanation"
