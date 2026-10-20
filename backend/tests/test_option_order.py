from __future__ import annotations

from collections import Counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.models import Attempt, Base, Participant, Question, Term, TutorSession, TutorTurn
from app.seed.content_loader import (
    ACTIVE_TERM_SLUGS,
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


def _assert_role_balance(bank: str, items: list[tuple[int, list[dict]]]) -> None:
    counts = {role: Counter() for role in ("correct", "M1", "M3", "unknown")}
    for item_index, options in items:
        displayed = present_options(options, mode=RANDOMIZED, bank=bank, item_index=item_index)
        assert [option["label"] for option in displayed] == list("ABCDEFGHIJ")
        source_by_body = {option["body"]: option_role(option) for option in options}
        for option in displayed:
            counts[source_by_body[option["body"]]][option["label"]] += 1
    for role_counts in counts.values():
        observed = [role_counts[label] for label in "ABCDEFGHIJ"]
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
        for phase, variant_indexes in (("pretest", [1]), ("retest", range(1, 6)), ("final_test", [1])):
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
        for stage in LEARNING_STAGES:
            for variant_index in range(1, 6):
                spec = learning_question_spec(term_slug, stage, variant_index)
                item_index = learning_bank_index(term_slug, stage, variant_index)
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

    assert len(assessment_items) == 21
    assert len(learning_items) == 30
    assert unknown_labels == set("ABCDEFGHIJ")
    _assert_role_balance("assessment", assessment_items)
    _assert_role_balance("learning", learning_items)


def test_missing_or_unknown_participant_mode_defaults_to_debug_fixed():
    assert effective_option_order_mode(None) == DEBUG_FIXED
    assert effective_option_order_mode("old_value") == DEBUG_FIXED


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
    response = client.post(
        "/api/participants",
        json={"assignment_code": assignment_code, "consent_checked": True},
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
        _assert_debug_roles(question["options"], assessment_question_spec(question["term_slug"], "pretest")["options"])

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
        spec = assessment_question_spec(question["term_slug"], "pretest")
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


def test_randomized_learning_response_uses_internal_role_and_preserves_displayed_history(isolated_api):
    client, engine = isolated_api
    assert client.put("/api/admin/option-order", json={"mode": RANDOMIZED}).status_code == 200
    participant_id = _create(client, "A")
    questions = client.get(f"/api/experiment/{participant_id}/pretest").json()["questions"]

    for question in questions:
        spec = assessment_question_spec(question["term_slug"], "pretest")
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
    assert all(option["option_id"] not in set("ABCDEFGHIJ") for option in options)
    assert all(set(option) == {"option_id", "label", "body", "exclusive"} for option in options)
    unknown_option = next(option for option in options if option["exclusive"])
    response = client.post(
        f"/api/tutor-turns/{turn['turn_id']}/respond",
        json={"selected_option_ids": [unknown_option["option_id"]]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["is_sufficient"] is False
    assert response.json()["learning_misconception_type"] == "unknown"

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
