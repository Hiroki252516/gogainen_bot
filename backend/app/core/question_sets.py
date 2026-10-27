from typing import Literal


QuestionSetMode = Literal["standard", "easy"]
STANDARD = "standard"
EASY = "easy"
QUESTION_SET_MODES = (STANDARD, EASY)
ASSESSMENT_BANK_VERSIONS = {STANDARD: "scenario-actions-v9", EASY: "scenario-actions-easy-v1"}
# The current spec uses the map above; this map only restores historical results.
HISTORICAL_ASSESSMENT_BANK_VERSIONS = {
    6: {STANDARD: "scenario-actions-v1"},
    7: {STANDARD: "scenario-actions-v1", EASY: "scenario-actions-easy-v1"},
    8: {STANDARD: "scenario-actions-v1", EASY: "scenario-actions-easy-v1"},
    9: {STANDARD: "scenario-actions-v2", EASY: "scenario-actions-easy-v1"},
    10: {STANDARD: "scenario-actions-v3", EASY: "scenario-actions-easy-v1"},
    11: {STANDARD: "scenario-actions-v4", EASY: "scenario-actions-easy-v1"},
    12: {STANDARD: "scenario-actions-v4", EASY: "scenario-actions-easy-v1"},
    13: {STANDARD: "scenario-actions-v4", EASY: "scenario-actions-easy-v1"},
    14: {STANDARD: "scenario-actions-v4", EASY: "scenario-actions-easy-v1"},
    15: {STANDARD: "scenario-actions-v4", EASY: "scenario-actions-easy-v1"},
    16: {STANDARD: "scenario-actions-v4", EASY: "scenario-actions-easy-v1"},
    17: {STANDARD: "scenario-actions-v4", EASY: "scenario-actions-easy-v1"},
    18: {STANDARD: "scenario-actions-v4", EASY: "scenario-actions-easy-v1"},
    19: {STANDARD: "scenario-actions-v5", EASY: "scenario-actions-easy-v1"},
    20: {STANDARD: "scenario-actions-v6", EASY: "scenario-actions-easy-v1"},
    21: {STANDARD: "scenario-actions-v6", EASY: "scenario-actions-easy-v1"},
    22: {STANDARD: "scenario-actions-v6", EASY: "scenario-actions-easy-v1"},
    23: {STANDARD: "scenario-actions-v7", EASY: "scenario-actions-easy-v1"},
    24: {STANDARD: "scenario-actions-v8", EASY: "scenario-actions-easy-v1"},
}
LEARNING_CONTENT_VERSIONS = {STANDARD: 15, EASY: 4}


def question_set_mode(value: str | None) -> QuestionSetMode:
    if value is None:
        return STANDARD
    if value not in QUESTION_SET_MODES:
        raise ValueError("unsupported question set mode")
    return value


def assessment_construct_key(
    term_slug: str, phase: str, mode: str | None = STANDARD, *, bank_version: str | None = None,
) -> str:
    bank = bank_version or ASSESSMENT_BANK_VERSIONS[question_set_mode(mode)]
    return f"{term_slug}_{'final_test_' if phase == 'final_test' else ''}{bank}"


def explanation_context(mode: str | None) -> dict[str, str]:
    return {"explanation_level": "beginner"} if question_set_mode(mode) == EASY else {}
