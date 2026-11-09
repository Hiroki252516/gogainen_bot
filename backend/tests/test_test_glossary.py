from copy import deepcopy
import csv
import json

import pytest
import yaml
from admin_client import AuthenticatedTestClient as TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID
from app.core.question_sets import HISTORICAL_ASSESSMENT_BANK_VERSIONS
from app.db import session as database
from app.db.session import SessionLocal
from app.main import app
from app.models import Attempt, Base, Participant, Question, Term, TutorSession, TutorTurn
from app.seed.seed_questions import seed_database
from app.services import experiment
from app.services.interaction_history import _test_record
from app.services.learning_glossary import (
    GLOSSARY_PATH, GLOSSARY_VERSION, glossary_snapshot, parse_learning_glossary, public_glossary,
)
from split_api_support import complete_presurvey


client = TestClient(app)
REMOVED_IDS = {"ai", "pretraining", "fine_tuning", "prompt_engineering", "rag", "database", "multi_agent", "task", "memory_process"}
CURRENTLY_EXCLUDED_IDS = REMOVED_IDS - {"rag"}


def test_current_dictionary_only_removes_requested_entries_and_preserves_old_source():
    v1_path = GLOSSARY_PATH.with_name("learning_glossary_v1.yml")
    v2_path = GLOSSARY_PATH.with_name("learning_glossary_v2.yml")
    v3_path = GLOSSARY_PATH.with_name("learning_glossary_v3.yml")
    old = yaml.safe_load(v1_path.read_text(encoding="utf-8"))
    v2 = yaml.safe_load(v2_path.read_text(encoding="utf-8"))
    v3 = yaml.safe_load(v3_path.read_text(encoding="utf-8"))
    current = yaml.safe_load(GLOSSARY_PATH.read_text(encoding="utf-8"))
    assert old["version"] == "learning-glossary-v1" and len(old["entries"]) == 25
    assert v2["version"] == "learning-glossary-v2"
    assert v2["entries"] == [entry for entry in old["entries"] if entry["id"] not in REMOVED_IDS]
    assert v3["version"] == "learning-glossary-v3"
    expected_v3 = deepcopy(v2)
    expected_v3["version"] = "learning-glossary-v3"
    updates = {
        "weights": "AIが文章を作るための計算に使う数値です。学習によってこの数値が調整されると、AIが選ぶ言葉や回答の仕方が変わることがある",
        "additional_training": "既に学習したAIに、新しい学習用データを使ってさらに学習させ、回答の仕方などを目的に合わせて調整すること",
        "agent": "与えられた目的に向けて、状況を見ながら次の行動を判断して進めるAI",
        "model": "AI本体を指す",
    }
    for entry in expected_v3["entries"]:
        if entry["id"] in updates:
            entry["definition"] = updates[entry["id"]]
    assert v3 == expected_v3
    expected_v4 = deepcopy(v3)
    expected_v4["version"] = "learning-glossary-v4"
    expected_v4["entries"].append(deepcopy(next(entry for entry in old["entries"] if entry["id"] == "rag")))
    assert current == expected_v4
    assert current["version"] == GLOSSARY_VERSION == "learning-glossary-v4"
    for entry in old["entries"]:
        if entry["id"] in REMOVED_IDS:
            for alias in entry["aliases"]:
                expected_ids = ["rag"] if entry["id"] == "rag" else []
                assert [item["id"] for item in glossary_snapshot(alias)["entries"]] == expected_ids, alias
    old_snapshot = {"version": old["version"], "dictionary_sha256": "old", "entries": [
        {key: entry[key] for key in ("id", "term", "definition")} for entry in old["entries"]
    ]}
    assert len(public_glossary(old_snapshot)["entries"]) == 25
    assert old_snapshot["dictionary_sha256"] == "old"


@pytest.mark.parametrize("message,expected", [
    ("マルチ・エージェントとプロンプトエンジニアリング", []),
    ("プロンプトエンジニアリングとプロンプト、マルチエージェントとエージェント", ["prompt", "agent"]),
    ("マルチ**エージェント**とプロンプト**エンジニアリング**", []),
    ("タスクとタスク分解、LLMと重み", ["task_decomposition", "llm", "weights"]),
    ("AI、事前訓練、fine-tuning、RAG、DB、記憶機能", ["rag"]),
])
def test_excluded_compounds_do_not_create_shorter_annotations(message, expected):
    assert [entry["id"] for entry in glossary_snapshot(message)["entries"]] == expected


@pytest.mark.parametrize("invalid", [None, "text", [""], [" マルチエージェント"], ["重み"], ["multi-agent", "ＭＵＬＴＩ-ＡＧＥＮＴ"]])
def test_invalid_excluded_aliases_fail_validation(invalid):
    content = yaml.safe_load(GLOSSARY_PATH.read_text(encoding="utf-8"))
    content["excluded_aliases"] = invalid
    with pytest.raises(ValueError):
        parse_learning_glossary(content)


def test_exclusions_are_part_of_dictionary_fingerprint():
    content = yaml.safe_load(GLOSSARY_PATH.read_text(encoding="utf-8"))
    changed = deepcopy(content)
    changed["excluded_aliases"].append("別の除外語")
    assert parse_learning_glossary(content).sha256 != parse_learning_glossary(changed).sha256


@pytest.fixture
def restore_settings():
    before = {key: client.get(f"/api/admin/{key}").json()["mode"] for key in ("option-order",)}
    yield
    for key, mode in before.items():
        client.put(f"/api/admin/{key}", json={"mode": mode})


@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("phase,completed", [("pretest", 0), ("retest", 0), ("retest", 1), ("final_test", 0)])
def test_test_glossary_uses_all_visible_text_and_is_saved_replayed_and_exported(layout, group, phase, completed, restore_settings, monkeypatch):
    client.put("/api/admin/option-order", json={"mode": layout})
    registration = client.post("/api/registrations", json={"assignment_code": group, "consent_checked": True, "student_number": "GLOSSARY-SYNTHETIC"})
    assert registration.status_code == 200, registration.text
    pid = registration.json()["participant_id"]
    complete_presurvey(client, pid)
    with SessionLocal() as db:
        participant = db.get(Participant, pid)
        assert participant.experiment_spec_version == CURRENT_EXPERIMENT_SPEC_VERSION == 46
        assert participant.protocol_id == CURRENT_PROTOCOL_ID == "experiment-plan-2026-11-09-four-topic-default-two-retests-v1"
        participant.current_step = phase
        participant.retest_cycles_completed = completed
        db.commit()
    path = f"/api/experiment/{pid}/{phase.replace('_', '-')}"
    response = client.get(path)
    assert response.status_code == 200, response.text
    questions = response.json()["questions"]
    assert len(questions) == 3
    assert client.get(path).json() == response.json()
    for question in questions:
        expected = experiment._test_glossary(question["term_label"], question["body"], question["options"])
        assert question["glossary"] == public_glossary(expected)
        assert CURRENTLY_EXCLUDED_IDS.isdisjoint(entry["id"] for entry in expected["entries"])
        assert set(question["glossary"]) == {"version", "entries"}
        assert all(set(entry) == {"id", "term", "definition"} for entry in question["glossary"]["entries"])
        assert all(set(option) == {"option_id", "label", "body", "exclusive"} for option in question["options"])
    with SessionLocal() as db:
        assert db.query(Attempt).filter_by(participant_id=pid).count() == 0
    question = questions[0]
    expected = experiment._test_glossary(question["term_label"], question["body"], question["options"])
    assert expected["entries"]
    body = {"participant_id": pid, "question_id": question["question_id"], "phase": phase,
            "selected_option_ids": [option["option_id"] for option in question["options"] if option["exclusive"]]}
    saved = client.post("/api/attempts", json=body, headers={"Idempotency-Key": "test-glossary"})
    assert saved.status_code == 200, saved.text
    original = experiment._test_glossary

    def no_recompute(term_label, message, options):
        assert message != question["body"], "submitted glossary must use its saved snapshot"
        return original(term_label, message, options)

    monkeypatch.setattr(experiment, "_test_glossary", no_recompute)
    assert client.post("/api/attempts", json=body, headers={"Idempotency-Key": "test-glossary"}).json() == saved.json()
    restored = client.get(path).json()["questions"][0]
    assert restored["glossary"] == question["glossary"] and restored["answer_status"] == "submitted"
    with SessionLocal() as db:
        attempt = db.query(Attempt).filter_by(participant_id=pid).one()
        assert attempt.glossary_snapshot == expected
        assert attempt.question_body_snapshot == question["body"]
        assert attempt.option_order_snapshot == question["options"]
        assert "glossary" not in json.dumps(_test_record(db, attempt), ensure_ascii=False)
    logs = client.get(f"/api/admin/participants/{pid}/logs").json()
    assert logs["attempts"][0]["test_glossary"] == expected
    exported = client.get(f"/api/admin/participants/{pid}/logs.csv")
    reader = csv.DictReader(exported.text.splitlines())
    assert reader.fieldnames == experiment.LOG_CSV_COLUMNS
    row = next(row for row in reader if row["record_type"] == "answer")
    assert json.loads(row["value_json"])["test_glossary"] == expected


def test_glossary_includes_unselected_options_and_deduplicates_in_display_order():
    snapshot = experiment._test_glossary("LLM", "モデルで回答する。", [
        {"body": "プロンプトに指示する。"}, {"body": "重みとモデルを調整する。"}, {"body": "AIとRAG。"},
    ])
    assert [entry["id"] for entry in snapshot["entries"]] == ["llm", "model", "prompt", "weights", "rag"]
    assert experiment._test_glossary("資料", "説明を読む。", [{"body": "わからない。"}])["entries"] == []


def test_v25_saved_annotations_and_result_bank_are_preserved(monkeypatch):
    old = {"version": "learning-glossary-v1", "dictionary_sha256": "historical-fingerprint", "entries": [
        {"id": "ai", "term": "AI（人工知能）", "definition": "保存当時の説明"},
    ]}
    with SessionLocal() as db:
        participant = Participant(display_code="OLD-GLOSSARY-V25", group_condition="control", current_step="learning",
                                  experiment_spec_version=25, protocol_id="experiment-plan-2026-10-27-round2-revision-v1",
                                  learning_content_version=15)
        db.add(participant)
        db.flush()
        pid = participant.id
        term = db.query(Term).filter_by(slug="llm_knowledge").one()
        session = TutorSession(participant_id=pid, term_id=term.id, group_condition="control", session_index=1)
        db.add(session)
        db.flush()
        session_id = session.id
        turn = TutorTurn(tutor_session_id=session.id, turn_index=1, teaching_strategy="general_explanation", tutor_message="保存済み教材",
                         ai_feedback="保存済み解説", diagnosis_json={"material_glossary": old}, grading_json={"feedback_glossary": old})
        db.add(turn)
        db.commit()
        from historical_bank_support import seed_scenario_bank
        seed_scenario_bank(db)
        question = experiment._test_result_question(db, participant, term, "retest_2", "retest")
        assert question.construct_key.endswith("scenario-actions-v9") and question.variant_key == "retest_v2"

    def no_recompute(_text):
        pytest.fail("historical annotations must not be recomputed")

    monkeypatch.setattr(experiment, "glossary_snapshot", no_recompute)
    assert client.get(f"/api/experiment/{pid}/pretest").status_code == 409
    logs = client.get(f"/api/admin/participants/{pid}/logs").json()
    stored = logs["tutor_sessions"][0]["turns"][0]
    assert stored["material_glossary"] == stored["feedback_glossary"] == old
    with SessionLocal() as db:
        assert db.get(Participant, pid).experiment_spec_version == 25
        assert db.query(TutorTurn).filter_by(tutor_session_id=session_id).one().diagnosis_json["material_glossary"] == old


def test_nullable_migration_and_repeated_seed_preserve_v25_records(tmp_path, monkeypatch):
    isolated = create_engine(f"sqlite:///{tmp_path / 'glossary-migration.db'}")
    monkeypatch.setattr(database, "engine", isolated)
    Base.metadata.create_all(isolated)
    with Session(isolated) as db:
        seed_database(db)
        participant = Participant(display_code="V25", group_condition="control", current_step="pretest", experiment_spec_version=25,
                                  protocol_id="experiment-plan-2026-10-27-round2-revision-v1", learning_content_version=15)
        question = db.query(Question).filter_by(phase="pretest", is_active=True).first()
        db.add(participant)
        db.flush()
        db.add(Attempt(participant_id=participant.id, term_id=question.term_id, question_id=question.id, phase="pretest", question_body_snapshot="当時の問題"))
        db.commit()
    with isolated.begin() as connection:
        connection.execute(text("ALTER TABLE attempts DROP COLUMN glossary_snapshot"))
        before = dict(connection.execute(text("SELECT * FROM attempts")).mappings().one())
    for _ in range(2):
        database.init_db()
        with Session(isolated) as db:
            seed_database(db)
            assert db.query(Question).filter_by(is_active=True).count() == 39
    assert next(column for column in inspect(isolated).get_columns("attempts") if column["name"] == "glossary_snapshot")["nullable"]
    with isolated.connect() as connection:
        after = dict(connection.execute(text("SELECT * FROM attempts")).mappings().one())
        assert after.pop("glossary_snapshot") is None
        assert after == before
    assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[25] == {"standard": "scenario-actions-v9"}
    isolated.dispose()
