from __future__ import annotations

from collections import Counter
from copy import deepcopy

import pytest
from admin_client import AuthenticatedTestClient as TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.models import Attempt, Base, Participant, Question, Term, TutorSession, TutorTurn
from app.seed.content_loader import (
    ACTIVE_TERM_SLUGS,
    ASSESSMENT_VARIANT_COUNTS,
    LEARNING_STAGES,
    assessment_question_spec,
    learning_question_spec,
)
from app.seed.seed_questions import seed_database
from app.services.option_order import (
    DEBUG_FIXED,
    RANDOMIZED,
    assessment_bank_index,
    effective_option_order_mode,
    learning_bank_index,
    option_role,
    present_options,
)
from app.services.interaction_history import build_interaction_history
from app.services import experiment as experiment_service


def _assert_role_balance(bank: str, items: list[tuple[int, list[dict]]]) -> None:
    counts = {role: Counter() for role in ("correct", "M1", "M3", "unknown")}
    for item_index, options in items:
        displayed = present_options(options, mode=RANDOMIZED, bank=bank, item_index=item_index)
        assert [option["label"] for option in displayed] == list("ABCDEFGHIJ")
        source_by_body = {option["body"]: option_role(option) for option in options}
        for option in displayed:
            counts[source_by_body[option["body"]]][option["label"]] += 1
    assert counts["unknown"] == {"J": len(items)}
    for role in ("correct", "M1", "M3"):
        role_counts = counts[role]
        assert role_counts["J"] == 0
        observed = [role_counts[label] for label in "ABCDEFGHI"]
        assert max(observed) - min(observed) <= 1


def _assert_debug_roles(options: list[dict], canonical_options: list[dict]) -> None:
    role_by_body = {option["body"]: option_role(option) for option in canonical_options}
    role_by_label = {option["label"]: role_by_body[option["body"]] for option in options}
    assert role_by_label == {
        **{label: "correct" for label in "ABC"},
        **{label: "M1" for label in "DEF"},
        **{label: "M3" for label in "GHI"},
        "J": "unknown",
    }


def test_randomized_assignment_is_stable_unique_and_balanced_for_both_banks():
    assessment_items = []
    learning_items = []
    unknown_labels = set()
    for term_slug in ACTIVE_TERM_SLUGS:
        for phase, count in ASSESSMENT_VARIANT_COUNTS.items():
            variant_indexes = range(1, count + 1)
            for variant_index in variant_indexes:
                spec = assessment_question_spec(term_slug, phase, variant_index)
                item_index = assessment_bank_index(term_slug, phase, spec["variant_key"])
                assessment_items.append((item_index, spec["options"]))
                fixed = present_options(spec["options"], mode=DEBUG_FIXED, bank="assessment", item_index=item_index)
                _assert_debug_roles(fixed, spec["options"])
                displayed = present_options(spec["options"], mode=RANDOMIZED, bank="assessment", item_index=item_index)
                unknown_labels.add(next(option["label"] for option in displayed if option["exclusive"]))
                repeated = present_options(spec["options"], mode=RANDOMIZED, bank="assessment", item_index=item_index)
                assert [(option["label"], option["body"]) for option in displayed] == [
                    (option["label"], option["body"]) for option in repeated
                ]
    for term_slug in ACTIVE_TERM_SLUGS:
        for variant_index in range(1, 4):
            enrichment = learning_question_spec(term_slug, "enrichment", variant_index)
            conceptual_change = learning_question_spec(term_slug, "conceptual_change", variant_index)
            assert enrichment["body"] == conceptual_change["body"]
            assert enrichment["options"] == conceptual_change["options"]
            item_index = learning_bank_index(term_slug, "enrichment", variant_index)
            assert item_index == learning_bank_index(term_slug, "conceptual_change", variant_index)
            spec = enrichment
            learning_items.append((item_index, spec["options"]))
            fixed = present_options(spec["options"], mode=DEBUG_FIXED, bank="learning", item_index=item_index)
            _assert_debug_roles(fixed, spec["options"])
            displayed = present_options(spec["options"], mode=RANDOMIZED, bank="learning", item_index=item_index)
            unknown_labels.add(next(option["label"] for option in displayed if option["exclusive"]))
            assert len({option["option_id"] for option in displayed}) == 10
            assert all(option["option_id"].startswith("lo_") for option in displayed)
            repeated = present_options(spec["options"], mode=RANDOMIZED, bank="learning", item_index=item_index)
            assert [(option["label"], option["body"]) for option in displayed] == [
                (option["label"], option["body"]) for option in repeated
            ]

    assert len(assessment_items) == 9
    assert len(learning_items) == 9
    assert unknown_labels == {"J"}
    _assert_role_balance("assessment", assessment_items)
    _assert_role_balance("learning", learning_items)


def test_missing_or_unknown_participant_mode_defaults_to_debug_fixed():
    assert effective_option_order_mode(None) == DEBUG_FIXED
    assert effective_option_order_mode("old_value") == DEBUG_FIXED


@pytest.mark.parametrize("variant_key", [None, "", "pretest", "pretest_vinvalid"])
def test_assessment_bank_index_rejects_invalid_variant_keys(variant_key):
    with pytest.raises(ValueError, match="invalid assessment variant key"):
        assessment_bank_index(ACTIVE_TERM_SLUGS[0], "pretest", variant_key)


@pytest.fixture
def isolated_api(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'option-order.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_database(db)
        seed_database(db)

    def override_get_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app), engine
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def _create(client: TestClient, assignment_code: str) -> str:
    # Ten-choice positioning remains supported by the easy bank. Four-choice
    # positioning and API replay are covered by test_split_option_order/flow.
    assert client.put("/api/admin/question-set", json={"mode": "easy"}).status_code == 200
    response = client.post(
        "/api/participants",
        json={"assignment_code": assignment_code, "consent_checked": True, "student_number": "TEST-OPTION-ORDER"},
    )
    assert response.status_code == 200, response.text
    return response.json()["participant_id"]


def test_admin_mode_is_persisted_and_snapshotted_for_new_participants(isolated_api):
    client, engine = isolated_api
    assert client.get("/api/admin/option-order").json() == {
        "mode": DEBUG_FIXED,
        "applies_to": "new_participants_only",
    }
    assert client.put("/api/admin/option-order", json={"mode": DEBUG_FIXED}).status_code == 200
    debug_participant = _create(client, "A")
    debug_questions = client.get(f"/api/experiment/{debug_participant}/pretest").json()["questions"]
    for question in debug_questions:
        assert [option["label"] for option in question["options"]] == list("ABCDEFGHIJ")
        _assert_debug_roles(question["options"], assessment_question_spec(question["term_slug"], "pretest", mode="easy")["options"])

    randomized_setting = client.put("/api/admin/option-order", json={"mode": RANDOMIZED})
    assert randomized_setting.status_code == 200
    proposed_participant = _create(client, "A")
    control_participant = _create(client, "B")
    proposed_questions = client.get(f"/api/experiment/{proposed_participant}/pretest").json()["questions"]
    control_questions = client.get(f"/api/experiment/{control_participant}/pretest").json()["questions"]
    still_debug_questions = client.get(f"/api/experiment/{debug_participant}/pretest").json()["questions"]

    assert proposed_questions == control_questions
    assert proposed_questions != debug_questions
    assert still_debug_questions == debug_questions
    for question in proposed_questions:
        options = question["options"]
        assert [option["label"] for option in options] == list("ABCDEFGHIJ")
        assert all(set(option) == {"option_id", "label", "body", "exclusive"} for option in options)
        assert sum(option["exclusive"] for option in options) == 1
        assert options[-1]["exclusive"] is True
        assert options[-1]["label"] == "J"
        assert not any("is_correct" in option or "misconception_type" in option for option in options)

    with Session(engine) as db:
        modes = {
            row.id: row.option_order_mode
            for row in db.query(Participant).filter(Participant.id.in_([debug_participant, proposed_participant, control_participant]))
        }
    assert modes == {
        debug_participant: DEBUG_FIXED,
        proposed_participant: RANDOMIZED,
        control_participant: RANDOMIZED,
    }

    assert client.put("/api/admin/option-order", json={"mode": "unsupported"}).status_code == 422


def test_randomized_labels_do_not_change_assessment_scoring_or_unknown_exclusivity(isolated_api):
    client, engine = isolated_api
    assert client.put("/api/admin/option-order", json={"mode": RANDOMIZED}).status_code == 200
    participant_id = _create(client, "A")
    questions = client.get(f"/api/experiment/{participant_id}/pretest").json()["questions"]

    for index, question in enumerate(questions):
        spec = assessment_question_spec(question["term_slug"], "pretest", mode="easy")
        if index == 0:
            selected_bodies = {option["body"] for option in spec["options"] if option["misconception_type"] == "unknown"}
        else:
            selected_bodies = {option["body"] for option in spec["options"] if option["misconception_type"] == "M1"}
        selected_ids = [option["option_id"] for option in question["options"] if option["body"] in selected_bodies]
        assert len(selected_ids) == (1 if index == 0 else 3)
        response = client.post(
            "/api/attempts",
            json={
                "participant_id": participant_id,
                "question_id": question["question_id"],
                "phase": "pretest",
                "selected_option_ids": selected_ids,
            },
        )
        assert response.status_code == 200, response.text

    diagnosed = client.post(f"/api/participants/{participant_id}/diagnose-pretest")
    assert diagnosed.status_code == 200, diagnosed.text
    with Session(engine) as db:
        attempts = db.query(Attempt).filter_by(participant_id=participant_id).all()
        actual_types = {db.get(Question, attempt.question_id).term_id: attempt.misconception_type for attempt in attempts}
        snapshots = {attempt.question_id: attempt.option_order_snapshot for attempt in attempts}
        assert all(attempt.is_correct is False for attempt in attempts)
        for question in questions:
            assert snapshots[question["question_id"]] == question["options"]
        expected_types = {
            db.query(Term).filter_by(slug=question["term_slug"]).one().id: ("unknown" if index == 0 else "M1")
            for index, question in enumerate(questions)
        }
    assert actual_types == expected_types


@pytest.mark.parametrize("mode", [DEBUG_FIXED, RANDOMIZED])
@pytest.mark.parametrize("assignment", ["A", "B"])
def test_both_post_tests_grade_internal_roles_and_preserve_displayed_results(isolated_api, mode, assignment):
    client, engine = isolated_api
    assert client.put("/api/admin/option-order", json={"mode": mode}).status_code == 200
    pid = _create(client, assignment)
    pretest = client.get(f"/api/experiment/{pid}/pretest").json()["questions"]
    for question in pretest:
        unknown_id = next(option["option_id"] for option in question["options"] if option["exclusive"])
        assert client.post("/api/attempts", json={"participant_id": pid, "question_id": question["question_id"], "selected_option_ids": [unknown_id]}).status_code == 200
    assert client.post(f"/api/participants/{pid}/diagnose-pretest").status_code == 200
    for cycle in (1, 2):
        questions = client.get(f"/api/experiment/{pid}/retest").json()["questions"]
        for index, question in enumerate(questions):
            spec = assessment_question_spec(question["term_slug"], "retest", cycle, mode="easy")
            if index == 0:
                selected_bodies = {spec["options"][i]["body"] for i in (0, 3, 6)}
            else:
                selected_bodies = {o["body"] for o in spec["options"] if o["misconception_type"] == "unknown"} if index == 1 else {o["body"] for o in spec["options"] if o["is_correct"]}
            selected_ids = [o["option_id"] for o in question["options"] if o["body"] in selected_bodies]
            response = client.post("/api/attempts", json={"participant_id": pid, "question_id": question["question_id"], "phase": "retest", "selected_option_ids": selected_ids})
            assert response.status_code == 200, response.text
            assert all(set(o) == {"option_id", "label", "body", "exclusive"} for o in question["options"])
        scored = client.post(f"/api/participants/{pid}/score-retest")
        assert scored.status_code == 200
        assert scored.json()["post_pretest_tests_completed"] == cycle
        assert scored.json()["next_step"] == ("survey" if cycle == 2 else "learning_targets")
        review = client.get(f"/api/participants/{pid}/learning-targets").json()["test_results"]
        assert review["test_round"] == f"retest_{cycle}"
        assert [r["is_correct"] for r in review["results"]] == [False, False, True]
        with Session(engine) as db:
            for index, question in enumerate(questions):
                attempt = db.query(Attempt).filter_by(participant_id=pid, question_id=question["question_id"]).one()
                assert attempt.misconception_type == ("M3", "unknown", None)[index]
                assert attempt.option_order_snapshot == question["options"]
                selected_options = [o for o in question["options"] if o["option_id"] in attempt.selected_option_ids]
                assert review["results"][index]["selected_options"] == [{"label": o["label"], "body": o["body"]} for o in selected_options]
    assert client.get(f"/api/experiment/{pid}/retest").status_code == 409


def test_randomized_learning_response_uses_internal_role_and_preserves_displayed_history(isolated_api, monkeypatch):
    client, engine = isolated_api
    assert client.put("/api/admin/option-order", json={"mode": RANDOMIZED}).status_code == 200
    participant_id = _create(client, "A")
    questions = client.get(f"/api/experiment/{participant_id}/pretest").json()["questions"]

    for question in questions:
        spec = assessment_question_spec(question["term_slug"], "pretest", mode="easy")
        m1_bodies = {option["body"] for option in spec["options"] if option["misconception_type"] == "M1"}
        selected_ids = [option["option_id"] for option in question["options"] if option["body"] in m1_bodies]
        response = client.post(
            "/api/attempts",
            json={
                "participant_id": participant_id,
                "question_id": question["question_id"],
                "phase": "pretest",
                "selected_option_ids": selected_ids,
            },
        )
        assert response.status_code == 200, response.text

    diagnosed = client.post(f"/api/participants/{participant_id}/diagnose-pretest")
    assert diagnosed.status_code == 200, diagnosed.text
    session_response = client.post(
        "/api/tutor-sessions",
        json={"participant_id": participant_id, "term_slug": "llm_knowledge"},
    )
    assert session_response.status_code == 200, session_response.text
    session_id = session_response.json()["tutor_session_id"]
    turn_response = client.post(f"/api/tutor-sessions/{session_id}/turns", json={})
    assert turn_response.status_code == 200, turn_response.text
    turn = turn_response.json()
    practice_question = turn["practice_question"]
    options = practice_question["options"]

    assert len(options) == 10
    assert sum(option["exclusive"] for option in options) == 1
    assert options[-1]["exclusive"] is True
    assert options[-1]["label"] == "J"
    assert all(option["option_id"] not in set("ABCDEFGHIJ") for option in options)
    assert all(set(option) == {"option_id", "label", "body", "exclusive"} for option in options)
    # Previously generated questions may have unknown elsewhere. Re-fetching
    # and answering must retain their saved layout rather than regenerate it.
    saved_question = deepcopy(practice_question)
    first = saved_question["options"][0]
    last = saved_question["options"][-1]
    first["label"], last["label"] = last["label"], first["label"]
    saved_question["options"].sort(key=lambda option: option["label"])
    with Session(engine) as db:
        saved_turn = db.get(TutorTurn, turn["turn_id"])
        saved_turn.practice_question_json = saved_question
        db.commit()
    cached = client.post(f"/api/tutor-sessions/{session_id}/turns", json={})
    assert cached.status_code == 200, cached.text
    assert cached.json()["practice_question"]["options"] == saved_question["options"]
    options = saved_question["options"]
    unknown_option = next(option for option in options if option["exclusive"])
    assert unknown_option["label"] == "A"

    original_public_learning_options = experiment_service._public_learning_options

    def fail_if_current_options_are_regenerated(spec, participant, term_slug, learning_stage, variant_index):
        if variant_index == 1:
            pytest.fail("answer processing should use the saved displayed-options snapshot")
        return original_public_learning_options(spec, participant, term_slug, learning_stage, variant_index)

    monkeypatch.setattr(experiment_service, "_public_learning_options", fail_if_current_options_are_regenerated)
    response = client.post(
        f"/api/tutor-turns/{turn['turn_id']}/respond",
        json={"selected_option_ids": [unknown_option["option_id"]]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["is_sufficient"] is False
    assert response.json()["learning_misconception_type"] == "unknown"
    expected_by_body = {
        option["body"]: option["is_correct"]
        for option in assessment_question_spec("llm_knowledge", "pretest", mode="easy")["options"]
    }
    assert response.json()["answer_key"] == {
        option["option_id"]: expected_by_body[option["body"]] for option in options
    }

    with Session(engine) as db:
        saved_turn = db.get(TutorTurn, turn["turn_id"])
        saved_session = db.get(TutorSession, session_id)
        assert saved_turn is not None and saved_session is not None
        assert saved_turn.practice_question_json["options"] == options
        assert saved_turn.grading_json["selected_option_ids"] == [unknown_option["option_id"]]
        history = build_interaction_history(db, participant_id, saved_session.term_id)

    learning_record = next(record for record in history if record["source_type"] == "learning_turn")
    assert learning_record["selected_options"] == [
        {"label": unknown_option["label"], "body": unknown_option["body"]}
    ]
    assert learning_record["is_correct"] is False
