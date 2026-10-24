import asyncio
import csv
import hashlib
import json
from collections import Counter
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.ai.codex_app_server_backend import CodexAppServerBackend
from app.ai.interaction_history import COMMON_INPUT_KEYS, project_model_payload
from app.ai.mock_backend import MockAIBackend
from app.core.question_sets import ASSESSMENT_BANK_VERSIONS, LEARNING_CONTENT_VERSIONS, assessment_construct_key
from app.db import session as database
from app.db.session import get_db
from app.main import app
from app.models import Attempt, Base, Participant, Question, QuestionOption, RuntimeSetting, Term, TutorSession, TutorTurn
from app.seed.content_loader import ACTIVE_TERM_SLUGS, CONTENT_PATH, LEARNING_V3_CONTENT_PATH, assessment_question_spec, learning_question_spec, load_content, load_learning_easy_content, _validate_assessment_variant
from app.seed.seed_questions import seed_database
from app.services import experiment, prefetch
from app.services.interaction_history import build_interaction_history
from app.services.option_order import assessment_bank_index, learning_bank_index, present_options, option_role


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'question-sets.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    with factory() as db:
        seed_database(db)
    def dependency():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = dependency
    monkeypatch.setattr(experiment, "SessionLocal", factory)
    monkeypatch.setattr(prefetch, "SessionLocal", factory)
    try:
        yield TestClient(app), factory, engine
    finally:
        prefetch.wait_for_prefetch_tasks()
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def create(client, mode="standard", layout="debug_fixed", group="A"):
    assert client.put("/api/admin/question-set", json={"mode": mode}).status_code == 200
    assert client.put("/api/admin/option-order", json={"mode": layout}).status_code == 200
    response = client.post("/api/participants", json={"assignment_code": group, "consent_checked": True, "student_number": "TEST-EASY-VERSION"})
    assert response.status_code == 200, response.text
    return response.json()["participant_id"]


def role_ids(question, spec, role):
    bodies = {o["body"] for o in spec["options"] if option_role(o) == role}
    return [o["option_id"] for o in question["options"] if o["body"] in bodies]


def submit(client, pid, phase, mode, role="M1", index=1):
    path = "final-test" if phase == "final_test" else phase
    response = client.get(f"/api/experiment/{pid}/{path}")
    assert response.status_code == 200, response.text
    questions = response.json()["questions"]
    for q in questions:
        spec = assessment_question_spec(q["term_slug"], phase, index, mode)
        assert q["body"] == spec["body"]
        result = client.post("/api/attempts", json={"participant_id": pid, "question_id": q["question_id"], "phase": phase, "selected_option_ids": role_ids(q, spec, role)}, headers={"Idempotency-Key": f"{phase}-{index}-{q['term_slug']}"})
        assert result.status_code == 200, result.text
    endpoint = "diagnose-pretest" if phase == "pretest" else "score-final-test" if phase == "final_test" else "score-retest"
    scored = client.post(f"/api/participants/{pid}/{endpoint}")
    assert scored.status_code == 200, scored.text
    return questions, scored.json()


def test_normal_files_are_unchanged_and_easy_banks_validate():
    assert hashlib.sha256(CONTENT_PATH.read_bytes()).hexdigest() == "916f2b89b731b7a658f50b5a8e5e42ed831b00d4d2471f34c11def96cb469ede"
    assert hashlib.sha256(LEARNING_V3_CONTENT_PATH.read_bytes()).hexdigest() == "2ae5b8483016db955d5fda4cc7aacca5e58c8f5bb070d51eb08fc6cd6022f156"
    bank = load_content("easy")
    learning = load_learning_easy_content()
    all_bodies = set()
    for mode in ("standard", "easy"):
        role_counts = {r: Counter() for r in ("correct", "M1", "M3")}
        for term in ACTIVE_TERM_SLUGS:
            for phase, index in (("pretest", 1), ("retest", 1), ("retest", 2)):
                spec = assessment_question_spec(term, phase, index, mode)
                assert len(spec["options"]) == 10
                assert Counter(map(option_role, spec["options"])) == {"correct": 3, "M1": 3, "M3": 3, "unknown": 1}
                displayed = present_options(spec["options"], mode="randomized", bank="assessment", item_index=assessment_bank_index(term, phase, spec["variant_key"]))
                for option in displayed:
                    role = next(option_role(o) for o in spec["options"] if o["body"] == option["body"])
                    if role != "unknown":
                        role_counts[role][option["label"]] += 1
                assert displayed[-1]["exclusive"] and displayed[-1]["label"] == "J"
                assert spec["body"] not in all_bodies
                all_bodies.add(spec["body"])
            for index in (1, 2, 3):
                spec = learning_question_spec(term, "conceptual_change", index, mode)
                assert spec["_content_version"] == LEARNING_CONTENT_VERSIONS[mode]
                assert spec["body"] not in all_bodies
                all_bodies.add(spec["body"])
                order = present_options(spec["options"], mode="randomized", bank="learning", item_index=learning_bank_index(term, "conceptual_change", index))
                repeated = present_options(spec["options"], mode="randomized", bank="learning", item_index=learning_bank_index(term, "conceptual_change", index))
                assert [(o["label"], o["body"]) for o in order] == [(o["label"], o["body"]) for o in repeated]
        for counts in role_counts.values():
            assert max(counts.values()) - min(counts.values()) <= 1
    for term in bank["terms"]:
        assert set(bank["teaching_targets"][term["slug"]]) == set("DEFGHI")
        for variants in term["questions"].values():
            for variant in variants:
                assert set(variant["choice_rationales"]) == set("DEFGHI")
        for variant in learning["terms"][term["slug"]]["variants"]:
            assert len(set(variant["choice_rationales"].values())) == 6
            lengths = [len(t) for texts in variant["choices"].values() for t in texts]
            assert max(lengths) <= 1.8 * min(lengths)
            assert max(lengths) - min(lengths) <= 32
    invalid = deepcopy(bank["terms"][0]["questions"]["pretest"][0])
    invalid["choice_rationales"].pop("D")
    with pytest.raises(ValueError, match="rationale"):
        _validate_assessment_variant("llm_knowledge", "pretest", invalid, "easy")


@pytest.mark.parametrize("mode", ["standard", "easy"])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
@pytest.mark.parametrize("group", ["A", "B"])
def test_fixed_mode_scoring_review_and_no_cross_bank_fallback(isolated, mode, layout, group):
    client, factory, _ = isolated
    pid = create(client, mode, layout, group)
    questions = client.get(f"/api/experiment/{pid}/pretest").json()["questions"]
    other = "standard" if mode == "easy" else "easy"
    client.put("/api/admin/question-set", json={"mode": other})
    client.put("/api/admin/option-order", json={"mode": "randomized" if layout == "debug_fixed" else "debug_fixed"})
    assert questions == client.get(f"/api/experiment/{pid}/pretest").json()["questions"]
    with factory() as db:
        participant = db.get(Participant, pid)
        assert participant.question_set_mode == mode
        assert participant.learning_content_version == LEARNING_CONTENT_VERSIONS[mode]
        foreign = db.query(Question).filter_by(phase="pretest", construct_key=assessment_construct_key("llm_knowledge", "pretest", other)).one()
        foreign_id = foreign.id
    assert client.post("/api/attempts", json={"participant_id": pid, "question_id": foreign_id, "selected_option_ids": []}).status_code == 409
    for q in questions:
        assert set(q["options"][0]) == {"option_id", "label", "body", "exclusive"}
    questions, result = submit(client, pid, "pretest", mode, "M3")
    review = client.get(f"/api/participants/{pid}/learning-targets").json()["test_results"]
    assert all(r["is_correct"] is False for r in review["results"])
    assert [r["question_body"] for r in review["results"]] == [q["body"] for q in questions]
    with factory() as db:
        assert {a.misconception_type for a in db.query(Attempt).filter_by(participant_id=pid)} == {"M3"}
        before = {q.id: q.body for q in db.query(Question)}
        seed_database(db)
        seed_database(db)
        assert before == {q.id: q.body for q in db.query(Question)}
        for q in questions:
            attempt = db.query(Attempt).filter_by(participant_id=pid, question_id=q["question_id"]).one()
            assert attempt.option_order_snapshot == q["options"]
        first = db.get(Question, questions[0]["question_id"])
        first.is_active = False
        db.commit()
    assert client.get(f"/api/experiment/{pid}/pretest").status_code == 409  # closed phase
    with factory() as db:
        p = db.get(Participant, pid)
        p.current_step = "pretest"
        db.commit()
    assert client.get(f"/api/experiment/{pid}/pretest").status_code == 503


@pytest.mark.parametrize("mode", ["standard", "easy"])
@pytest.mark.parametrize("initial_perfect", [False, True])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
def test_three_test_cap_with_snapshot_history_and_replay(isolated, mode, initial_perfect, layout):
    client, factory, _ = isolated
    pid = create(client, mode, layout)
    baseline, _ = submit(client, pid, "pretest", mode, "correct" if initial_perfect else "M1")
    phase = "final_test" if initial_perfect else "retest"
    first, first_result = submit(client, pid, phase, mode, "unknown")
    assert first_result["post_pretest_tests_completed"] == 1
    second, result = submit(client, pid, "retest", mode, "M1", 2)
    assert result["post_pretest_tests_completed"] == 2
    assert result["next_step"] == "survey"
    assert result["post_pretest_test_limit"] == 2
    assert len({q["body"] for qs in (baseline, first, second) for q in qs}) == 9
    assert client.post(f"/api/participants/{pid}/score-retest").status_code == 409
    with factory() as db:
        assert db.query(Attempt).filter_by(participant_id=pid).count() == 9
        assert db.query(Attempt).filter_by(participant_id=pid, is_correct=False).count() >= 6
        attempt = db.query(Attempt).filter_by(participant_id=pid, question_id=baseline[0]["question_id"]).one()
        attempt.question_body_snapshot = None
        attempt.option_order_snapshot = None
        db.commit()
        history = build_interaction_history(db, pid, attempt.term_id)
        assert history[0]["question_body"] == baseline[0]["body"]
        chosen = set(attempt.selected_option_ids)
        assert history[0]["selected_options"] == [{"label": o["label"], "body": o["body"]} for o in baseline[0]["options"] if o["option_id"] in chosen]
        assert len(history) == 3 and history[1]["selected_options"] == [{"label": "J", "body": "わからない。"}]


@pytest.mark.parametrize("mode", ["standard", "easy"])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
@pytest.mark.parametrize("roles,expected", [(["correct", "correct", "correct"], None), (["correct", "M1", "M1"], "M1"), (["correct", "M1", "M3"], "M3"), (["unknown"], "unknown")])
def test_all_modes_use_role_metadata_for_mixed_answers(isolated, mode, layout, roles, expected):
    client, factory, _ = isolated
    pid = create(client, mode, layout)
    questions = client.get(f"/api/experiment/{pid}/pretest").json()["questions"]
    for q in questions:
        spec = assessment_question_spec(q["term_slug"], "pretest", mode=mode)
        ids = []
        for role in roles:
            ids.append(next(oid for oid in role_ids(q, spec, role) if oid not in ids))
        saved = client.post("/api/attempts", json={"participant_id": pid, "question_id": q["question_id"], "selected_option_ids": ids})
        assert saved.status_code == 200, saved.text
    assert client.post(f"/api/participants/{pid}/diagnose-pretest").status_code == 200
    with factory() as db:
        assert {a.misconception_type for a in db.query(Attempt).filter_by(participant_id=pid)} == {expected}
        assert {a.is_correct for a in db.query(Attempt).filter_by(participant_id=pid)} == {expected is None}


@pytest.mark.parametrize("mode", ["standard", "easy"])
@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("role", ["M1", "M3", "unknown"])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
def test_material_feedback_prefetch_and_teaching_targets_use_fixed_bank(isolated, monkeypatch, mode, group, role, layout):
    client, factory, _ = isolated
    captured = []
    for method in ("generate_tutoring_turn", "generate_correct_answer_summary", "explain_selected_distractor"):
        original = getattr(MockAIBackend, method)
        async def capture(self, payload, _method=method, _original=original):
            captured.append((_method, deepcopy(payload)))
            return await _original(self, payload)
        monkeypatch.setattr(MockAIBackend, method, capture)
    pid = create(client, mode, layout, group)
    submit(client, pid, "pretest", mode, role)
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "llm_knowledge"}).json()
    url = f"/api/tutor-sessions/{session['tutor_session_id']}/turns"
    first = client.post(url, json={})
    assert first.status_code == 200, first.text
    first = first.json()
    prefetch.wait_for_prefetch_tasks()
    spec = learning_question_spec("llm_knowledge", first["learning_stage"], 1, mode)
    assert first["practice_question"]["body"] == spec["body"]
    client.put("/api/admin/question-set", json={"mode": "standard" if mode == "easy" else "easy"})
    answered = client.post(f"/api/tutor-turns/{first['turn_id']}/respond", json={"selected_option_ids": role_ids(first["practice_question"], spec, "M3")}, headers={"Idempotency-Key": "first-learning-answer"})
    assert answered.status_code == 200, answered.text
    prefetch.wait_for_prefetch_tasks()
    second = client.post(url, json={})
    assert second.status_code == 200, second.text
    second = second.json()
    assert second["practice_question"]["body"] == spec["body"]
    good = client.post(f"/api/tutor-turns/{second['turn_id']}/respond", json={"selected_option_ids": role_ids(second["practice_question"], spec, "correct")})
    assert good.status_code == 200 and good.json()["is_sufficient"] is True, good.text
    prefetch.wait_for_prefetch_tasks()
    assert {m for m, _ in captured} == {"generate_tutoring_turn", "generate_correct_answer_summary", "explain_selected_distractor"}
    for _, payload in captured:
        projected = project_model_payload(payload, proposed=group == "A", feedback="material" in payload)
        assert (projected.get("explanation_level") == "beginner") == (mode == "easy")
        if group == "B":
            assert not set(projected) & {"pretest_targets", "diagnostic_evidence", "misconception_taxonomy", "active_misconception_type"}
        if payload.get("pretest_target"):
            target = payload["pretest_target"]
            term = next(t for t in load_content(mode)["terms"] if t["slug"] == target["term_slug"])
            assert target["observed_claim"] in term["questions"]["pretest"][0]["choices"][target["misconception_type"]]
    with factory() as db:
        turn = db.get(TutorTurn, second["turn_id"])
        assert turn.diagnosis_json["question_set_mode"] == mode
        history = turn.diagnosis_json["instruction_audit"]["actual_ai_input"]["interaction_history"]
        assert len(history) == 2
        assert history[-1]["is_correct"] is False
        assert history[-1]["question_body"] == spec["body"]
        p = db.get(Participant, pid)
        assert p.question_set_mode == mode
        assert turn.practice_question_json["learning_content_version"] == LEARNING_CONTENT_VERSIONS[mode]


@pytest.mark.parametrize("method", ["generate_tutoring_turn", "generate_correct_answer_summary", "explain_selected_distractor"])
def test_provider_prompt_beginner_instruction_is_shared_but_diagnostics_are_not(monkeypatch, method):
    backend = CodexAppServerBackend()
    prompts = []
    async def capture(purpose, prompt, schema, **kwargs):
        prompts.append(prompt)
        return {"summary": "要点", "feedback": "見直す点", "remediation_focus": "役割", "general_knowledge_supplement": None, "tutor_message": "## 用語\n説明", "teaching_strategy": "general_explanation"}
    monkeypatch.setattr(backend, "_run_structured_turn", capture)
    base = {"group_condition": "control", "term": {"label": "用語"}, "interaction_history": [], "question_body": "問題", "material": "教材", "pretest_targets": [{"corrected_claim": "PRIVATE_DIAGNOSIS"}]}
    for payload in (base, {**base, "explanation_level": "beginner"}, {**base, "explanation_level": "beginner", "pretest_targets": []}):
        asyncio.run(getattr(backend, method)(payload))
    assert prompts[1] == prompts[2] and prompts[0] != prompts[1]
    assert "知識が少ない学習者" in prompts[1] and "PRIVATE_DIAGNOSIS" not in prompts[1]
    sent = json.loads(prompts[1].split("入力JSON:\n", 1)[1])
    assert sent["explanation_level"] == "beginner"
    assert {key for key in COMMON_INPUT_KEYS if key in base}.issubset(sent)


def test_settings_and_aggregate_mode_are_independent_and_csv_denominators_match(isolated):
    client, factory, _ = isolated
    assert client.get("/api/admin/question-set").json()["mode"] == "standard"
    assert client.get("/api/admin/question-set").headers["cache-control"] == "no-store"
    assert client.put("/api/admin/question-set", json={"mode": "invalid"}).status_code == 422
    assert client.put("/api/admin/question-set", json={"mode": "easy", "extra": 1}).status_code == 422
    ids = {mode: [create(client, mode, group=g) for g in ("A", "B")] for mode in ("standard", "easy")}
    for mode, pids in ids.items():
        for pid in pids:
            submit(client, pid, "pretest", mode)
            submit(client, pid, "retest", mode, "correct")
        summary = client.get(f"/api/admin/evaluation-summary?question_set_mode={mode}")
        assert summary.status_code == 200, summary.text
        assert summary.json()["question_set_mode"] == mode
        assert [r["participant_count"] for r in summary.json()["groups"]] == [1, 1]
        for name in ("hypothesis_metrics", "hypothesis_group_summary"):
            exported = client.get(f"/api/admin/export/{name}.csv?question_set_mode={mode}")
            assert exported.status_code == 200, exported.text
            records = list(csv.DictReader(exported.text.splitlines()))
            assert records and all(json.loads(r["details_json"])["question_set_mode"] == mode for r in records)
            if name == "hypothesis_metrics":
                assert {r["participant_id"] for r in records} == set(pids)
    assert client.get("/api/admin/evaluation-summary?question_set_mode=bad").status_code == 422
    overview = client.get("/api/admin/logs/overview?question_set_mode=easy").json()
    assert {p["participant_id"] for p in overview["participants"]} == {pid for pids in ids.values() for pid in pids}
    assert {p["question_set_mode"] for p in overview["participants"]} == {"standard", "easy"}
    assert client.get("/api/admin/question-set").json()["mode"] == "easy"


def test_migration_adds_nullable_modes_without_backfilling_or_mutating_old_trials(isolated, monkeypatch):
    client, factory, engine = isolated
    pid = create(client)
    with factory() as db:
        db.execute(text("UPDATE participants SET experiment_spec_version=6, protocol_id='experiment-plan-2026-10-24-two-posttests-v1' WHERE id=:pid"), {"pid": pid})
        db.commit()
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE participants DROP COLUMN question_set_mode"))
        conn.execute(text("ALTER TABLE runtime_settings DROP COLUMN question_set_mode"))
    monkeypatch.setattr(database, "engine", engine)
    database.init_db()
    database.init_db()
    with factory() as db:
        assert db.get(Participant, pid).question_set_mode is None
        assert db.get(RuntimeSetting, 1).question_set_mode is None
        assert db.get(Participant, pid).experiment_spec_version == 6
    response = client.post(f"/api/participants/{pid}/diagnose-pretest")
    assert response.status_code == 409 and response.json()["detail"]["error_code"] == "legacy_experiment_read_only"
    assert client.get("/api/admin/question-set").json()["mode"] == "standard"
    fresh = create(client, "easy")
    with factory() as db:
        assert db.get(Participant, pid).question_set_mode is None
        assert db.get(Participant, fresh).question_set_mode == "easy"


@pytest.mark.parametrize("mode", ["standard", "easy"])
def test_partial_tests_advance_all_terms_and_do_not_count_replays_twice(isolated, mode):
    client, factory, _ = isolated
    pid = create(client, mode)
    assert client.post(f"/api/participants/{pid}/diagnose-pretest").status_code == 400
    submit(client, pid, "pretest", mode)
    first = client.get(f"/api/experiment/{pid}/retest").json()["questions"]
    q = first[0]
    spec = assessment_question_spec(q["term_slug"], "retest", mode=mode)
    body = {"participant_id": pid, "question_id": q["question_id"], "phase": "retest", "selected_option_ids": role_ids(q, spec, "unknown")}
    for _ in range(2):
        assert client.post("/api/attempts", json=body, headers={"Idempotency-Key": "partial-answer"}).status_code == 200
    score = client.post(f"/api/participants/{pid}/score-retest", headers={"Idempotency-Key": "partial-score"})
    assert score.status_code == 200, score.text
    assert client.post(f"/api/participants/{pid}/score-retest", headers={"Idempotency-Key": "partial-score"}).json() == score.json()
    second = client.get(f"/api/experiment/{pid}/retest").json()["questions"]
    assert len(second) == 3
    assert {q["question_id"] for q in first}.isdisjoint(q["question_id"] for q in second)
    assert all(q["body"] == assessment_question_spec(q["term_slug"], "retest", 2, mode)["body"] for q in second)
    with factory() as db:
        assert db.get(Participant, pid).retest_cycles_completed == 1


def test_inconsistent_mode_is_rejected_without_falling_back_and_old_six_review_keeps_its_bank(isolated):
    client, factory, _ = isolated
    pid = create(client)
    questions, _ = submit(client, pid, "pretest", "standard")
    with factory() as db:
        p = db.get(Participant, pid)
        p.question_set_mode = "easy"
        db.commit()
    failure = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "llm_knowledge"})
    assert failure.status_code == 503 and failure.json()["detail"]["error_code"] == "question_set_unavailable"
    with factory() as db:
        p = db.get(Participant, pid)
        p.question_set_mode = None
        p.experiment_spec_version = 6
        p.protocol_id = "experiment-plan-2026-10-24-two-posttests-v1"
        attempts = db.query(Attempt).filter_by(participant_id=pid).all()
        for a in attempts:
            a.option_order_snapshot = None
            a.question_body_snapshot = None
        db.delete(attempts[-1])
        db.commit()
        before = [(a.id, a.is_correct) for a in db.query(Attempt).filter_by(participant_id=pid)]
    review = client.get(f"/api/participants/{pid}/learning-targets").json()["test_results"]
    assert [q["question_body"] for q in review["results"]] == [q["body"] for q in questions]
    with factory() as db:
        assert before == [(a.id, a.is_correct) for a in db.query(Attempt).filter_by(participant_id=pid)]
