import pytest

from app.services.option_order import present_options


OPTIONS = [
    {"option_id": "correct-id", "label": "A", "body": "correct", "is_correct": True},
    {"option_id": "m1-id", "label": "B", "body": "wrong one", "misconception_type": "M1"},
    {"option_id": "m3-id", "label": "C", "body": "wrong three", "misconception_type": "M3"},
    {"option_id": "unknown-id", "label": "D", "body": "unknown", "misconception_type": "unknown"},
]
SIX_OPTIONS = [
    {"option_id": "correct-id", "label": "A", "body": "correct", "is_correct": True},
    {"option_id": "m1-one-id", "label": "B", "body": "wrong M1 one", "misconception_type": "M1"},
    {"option_id": "m1-two-id", "label": "C", "body": "wrong M1 two", "misconception_type": "M1"},
    {"option_id": "m3-one-id", "label": "D", "body": "wrong M3 one", "misconception_type": "M3"},
    {"option_id": "m3-two-id", "label": "E", "body": "wrong M3 two", "misconception_type": "M3"},
    {"option_id": "unknown-id", "label": "F", "body": "unknown", "misconception_type": "unknown"},
]


def test_four_option_debug_order_and_public_fields():
    result = present_options(OPTIONS, mode="debug_fixed", bank="assessment", item_index=0)
    assert [item["label"] for item in result] == list("ABCD")
    assert [item["exclusive"] for item in result] == [False, False, False, True]
    assert all(set(item) == {"option_id", "label", "body", "exclusive"} for item in result)


def test_four_option_randomized_order_is_reproducible_balanced_and_unknown_last():
    orders = [present_options(OPTIONS, mode="randomized", bank="assessment", item_index=i) for i in range(3)]
    for index, order in enumerate(orders):
        assert order == present_options(OPTIONS, mode="randomized", bank="assessment", item_index=index)
        assert [item["label"] for item in order] == list("ABCD")
        assert order[-1]["option_id"] == "unknown-id"
        assert all(set(item) == {"option_id", "label", "body", "exclusive"} for item in order)
    for identifier in ("correct-id", "m1-id", "m3-id"):
        assert {next(item["label"] for item in order if item["option_id"] == identifier) for order in orders} == set("ABC")


def test_four_option_randomization_rejects_duplicate_roles():
    malformed = [*OPTIONS[:3], {**OPTIONS[3], "misconception_type": "M1"}]
    with pytest.raises(ValueError):
        present_options(malformed, mode="randomized", bank="assessment", item_index=0)


def test_six_option_debug_order_and_randomized_role_balance():
    fixed = present_options(SIX_OPTIONS, mode="debug_fixed", bank="assessment", item_index=0)
    assert [item["label"] for item in fixed] == list("ABCDEF")
    assert [item["exclusive"] for item in fixed] == [False, False, False, False, False, True]

    role_by_id = {
        "correct-id": "correct",
        "m1-one-id": "M1",
        "m1-two-id": "M1",
        "m3-one-id": "M3",
        "m3-two-id": "M3",
        "unknown-id": "unknown",
    }
    counts = {role: {label: 0 for label in "ABCDE"} for role in ("correct", "M1", "M3")}
    for item_index in range(5):
        displayed = present_options(SIX_OPTIONS, mode="randomized", bank="assessment", item_index=item_index)
        assert displayed == present_options(SIX_OPTIONS, mode="randomized", bank="assessment", item_index=item_index)
        assert [item["label"] for item in displayed] == list("ABCDEF")
        assert displayed[-1]["option_id"] == "unknown-id"
        for item in displayed[:-1]:
            counts[role_by_id[item["option_id"]]][item["label"]] += 1
        assert all(set(item) == {"option_id", "label", "body", "exclusive"} for item in displayed)

    assert counts["correct"] == {label: 1 for label in "ABCDE"}
    assert counts["M1"] == {label: 2 for label in "ABCDE"}
    assert counts["M3"] == {label: 2 for label in "ABCDE"}


def test_six_option_randomization_rejects_incorrect_role_counts():
    malformed = [*SIX_OPTIONS[:-1], {**SIX_OPTIONS[-1], "misconception_type": "M1"}]
    with pytest.raises(ValueError):
        present_options(malformed, mode="randomized", bank="assessment", item_index=0)
