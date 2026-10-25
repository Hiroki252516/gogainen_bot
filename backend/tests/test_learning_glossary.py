from copy import deepcopy
import csv
import json

import pytest
import yaml
from fastapi.testclient import TestClient

from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID
from app.db.session import SessionLocal
from app.main import app
from app.models import AICallLog, Participant, TutorTurn
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
    assert len(glossary.entries) == 25
    assert glossary.version == GLOSSARY_VERSION
    snapshot = glossary_snapshot("## 重み\n\n**モデル**のパラメータと重みを確認する。")
    assert [entry["id"] for entry in snapshot["entries"]] == ["weights", "model", "parameters"]
    assert len(snapshot["dictionary_sha256"]) == 64
    public = public_glossary(snapshot)
    assert set(public) == {"version", "entries"}
    assert all(set(entry) == {"id", "term", "definition"} for entry in public["entries"])
    assert public_glossary(None) is None
    public["entries"][0]["definition"] = "changed"
    assert snapshot["entries"][0]["definition"] != "changed"


@pytest.mark.parametrize("message,expected", [
    ("マルチエージェントとプロンプトエンジニアリング、タスク分解。", ["multi_agent", "prompt_engineering", "task_decomposition"]),
    ("マルチ**エージェント**を使い、別のエージェントに渡す。", ["multi_agent", "agent"]),
    ("RAG、rag、ＲＡＧ。LLM、ｌｌｍ、人工知能、AI。", ["rag", "llm", "ai"]),
    ("パラメータとパラメーター。エンベッディングと埋め込み。", ["parameters", "embedding"]),
    ("trait RAGged email DBASE my_llm embeddingstuff", []),
    ("[参考資料](https://example.org/RAG/LLM)\n\n<div data-name='AI'>\n</div>", []),
    ("[RAG](https://example.org)から資料を探す。", ["rag"]),
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
        content["entries"][0]["aliases"].append("ｒａｇ")
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
    settings = {name: client.get(f"/api/admin/{name}").json()["mode"] for name in ("question-set", "option-order")}
    yield
    for name, mode in settings.items():
        client.put(f"/api/admin/{name}", json={"mode": mode})


def start_learning(mode, group):
    client.put("/api/admin/question-set", json={"mode": mode})
    client.put("/api/admin/option-order", json={"mode": "debug_fixed"})
    participant = client.post("/api/participants", json={"assignment_code": group, "consent_checked": True, "student_number": "GLOSSARY-TEST"}).json()
    pid = participant["participant_id"]
    questions = client.get(f"/api/experiment/{pid}/pretest").json()["questions"]
    assert all("glossary" not in question for question in questions)
    for question in questions:
        labels = "DEF" if question["term_slug"] == "llm_knowledge" else "ABC"
        selected = [option["option_id"] for option in question["options"] if option["label"] in labels]
        saved = client.post("/api/attempts", json={"participant_id": pid, "question_id": question["question_id"], "selected_option_ids": selected})
        assert saved.status_code == 200, saved.text
    assert client.post(f"/api/participants/{pid}/diagnose-pretest").status_code == 200
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "llm_knowledge"}).json()
    url = f"/api/tutor-sessions/{session['tutor_session_id']}/turns"
    response = client.post(url, json={}, headers={"Idempotency-Key": "glossary-material"})
    assert response.status_code == 200, response.text
    return pid, url, response.json()


@pytest.mark.parametrize("mode", ["standard", "easy"])
@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("labels", ["ABC", "DEF"])
def test_material_and_feedback_snapshots_replays_and_audit(mode, group, labels, restore_settings, monkeypatch):
    pid, url, turn = start_learning(mode, group)
    expected_material = glossary_snapshot(turn["tutor_message"])
    assert turn["glossary"] == public_glossary(expected_material)
    assert turn["glossary"]["entries"]
    assert "glossary" not in turn["practice_question"]
    with SessionLocal() as db:
        p = db.get(Participant, pid)
        assert p.experiment_spec_version == CURRENT_EXPERIMENT_SPEC_VERSION == 8
        assert p.protocol_id == CURRENT_PROTOCOL_ID == "experiment-plan-2026-10-25-glossary-v1"
        stored = db.get(TutorTurn, turn["turn_id"])
        assert stored.diagnosis_json["material_glossary"] == expected_material
        assert 600 <= len(stored.tutor_message) <= 800

    def no_recompute(_text):
        pytest.fail("saved glossary snapshots must not be recomputed")

    with monkeypatch.context() as scoped:
        scoped.setattr(experiment, "glossary_snapshot", no_recompute)
        for key in ("glossary-material", "new-material-key"):
            replay = client.post(url, json={}, headers={"Idempotency-Key": key})
            assert replay.status_code == 200, replay.text
            assert replay.json() == turn

    respond_url = f"/api/tutor-turns/{turn['turn_id']}/respond"
    body = {"selected_option_ids": [option["option_id"] for option in turn["practice_question"]["options"] if option["label"] in labels]}
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
        for call in calls:
            assert "glossary" not in json.dumps(call.request_payload["input_projection"], ensure_ascii=False)
    logs = client.get(f"/api/admin/participants/{pid}/logs").json()
    row = next(row for session in logs["tutor_sessions"] for row in session["turns"] if row["tutor_turn_id"] == turn["turn_id"])
    assert row["material_glossary"] == expected_material
    assert row["feedback_glossary"] == expected_feedback
    exported = client.get(f"/api/admin/participants/{pid}/logs.csv")
    reader = csv.DictReader(exported.text.splitlines())
    assert reader.fieldnames == experiment.LOG_CSV_COLUMNS
    answer = next(row for row in reader if row["record_type"] == "answer" and json.loads(row["value_json"]).get("source_id") == turn["turn_id"])
    assert json.loads(answer["value_json"])["material_glossary"] == expected_material


def test_old_v7_question_lookup_uses_its_own_bank_without_snapshot(restore_settings):
    pid, _, _ = start_learning("easy", "B")
    from app.models import Term
    with SessionLocal() as db:
        p = db.get(Participant, pid)
        p.experiment_spec_version = 7
        p.protocol_id = "experiment-plan-2026-10-24-easy-version-v1"
        db.commit()
        term = db.query(Term).filter_by(slug="llm_knowledge").one()
        question = experiment._test_result_question(db, p, term, "retest_2", "retest")
        assert question.variant_key == "retest_v2"
        assert question.construct_key.endswith("scenario-actions-easy-v1")
