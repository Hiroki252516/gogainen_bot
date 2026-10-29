import pytest

from app.services.split_assessment import TERMS, score_split_batch


def make_questions():
    return [
        {
            "question_id": f"{term}-{number}",
            "term_slug": term,
            "question_number": number,
            "options": [{"option_id": f"{term}-{number}-{role}", "role": role, "body": f"{role} body"} for role in ("correct", "M1", "M3", "unknown")],
        }
        for term in TERMS
        for number in (1, 2)
    ]


def selections_for(questions):
    return {question["question_id"]: question["options"][0]["option_id"] for question in questions}


def test_all_correct_scores_six_and_requires_no_teaching():
    questions = make_questions()
    result = score_split_batch(questions, selections_for(questions))
    assert result["correct_count"] == result["total"] == 6
    assert result["targets"] == []


def test_m3_priority_retains_both_observed_errors():
    questions = make_questions()
    selections = selections_for(questions)
    selections[questions[0]["question_id"]] = questions[0]["options"][1]["option_id"]
    selections[questions[1]["question_id"]] = questions[1]["options"][2]["option_id"]
    result = score_split_batch(questions, selections)
    target = result["targets"][0]
    assert target["diagnosis"] == "M3"
    assert [error["role"] for error in target["selected_errors"]] == ["M1", "M3"]
    assert target["confirmation_question_ids"] == [questions[0]["question_id"], questions[1]["question_id"]]


def test_unknown_priority_suppresses_errors_but_confirms_both_questions():
    questions = make_questions()
    selections = selections_for(questions)
    selections[questions[0]["question_id"]] = questions[0]["options"][3]["option_id"]
    selections[questions[1]["question_id"]] = questions[1]["options"][2]["option_id"]
    target = score_split_batch(questions, selections)["targets"][0]
    assert target["diagnosis"] == "unknown"
    assert target["selected_errors"] == []
    assert target["confirmation_question_ids"] == [questions[0]["question_id"], questions[1]["question_id"]]


def test_correct_questions_are_not_included_in_teaching_or_confirmation():
    questions = make_questions()
    selections = selections_for(questions)
    selections[questions[0]["question_id"]] = questions[0]["options"][1]["option_id"]
    target = score_split_batch(questions, selections)["targets"][0]
    assert target["diagnosis"] == "M1"
    assert target["confirmation_question_ids"] == [questions[0]["question_id"]]
    assert [error["question_id"] for error in target["selected_errors"]] == [questions[0]["question_id"]]


def test_incomplete_and_cross_question_selections_are_rejected():
    questions = make_questions()
    selections = selections_for(questions)
    missing = dict(selections)
    del missing[questions[0]["question_id"]]
    with pytest.raises(ValueError):
        score_split_batch(questions, missing)
    selections[questions[0]["question_id"]] = questions[1]["options"][0]["option_id"]
    with pytest.raises(ValueError):
        score_split_batch(questions, selections)


def test_reserved_question_three_cannot_be_scored():
    questions = make_questions()
    selections = selections_for(questions)
    questions[0]["question_number"] = 3
    with pytest.raises(ValueError, match="only questions one and two"):
        score_split_batch(questions, selections)
