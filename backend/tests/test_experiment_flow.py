from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models import AICallLog


client = TestClient(app)


def _ai_call_count(purpose: str) -> int:
    db = SessionLocal()
    try:
        return db.query(AICallLog).filter_by(purpose=purpose, status="success").count()
    finally:
        db.close()


def _option_containing(question: dict, marker: str) -> dict:
    return next(option for option in question["options"] if marker in option["body"])


def _create_participant_with_pretest(group: str = "proposed", *, correct: bool = False) -> str:
    participant = client.post("/api/participants", json={"group_condition": group, "consent_checked": True}).json()
    pid = participant["participant_id"]
    markers = {
        "llm_training_process": "大量のテキストで言語パターン" if correct else "入力された文章を理解",
        "transformer": "Attentionレイヤーでトークン間" if correct else "文章全体の意味を理解",
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


def test_pretest_returns_only_llm_training_process_and_transformer():
    participant = client.post("/api/participants", json={"group_condition": "proposed", "consent_checked": True}).json()
    questions = client.get(f"/api/experiment/{participant['participant_id']}/pretest").json()["questions"]

    assert [question["term_slug"] for question in questions] == ["llm_training_process", "transformer"]
    assert len(questions) == 2
    assert all(question["options"] for question in questions)
    assert all(question["requires_reason"] is False for question in questions)


def test_final_test_is_choice_only_and_scores_without_reason():
    pid = _create_participant_with_pretest(correct=True)
    final_questions = client.get(f"/api/experiment/{pid}/final-test").json()["questions"]

    assert [question["term_slug"] for question in final_questions] == ["llm_training_process", "transformer"]
    assert all(question["question_type"] == "final_choice" for question in final_questions)
    assert all(question["requires_reason"] is False for question in final_questions)
    assert all(question["options"] for question in final_questions)

    for question in final_questions:
        correct = next(option for option in question["options"] if option["body"] != "わからない。" and option["label"])
        # Pick the actual correct option by stable text markers because option display order is randomized.
        if question["term_slug"] == "llm_training_process":
            correct = _option_containing(question, "事前学習、インストラクションチューニング、事後学習")
        else:
            correct = _option_containing(question, "Transformer。Attentionレイヤー")
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
    ai_calls_before = _ai_call_count("generate_tutoring_turn")
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert _ai_call_count("generate_tutoring_turn") == ai_calls_before

    assert turn["term_label"] in {"LLMの学習段階", "Transformer"}
    assert turn["teaching_strategy"] == "general_explanation"
    assert turn["learning_stage"] == "concept_understanding"
    assert "L3" not in turn["practice_question"]["question_type"]
    assert turn["practice_question"]["question_type"] == "control_l2_check"
    assert "事前学習" in turn["tutor_message"] or "Attention" in turn["tutor_message"]
    assert len(turn["practice_question"]["options"]) == 5

    learner_response = (
        "事前学習、インストラクションチューニング、事後学習の目的が違います。"
        if target["term_slug"] == "llm_training_process"
        else "Attentionで関係性を扱い、FFNで特徴を変換します。"
    )
    response = client.post(
        f"/api/tutor-turns/{turn['turn_id']}/respond",
        json={"learner_response": learner_response},
    ).json()
    assert response["next_learning_stage"] == "final_feedback"
    assert response["session_completed"] is True


def _answer_for_component(component_term: str) -> str:
    return {
        "事前学習": "事前学習は大規模データから基盤能力を作る段階です。",
        "インストラクションチューニング": "インストラクションチューニングは指示と応答の例から指示応答を学ぶ段階です。",
        "事後学習": "事後学習は人間評価などで安全性や有用性を調整する段階です。",
        "Attentionレイヤー": "Attentionレイヤーはトークン間の関係性を計算して重み付けします。",
        "FFNレイヤー": "FFNレイヤーは各トークンの特徴を変換します。",
        "トークン間の関係性": "トークン間の関係性は離れたトークン同士のつながりを扱う情報です。",
    }[component_term]


def _assert_component_sequence(pid: str, term_slug: str, expected_components: list[str], concept_answer: str) -> None:
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": term_slug}).json()

    ai_calls_before = _ai_call_count("generate_tutoring_turn")
    for index, component in enumerate(expected_components):
        turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
        assert _ai_call_count("generate_tutoring_turn") == ai_calls_before + index + 1
        assert turn["learning_stage"] == "term_understanding"
        assert turn["component_term"] == component
        assert turn["component_index"] == index
        assert turn["component_total"] == len(expected_components)
        assert len(turn["practice_question"]["options"]) == 5
        correct_option = next(option for option in turn["practice_question"]["options"] if option["label"] == "A")
        feedback = client.post(
            f"/api/tutor-turns/{turn['turn_id']}/respond",
            json={"selected_option_id": correct_option["option_id"]},
        ).json()
        assert feedback["is_sufficient"] is True
        assert feedback["session_completed"] is False
        expected_next = "concept_understanding" if index == len(expected_components) - 1 else "term_understanding"
        assert feedback["next_learning_stage"] == expected_next

    concept = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()
    assert _ai_call_count("generate_tutoring_turn") == ai_calls_before + len(expected_components) + 1
    assert concept["learning_stage"] == "concept_understanding"
    assert len(concept["practice_question"]["options"]) == 5
    concept_correct = next(option for option in concept["practice_question"]["options"] if option["label"] == "A")
    concept_feedback = client.post(
        f"/api/tutor-turns/{concept['turn_id']}/respond",
        json={"selected_option_id": concept_correct["option_id"]},
    ).json()
    assert concept_feedback["is_sufficient"] is True
    assert concept_feedback["session_completed"] is True
    assert concept_feedback["next_learning_stage"] == "final_feedback"


def test_proposed_group_progresses_llm_training_components_then_l2_question():
    pid = _create_participant_with_pretest(group="proposed")
    _assert_component_sequence(
        pid,
        "llm_training_process",
        ["事前学習", "インストラクションチューニング", "事後学習"],
        "事前学習、インストラクションチューニング、事後学習の3段階でLLMの学習プロセスを説明できます。",
    )


def test_proposed_group_progresses_transformer_components_then_l2_question():
    pid = _create_participant_with_pretest(group="proposed")
    _assert_component_sequence(
        pid,
        "transformer",
        ["Attentionレイヤー", "FFNレイヤー", "トークン間の関係性"],
        "TransformerはAttentionでトークン間の関係性を扱い、FFNで各トークンの特徴を変換します。",
    )



def test_learning_choice_incorrect_option_sets_learning_misconception_type():
    pid = _create_participant_with_pretest(group="proposed")
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "transformer"}).json()
    turn = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}).json()

    assert turn["learning_stage"] == "term_understanding"
    wrong_option = next(option for option in turn["practice_question"]["options"] if option["label"] == "B")
    feedback = client.post(
        f"/api/tutor-turns/{turn['turn_id']}/respond",
        json={"selected_option_id": wrong_option["option_id"]},
    ).json()

    assert feedback["is_sufficient"] is False
    assert feedback["next_learning_stage"] == "term_understanding"
    assert feedback["learning_misconception_type"] == "M1"


def test_retest_removes_correct_terms_and_final_test_stays_two_items():
    pid = _create_participant_with_pretest(group="proposed")
    retest = client.get(f"/api/experiment/{pid}/retest").json()["questions"]
    assert [question["term_slug"] for question in retest] == ["llm_training_process", "transformer"]
    assert all(question["requires_reason"] is False for question in retest)

    answers = {
        "llm_training_process": "人間の学習段階",
        "transformer": "Attentionでトークン間の関係性",
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
    participant_logs = client.get(f"/api/admin/participants/{pid}/logs").json()
    assert all(state["scaffolding_level"] in {"L2", "L3"} for state in participant_logs["learner_states"])
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
    assert any(row["term_slug"] == "transformer" for row in logs_json["attempts"])
    assert "learner_states" in logs_json
    assert "ai_call_logs" in logs_json

    overview_csv = client.get("/api/admin/logs/overview.csv")
    assert overview_csv.status_code == 200
    assert "record_type,participant_id,display_code,phase,term_slug,event_time,summary,value_json" in overview_csv.text
    assert "attempt" in overview_csv.text
    overview_excel_csv = client.get("/api/admin/logs/overview_excel.csv")
    assert overview_excel_csv.status_code == 200
    assert overview_excel_csv.content.startswith(b"\xef\xbb\xbf")
    assert "attempt".encode() in overview_excel_csv.content

    participant_csv = client.get(f"/api/admin/participants/{pid}/logs.csv")
    assert participant_csv.status_code == 200
    assert "record_type,participant_id,display_code,phase,term_slug,event_time,summary,value_json" in participant_csv.text
    assert "attempt" in participant_csv.text
    participant_excel_csv = client.get(f"/api/admin/participants/{pid}/logs_excel.csv")
    assert participant_excel_csv.status_code == 200
    assert participant_excel_csv.content.startswith(b"\xef\xbb\xbf")
    assert "attempt".encode() in participant_excel_csv.content


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


def test_rag_retrieves_current_active_material_chunks():
    from app.rag.retriever import retrieve_rag_context

    llm_context = retrieve_rag_context("LLMの学習プロセス 事前学習 インストラクションチューニング 事後学習")
    assert llm_context["status"] == "ok"
    assert any("LLM の学習プロセス" in chunk["section"] for chunk in llm_context["chunks"])

    transformer_context = retrieve_rag_context("Transformer Attention FFN トークン間の関係性")
    assert transformer_context["status"] == "ok"
    assert any("Transformer の解説" in chunk["section"] for chunk in transformer_context["chunks"])
