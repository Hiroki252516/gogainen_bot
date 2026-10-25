import json
from pathlib import Path

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Attempt, Base, EvaluationSummary, Participant, Question, QuestionOption, Term
from app.core.question_sets import ASSESSMENT_BANK_VERSIONS
from app.seed.content_loader import ASSESSMENT_BANK_VERSION, CONTENT_PATH, PRE_ISSUE156_CONTENT_PATH, load_content
from app.seed.seed_questions import _upsert_question, seed_database
from app.services import experiment


def test_llm_proposals_are_preserved_verbatim_in_all_three_measurements():
    fixture = Path(__file__).with_name("fixtures") / "issue156_llm_proposals.json"
    expected = json.loads(fixture.read_text(encoding="utf-8"))
    questions = load_content()["terms"][0]["questions"]
    assert [questions["pretest"][0], *questions["retest"]] == expected


def test_replacement_seed_preserves_old_questions_options_and_snapshotless_results(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old-bank.db'}")
    Base.metadata.create_all(engine)
    old_content = yaml.safe_load(PRE_ISSUE156_CONTENT_PATH.read_text(encoding="utf-8"))
    with Session(engine) as db:
        old_questions = []
        for index, item in enumerate(old_content["terms"], start=1):
            term = Term(slug=item["slug"], label=item["label"], description=item["description"], display_order=index)
            db.add(term)
            db.flush()
            for phase in ("pretest", "retest", "final_test"):
                variants = item["questions"].get(phase) or [item["questions"]["retest"][0]]
                for variant in variants:
                    options = [
                        (label, body, role == "correct", None if role == "correct" else role)
                        for role, labels in (("correct", "ABC"), ("M1", "DEF"), ("M3", "GHI"))
                        for label, body in zip(labels, variant["choices"][role], strict=True)
                    ] + [("J", "わからない。", False, "unknown")]
                    old_questions.append(_upsert_question(
                        db, term, phase=phase, question_type="multi_select",
                        body=f"{variant['scenario']}\n\n{variant['task']}", expected_answer="A、B、C",
                        construct_key=f"{term.slug}_{'final_test' if phase == 'final_test' else 'definition'}",
                        variant_key=variant["variant_key"], options=options,
                    ))
        old_participant = Participant(
            display_code="OLD-BANK", group_condition="proposed", current_step="learning_targets",
            experiment_spec_version=5, protocol_id="experiment-plan-2026-10-23-learning-rotation-v1",
            learning_content_version=3, retest_cycles_completed=3,
        )
        db.add(old_participant)
        db.flush()
        question = old_questions[0]
        selected = db.query(QuestionOption).filter_by(question_id=question.id, option_label="D").one()
        db.add(Attempt(
            participant_id=old_participant.id, term_id=question.term_id, question_id=question.id,
            phase="pretest", test_round="test", selected_option_ids=[selected.id], is_correct=False,
            misconception_type="M1", question_body_snapshot=None, option_order_snapshot=None,
        ))
        db.add(EvaluationSummary(participant_id=old_participant.id, group_condition="proposed", pretest_score=0.125))
        db.commit()
        before_questions = {row.id: (row.body, row.expected_answer, row.construct_key, row.variant_key) for row in old_questions}
        before_options = {row.id: (row.question_id, row.option_label, row.body, row.is_correct, row.misconception_type) for row in db.query(QuestionOption)}
        seed_database(db)
        seed_database(db)
        assert db.query(Question).count() == 39
        assert db.query(Question).filter_by(is_active=True).count() == 24
        assert db.query(QuestionOption).count() == 390
        for qid, expected in before_questions.items():
            row = db.get(Question, qid)
            assert not row.is_active
            assert (row.body, row.expected_answer, row.construct_key, row.variant_key) == expected
        for oid, expected in before_options.items():
            row = db.get(QuestionOption, oid)
            assert (row.question_id, row.option_label, row.body, row.is_correct, row.misconception_type) == expected
        for bank in ASSESSMENT_BANK_VERSIONS.values():
            assert db.query(Question).filter(Question.is_active.is_(True), Question.construct_key.endswith(bank)).count() == 12
        logs = experiment.participant_logs(db, old_participant.id)
        assert logs["attempts"][0]["question_body"] == before_questions[question.id][0]
        assert logs["attempts"][0]["selected_option_body"] == "D"
        assert logs["participant"]["post_pretest_tests_completed"] is None
        assert logs["participant"]["post_pretest_test_limit"] is None
        assert logs["participant"]["retest_cycles_completed"] == 3
        assert logs["latest_evaluation_summary"]["pretest_score"] == 0.125
        review = experiment.latest_test_results(db, old_participant.id)
        assert review["results"][0]["question_body"] == before_questions[question.id][0]
        assert review["results"][0]["selected_options"] == [{"label": "D", "body": selected.body}]
        assert review["results"][1]["question_body"] == old_content["terms"][1]["questions"]["pretest"][0]["scenario"] + "\n\n" + old_content["terms"][1]["questions"]["pretest"][0]["task"]
        assert db.get(Attempt, logs["attempts"][0]["attempt_id"]).question_body_snapshot is None
    engine.dispose()
