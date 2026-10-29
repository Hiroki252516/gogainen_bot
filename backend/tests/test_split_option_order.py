import pytest

from app.services.option_order import present_options


OPTIONS = [
    {"option_id": "correct-id", "label": "A", "body": "correct", "is_correct": True},
    {"option_id": "m1-id", "label": "B", "body": "wrong one", "misconception_type": "M1"},
    {"option_id": "m3-id", "label": "C", "body": "wrong three", "misconception_type": "M3"},
    {"option_id": "unknown-id", "label": "D", "body": "unknown", "misconception_type": "unknown"},
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
