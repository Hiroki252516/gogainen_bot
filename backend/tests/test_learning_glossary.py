from copy import deepcopy
import csv
import json
from uuid import uuid4

import pytest
import yaml
from admin_client import AuthenticatedTestClient as TestClient

from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID
from app.db.session import SessionLocal
from app.main import app
from app.models import AICallLog, Participant, TutorTurn
from split_api_support import acknowledge_all_question_reviews, complete_presurvey, new_research_code, select_roles
from app.services import experiment
from app.services.learning_glossary import (
    GLOSSARY_PATH, GLOSSARY_VERSION, glossary_snapshot, load_learning_glossary,
    parse_learning_glossary, public_glossary,
)


client = TestClient(app)


def ids(message):
    return [entry["id"] for entry in glossary_snapshot(message)["entries"]]


def test_dictionary_and_snapshot_are_versioned_and_do_not_expose_sources():
    glossary = load_learning_glossary()
    assert len(glossary.entries) == 17
    assert glossary.version == GLOSSARY_VERSION
    definitions = {entry.id: entry.definition for entry in glossary.entries}
    assert definitions == {
        "weights": "AIが文章を作るための計算に使う数値です。学習によってこの数値が調整されると、AIが選ぶ言葉や回答の仕方が変わることがある",
        "additional_training": "既に学習したAIに、新しい学習用データを使ってさらに学習させ、回答の仕方などを目的に合わせて調整すること",
        "agent": "与えられた目的に向けて、状況を見ながら次の行動を判断して進めるAI",
        "model": "AI本体を指す",
        "rag": "質問に関係する資料を外部から検索し、取り出した情報を使ってAIに回答を作らせる仕組みです。",
    } | {entry.id: entry.definition for entry in glossary.entries if entry.id not in {"weights", "additional_training", "agent", "model"}}
    snapshot = glossary_snapshot("## 重み\n\n**モデル**のパラメータと重みを確認する。")
    assert [entry["id"] for entry in snapshot["entries"]] == ["weights", "model", "parameters"]
    assert len(snapshot["dictionary_sha256"]) == 64
    public = public_glossary(snapshot)
    assert set(public) == {"version", "entries"}
    assert all(set(entry) == {"id", "term", "definition"} for entry in public["entries"])
    assert public_glossary(None) is None
    public["entries"][0]["definition"] = "changed"
    assert snapshot["entries"][0]["definition"] != "changed"


def test_existing_v2_snapshot_keeps_its_saved_definition():
    saved = {
        "version": "learning-glossary-v2",
        "dictionary_sha256": "historical-v2-fingerprint",
        "entries": [{
            "id": "weights",
            "term": "重み",
            "definition": "AIの内部の計算で、ある情報をどれくらい結果に反映するかに関わる数値。学習の過程で調整されます。",
        }],
    }

    assert public_glossary(saved) == {
        "version": "learning-glossary-v2",
        "entries": [{
            "id": "weights",
            "term": "重み",
            "definition": "AIの内部の計算で、ある情報をどれくらい結果に反映するかに関わる数値。学習の過程で調整されます。",
        }],
    }


def test_existing_v3_snapshot_keeps_its_saved_definition():
    definition = "AIが文章を作るための計算に使う数値です。学習によってこの数値が調整されると、AIが選ぶ言葉や回答の仕方が変わることがある"
    saved = {
        "version": "learning-glossary-v3",
        "dictionary_sha256": "historical-v3-fingerprint",
        "entries": [{"id": "weights", "term": "重み", "definition": definition}],
    }

    assert public_glossary(saved) == {
        "version": "learning-glossary-v3",
        "entries": [{"id": "weights", "term": "重み", "definition": definition}],
    }


@pytest.mark.parametrize("message,expected", [
    ("マルチエージェントとプロンプトエンジニアリング、タスク分解。", ["task_decomposition"]),
    ("マルチ**エージェント**を使い、別のエージェントに渡す。", ["agent"]),
    ("RAG、rag、ＲＡＧ。LLM、ｌｌｍ、人工知能、AI。", ["rag", "llm"]),
    ("パラメータとパラメーター。エンベッディングと埋め込み。", ["parameters", "embedding"]),
    ("trait RAGged email DBASE my_llm embeddingstuff", []),
    ("[参考資料](https://example.org/RAG/LLM)\n\n<div data-name='AI'>\n</div>", []),
    ("[RAG](https://example.org)から資料を探す。", ["rag"]),
    ("検索拡張生成を使って回答する。", ["rag"]),
    ("ここには登録されていない言葉だけを書きます。", []),
    ("### 永続化\n\n情報を残す。\n\n### 推論\n\n回答を作る。", ["persistence", "inference"]),
])
def test_visible_text_matching(message, expected):
    assert ids(message) == expected


@pytest.mark.parametrize("invalid", ["version", "entries", "duplicate_id", "duplicate_alias", "normalized_alias", "definition", "alias", "sources"])
def test_invalid_dictionary_is_rejected(invalid):
    content = yaml.safe_load(GLOSSARY_PATH.read_text(encoding="utf-8"))
    if invalid == "version":
        content["version"] = "unknown"
    elif invalid == "entries":
        content["entries"] = []
    elif invalid == "duplicate_id":
        content["entries"][1]["id"] = content["entries"][0]["id"]
    elif invalid == "duplicate_alias":
        content["entries"][1]["aliases"].append("重み")
    elif invalid == "normalized_alias":
        content["entries"][0]["aliases"].append("ｌｌｍ")
    elif invalid == "definition":
        content["entries"][0]["definition"] = " "
    elif invalid == "alias":
        content["entries"][0]["aliases"] = [""]
    else:
        content["entries"][0]["sources"] = []
    with pytest.raises(ValueError):
        parse_learning_glossary(content)


def test_fingerprint_covers_definition_changes():
    content = yaml.safe_load(GLOSSARY_PATH.read_text(encoding="utf-8"))
    before = parse_learning_glossary(content)
    changed = deepcopy(content)
    changed["entries"][0]["definition"] += "改訂"
    assert parse_learning_glossary(changed).sha256 != before.sha256
    assert parse_learning_glossary(dict(reversed(list(content.items())))).sha256 == before.sha256


def test_invalid_dictionary_stops_startup_before_database_writes(monkeypatch):
    import app.main as main

    def invalid():
        raise ValueError("invalid glossary")

    def no_db():
        pytest.fail("database initialization must not precede glossary validation")

    monkeypatch.setattr(main, "load_learning_glossary", invalid)
    monkeypatch.setattr(main, "init_db", no_db)
    with pytest.raises(ValueError, match="invalid glossary"):
        with TestClient(app):
            pass


@pytest.fixture
def restore_settings():
    settings = {"option-order": client.get("/api/admin/option-order").json()["mode"]}
    yield
    for name, mode in settings.items():
        client.put(f"/api/admin/{name}", json={"mode": mode})


def start_learning(group, research_code=None, labels="DEF"):
    client.put("/api/admin/option-order", json={"mode": "debug_fixed"})
    research_code = research_code or new_research_code()
    participant_response = client.post("/api/participants", json={"assignment_code": group, "consent_checked": True, "research_code": research_code})
    assert participant_response.status_code == 200, participant_response.text
    pid = participant_response.json()["participant_id"]
    complete_presurvey(client, pid)
    questions_response = client.get(f"/api/experiment/{pid}/pretest")
    assert questions_response.status_code == 200, questions_response.text
    questions = questions_response.json()["questions"]
    assert all(question["glossary"]["version"] == GLOSSARY_VERSION for question in questions)
    for question in questions:
        role = "M1" if question["term_slug"] == "llm_knowledge" else None
        selected = select_roles(question, [role])
        saved = client.post("/api/attempts", json={"participant_id": pid, "question_id": question["question_id"], "selected_option_ids": selected})
        assert saved.status_code == 200, saved.text
    acknowledge_all_question_reviews(client, pid, "pretest")
    assert client.post(f"/api/participants/{pid}/diagnose-pretest").status_code == 200
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "llm_knowledge"}).json()
    url = f"/api/tutor-sessions/{session['tutor_session_id']}/turns"
    response = client.post(url, json={}, headers={"Idempotency-Key": "glossary-material"})
    assert response.status_code == 200, response.text
    return pid, url, response.json()


@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("labels", ["ABC", "DEF"])
def test_material_and_feedback_snapshots_replays_and_audit(group, labels, restore_settings, monkeypatch):
    pid, url, turn = start_learning(group, labels=labels)
    expected_material = glossary_snapshot(turn["tutor_message"])
    assert turn["glossary"] == public_glossary(expected_material)
    assert turn["glossary"]["entries"]
    assert "glossary" not in turn["practice_question"]
    with SessionLocal() as db:
        p = db.get(Participant, pid)
        assert p.experiment_spec_version == CURRENT_EXPERIMENT_SPEC_VERSION == 51
        assert p.protocol_id == CURRENT_PROTOCOL_ID == "experiment-plan-2026-11-12-posttest-material-amount-wording-v1"
        assert p.learning_material_glossary_mode == "integrated_material"
        stored = db.get(TutorTurn, turn["turn_id"])
        assert stored.diagnosis_json["material_glossary"] == expected_material
        length_metrics = stored.diagnosis_json["material_length_metrics"]
        assert length_metrics == {"character_count": len(stored.tutor_message), "target_character_count": 800}
        metrics = stored.diagnosis_json["tutoring_output_metrics"]
        assert metrics["target_character_count"] == 800
        assert "min_character_count" not in metrics
        assert "max_character_count" not in metrics
    assert turn["show_material_glossary"] is False

    def no_recompute(_text):
        pytest.fail("saved glossary snapshots must not be recomputed")

    with monkeypatch.context() as scoped:
        scoped.setattr(experiment, "glossary_snapshot", no_recompute)
        for key in ("glossary-material", "new-material-key"):
            replay = client.post(url, json={}, headers={"Idempotency-Key": key})
            assert replay.status_code == 200, replay.text
            assert replay.json() == turn

    respond_url = f"/api/tutor-turns/{turn['turn_id']}/respond"
    selected = [select_roles(q, [None if labels == "ABC" else "M1"])[0] for q in turn["practice_question"]["questions"]]
    body = {"selected_option_ids": selected}
    response = client.post(respond_url, json=body, headers={"Idempotency-Key": "glossary-feedback"})
    assert response.status_code == 200, response.text
    feedback = response.json()
    assert feedback["is_sufficient"] == (labels == "ABC")
    expected_feedback = glossary_snapshot(feedback["feedback"])
    assert feedback["glossary"] == public_glossary(expected_feedback)
    with monkeypatch.context() as scoped:
        scoped.setattr(experiment, "glossary_snapshot", no_recompute)
        assert client.post(respond_url, json=body, headers={"Idempotency-Key": "glossary-feedback"}).json() == feedback
    with SessionLocal() as db:
        stored = db.get(TutorTurn, turn["turn_id"])
        assert stored.tutor_message == turn["tutor_message"]
        assert stored.ai_feedback == feedback["feedback"]
        assert stored.grading_json["feedback_glossary"] == expected_feedback
        calls = db.query(AICallLog).filter(AICallLog.request_payload["participant_id"].as_string() == pid).all()
        material_call = next(call for call in calls if call.purpose == "generate_tutoring_turn")
        assert material_call.request_payload["input_projection"]["glossary_reference"]["version"] == GLOSSARY_VERSION
    logs = client.get(f"/api/admin/participants/{pid}/logs").json()
    row = next(row for session in logs["tutor_sessions"] for row in session["turns"] if row["tutor_turn_id"] == turn["turn_id"])
    assert row["material_glossary"] == expected_material
    assert row["feedback_glossary"] == expected_feedback
    exported = client.get(f"/api/admin/participants/{pid}/logs.csv")
    reader = csv.DictReader(exported.text.splitlines())
    assert reader.fieldnames == experiment.LOG_CSV_COLUMNS
    answer = next(row for row in reader if row["record_type"] == "answer" and json.loads(row["value_json"]).get("source_id") == turn["turn_id"])
    assert json.loads(answer["value_json"])["material_glossary"] == expected_material


def test_integrated_material_mode_is_common_to_both_groups_and_snapshotted(restore_settings):
    projections = {}
    participant_ids = []
    for group in ("A", "B"):
        pid, _url, turn = start_learning(group, research_code=new_research_code())
        participant_ids.append(pid)
        assert turn["show_material_glossary"] is False
        assert turn["glossary"]["entries"]
        with SessionLocal() as db:
            participant = db.get(Participant, pid)
            assert participant.learning_material_glossary_mode == "integrated_material"
            call = (
                db.query(AICallLog)
                .filter(AICallLog.request_payload["participant_id"].as_string() == pid)
                .filter_by(purpose="generate_tutoring_turn")
                .one()
            )
            stored_turn = db.get(TutorTurn, turn["turn_id"])
            length_metrics = stored_turn.diagnosis_json["material_length_metrics"]
            assert length_metrics == {"character_count": len(stored_turn.tutor_message), "target_character_count": 800}
            metrics = stored_turn.diagnosis_json["tutoring_output_metrics"]
            assert metrics["target_character_count"] == 800
            assert "min_character_count" not in metrics
            assert "max_character_count" not in metrics
            assert call.response_payload["output_metrics"]["target_character_count"] == 800
            assert "min_character_count" not in call.response_payload["output_metrics"]
            assert "max_character_count" not in call.response_payload["output_metrics"]
            projection = call.request_payload["input_projection"]
            assert projection["glossary_reference"]["version"] == GLOSSARY_VERSION
            assert len(projection["glossary_reference"]["entries"]) == 17
            if group == "A":
                assert "diagnostic_evidence" in projection
                assert "misconception_taxonomy" in projection
            else:
                assert "diagnostic_evidence" not in projection
                assert "misconception_taxonomy" not in projection
            projections[group] = projection

    common_keys = ("term", "component_terms", "rag_context", "interaction_history", "glossary_reference")
    assert {key: projections["A"][key] for key in common_keys} == {key: projections["B"][key] for key in common_keys}
    for pid in participant_ids:
        logs = client.get(f"/api/admin/participants/{pid}/logs").json()
        assert logs["participant"]["learning_material_glossary_mode"] == "integrated_material"
    csv_response = client.get("/api/admin/export/participants.csv")
    assert "learning_material_glossary_mode" in csv_response.text.splitlines()[0]
