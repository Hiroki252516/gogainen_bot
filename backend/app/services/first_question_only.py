"""Read each participant's saved question-selection snapshot."""


def enabled(participant) -> bool:
    return getattr(participant, "first_question_only", None) is True


def question_numbers(participant) -> tuple[int, ...]:
    return (1,) if enabled(participant) else (1, 2)
