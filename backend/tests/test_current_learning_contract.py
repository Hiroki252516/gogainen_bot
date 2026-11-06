import pytest

from app.core.question_sets import LEARNING_CONTENT_VERSIONS
from app.seed.content_loader import ACTIVE_TERM_SLUGS, assessment_question_spec, learning_question_spec


@pytest.mark.parametrize("term_slug", ACTIVE_TERM_SLUGS)
@pytest.mark.parametrize("stage", ["enrichment", "conceptual_change"])
@pytest.mark.parametrize("index,phase,assessment_index", [(1, "pretest", 1), (2, "retest", 1), (3, "retest", 2)])
def test_current_confirmation_reuses_the_expected_assessment(term_slug, stage, index, phase, assessment_index):
    learning = learning_question_spec(term_slug, stage, index)
    assessment = assessment_question_spec(term_slug, phase, assessment_index)
    assert learning["variant_key"] == f"learning_round_v{index}"
    assert learning["_content_version"] == LEARNING_CONTENT_VERSIONS["standard"]
    assert learning["body"] == assessment["body"]
    assert [{key: value for key, value in option.items() if key != "option_id"} for option in learning["options"]] == assessment["options"]


@pytest.mark.parametrize("term_slug", ACTIVE_TERM_SLUGS)
def test_historical_learning_bank_remains_available_for_restoration(term_slug):
    current = learning_question_spec(term_slug, "enrichment", 1)
    historical = learning_question_spec(
        term_slug, "enrichment", 1,
        content_version=LEARNING_CONTENT_VERSIONS["standard"], use_current_assessment_source=False,
    )
    assert current["body"] == assessment_question_spec(term_slug, "pretest", 1)["body"]
    assert historical["body"] != current["body"]
    assert len(historical["options"]) == 10
