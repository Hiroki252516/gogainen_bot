from sqlalchemy.orm import Session

from app.db.session import SessionLocal, init_db
from app.models import Question, QuestionOption, Term
from app.seed.data import SEED_TERMS
from app.seed.content_loader import seed_terms
from app.core.question_sets import ASSESSMENT_BANK_VERSIONS, STANDARD, EASY, assessment_construct_key


def _sync_options(db: Session, question: Question, options: list[tuple[str, str, bool, str | None]]) -> None:
    existing = {option.option_label: option for option in db.query(QuestionOption).filter(QuestionOption.question_id == question.id).all()}
    for order, (label, body, is_correct, misconception_type) in enumerate(options, start=1):
        option = existing.get(label)
        if not option:
            option = QuestionOption(question_id=question.id, option_label=label)
            db.add(option)
        option.body = body
        option.is_correct = is_correct
        option.misconception_type = misconception_type
        option.default_order = order


def _upsert_question(
    db: Session,
    term: Term,
    *,
    phase: str,
    question_type: str,
    body: str,
    expected_answer: str,
    construct_key: str,
    variant_key: str,
    options: list[tuple[str, str, bool, str | None]] | None = None,
) -> Question:
    # A retired bank must still resolve historical answers without snapshots.
    question = (
        db.query(Question)
        .filter(
            Question.term_id == term.id,
            Question.phase == phase,
            Question.construct_key == construct_key,
            Question.variant_key == variant_key,
        )
        .one_or_none()
    )
    if not question:
        question = Question(
            term_id=term.id,
            phase=phase,
            question_type=question_type,
            body=body,
            expected_answer=expected_answer,
            construct_key=construct_key,
            variant_key=variant_key,
        )
        db.add(question)
        db.flush()
    question.question_type = question_type
    question.body = body
    question.expected_answer = expected_answer
    question.construct_key = construct_key
    question.variant_key = variant_key
    question.is_active = True
    if options is not None:
        _sync_options(db, question, options)
    return question


def seed_database(db: Session) -> None:
    active_slugs = {item["slug"] for item in SEED_TERMS}
    active_question_ids = set()
    bank_items = [
        (mode, index, item)
        for mode in (STANDARD, EASY)
        for index, item in enumerate(SEED_TERMS if mode == STANDARD else seed_terms(mode), start=1)
    ]
    for mode, index, item in bank_items:
        term = db.query(Term).filter(Term.slug == item["slug"]).one_or_none()
        if not term:
            term = Term(
                slug=item["slug"],
                label=item["label"],
                description=item["description"],
                display_order=index,
            )
            db.add(term)
            db.flush()
        term.label = item["label"]
        term.description = item["description"]
        term.display_order = index
        term.is_active = True

        if mode == STANDARD:
            from app.services.split_assessment import split_specs
            for phase, rounds in (("pretest", ["pretest_v1"]), ("retest", ["retest_v1", "retest_v2"])):
                for round_key in rounds:
                    for spec in split_specs(term.slug, round_key, bank_version=ASSESSMENT_BANK_VERSIONS[mode]):
                        question = _upsert_question(db, term, phase=phase, question_type="split_single", body=spec["body"], expected_answer="A", construct_key=assessment_construct_key(term.slug, phase, mode), variant_key=spec["variant_key"], options=spec["options"])
                        active_question_ids.add(question.id)
            continue

        for phase in ("pretest", "retest"):
            variants = item["questions"][phase] if phase == "retest" else [item["questions"]["pretest"]]
            for qd in variants:
                question = _upsert_question(
                    db,
                    term,
                    phase=phase,
                    question_type="multi_select" if phase == "pretest" else "retest_multi_select",
                    body=qd["body"],
                    expected_answer=qd["expected"],
                    construct_key=assessment_construct_key(item["slug"], phase, mode),
                    variant_key=qd["variant_key"],
                    options=qd["options"],
                )
                active_question_ids.add(question.id)

        final_q = item["questions"].get("final_test")
        if final_q:
            question = _upsert_question(
                db,
                term,
                phase="final_test",
                question_type="final_multi_select",
                body=final_q["body"],
                expected_answer=final_q["expected"],
                construct_key=assessment_construct_key(item["slug"], "final_test", mode),
                variant_key=final_q["variant_key"],
                options=final_q["options"],
            )
            active_question_ids.add(question.id)

    for term in db.query(Term).all():
        if term.slug not in active_slugs:
            term.is_active = False
            db.query(Question).filter(Question.term_id == term.id).update({Question.is_active: False}, synchronize_session=False)
    db.query(Question).filter(~Question.id.in_(active_question_ids)).update({Question.is_active: False}, synchronize_session=False)
    db.commit()


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
