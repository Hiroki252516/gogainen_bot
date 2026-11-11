from sqlalchemy.orm import Session

from app.db.session import SessionLocal, init_db
from app.models import Question, QuestionOption, Term
from app.seed.data import SEED_TERMS
from app.seed.content_loader import four_topic_terms
from app.core.question_sets import ASSESSMENT_BANK_VERSIONS, ASSESSMENT_MODE_BANK_VERSIONS, STANDARD, assessment_construct_key


def _sync_options(
    db: Session,
    question: Question,
    options: list[
        tuple[str, str, bool, str | None]
        | tuple[str, str, bool, str | None, str]
    ],
) -> None:
    existing = {option.option_label: option for option in db.query(QuestionOption).filter(QuestionOption.question_id == question.id).all()}
    for order, entry in enumerate(options, start=1):
        label, body, is_correct, misconception_type = entry[:4]
        rationale = entry[4] if len(entry) == 5 else None
        option = existing.get(label)
        if not option:
            option = QuestionOption(question_id=question.id, option_label=label)
            db.add(option)
        option.body = body
        option.is_correct = is_correct
        option.misconception_type = misconception_type
        if rationale is not None:
            option.rationale = rationale
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
    options: list[
        tuple[str, str, bool, str | None]
        | tuple[str, str, bool, str | None, str]
    ] | None = None,
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
    four_terms = list(four_topic_terms())
    active_slugs = {item["slug"] for item in SEED_TERMS} | {item["slug"] for item in four_terms}
    active_question_ids = set()
    for index, item in enumerate(SEED_TERMS, start=1):
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

        from app.services.split_assessment import split_specs
        bank_versions = {
            ASSESSMENT_MODE_BANK_VERSIONS["application"],
            ASSESSMENT_MODE_BANK_VERSIONS["basic_understanding"],
        }
        for bank_version in bank_versions:
            for phase, rounds in (("pretest", ["pretest_v1"]), ("retest", ["retest_v1", "retest_v2"])):
                for round_key in rounds:
                    for spec in split_specs(term.slug, round_key, bank_version=bank_version):
                        question = _upsert_question(
                            db,
                            term,
                            phase=phase,
                            question_type="split_single",
                            body=spec["body"],
                            expected_answer="A",
                            construct_key=assessment_construct_key(term.slug, phase, bank_version=bank_version),
                            variant_key=spec["variant_key"],
                            options=spec["options"],
                        )
                        active_question_ids.add(question.id)

    from app.services.split_assessment import FOUR_TOPIC_BANK_VERSION, HISTORICAL_FOUR_TOPIC_BANK_VERSION, split_specs
    for bank_version in (HISTORICAL_FOUR_TOPIC_BANK_VERSION, FOUR_TOPIC_BANK_VERSION):
        for index, item in enumerate(four_topic_terms(bank_version), start=len(SEED_TERMS) + 1):
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
            for phase, rounds in (("pretest", ["pretest_v1"]), ("retest", ["retest_v1", "retest_v2"])):
                for round_key in rounds:
                    for spec in split_specs(item["slug"], round_key, bank_version=bank_version):
                        correct_labels = [entry[0] for entry in spec["options"] if entry[2]]
                        question = _upsert_question(
                            db,
                            term,
                            phase=phase,
                            question_type=spec["question_type"],
                            body=spec["body"],
                            expected_answer="、".join(correct_labels),
                            construct_key=assessment_construct_key(item["slug"], phase, bank_version=bank_version),
                            variant_key=spec["variant_key"],
                            options=spec["options"],
                        )
                        if bank_version == FOUR_TOPIC_BANK_VERSION:
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
