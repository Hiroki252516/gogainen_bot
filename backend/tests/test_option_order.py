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
from split_api_support import new_research_code


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
    response = client.post(
        "/api/participants",
        json={"assignment_code": assignment_code, "consent_checked": True, "research_code": new_research_code()},
    )
    assert response.status_code == 200, response.text
    return response.json()["participant_id"]
