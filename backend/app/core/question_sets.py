from typing import Literal


QuestionSetMode = Literal["standard", "easy"]
STANDARD = "standard"
EASY = "easy"
QUESTION_SET_MODES = (STANDARD, EASY)
ASSESSMENT_BANK_VERSIONS = {STANDARD: "scenario-actions-v1", EASY: "scenario-actions-easy-v1"}
LEARNING_CONTENT_VERSIONS = {STANDARD: 3, EASY: 4}


def question_set_mode(value: str | None) -> QuestionSetMode:
    if value is None:
        return STANDARD
    if value not in QUESTION_SET_MODES:
        raise ValueError("unsupported question set mode")
    return value


def assessment_construct_key(term_slug: str, phase: str, mode: str | None = STANDARD) -> str:
    bank = ASSESSMENT_BANK_VERSIONS[question_set_mode(mode)]
    return f"{term_slug}_{'final_test_' if phase == 'final_test' else ''}{bank}"


def explanation_context(mode: str | None) -> dict[str, str]:
    return {"explanation_level": "beginner"} if question_set_mode(mode) == EASY else {}
