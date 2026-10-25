from typing import Literal


QuestionSetMode = Literal["standard", "easy"]
STANDARD = "standard"
EASY = "easy"
QUESTION_SET_MODES = (STANDARD, EASY)
ASSESSMENT_BANK_VERSIONS = {STANDARD: "scenario-actions-v4", EASY: "scenario-actions-easy-v1"}
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
}
LEARNING_CONTENT_VERSIONS = {STANDARD: 10, EASY: 4}


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
