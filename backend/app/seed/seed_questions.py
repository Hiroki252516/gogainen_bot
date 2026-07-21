from sqlalchemy.orm import Session

from app.db.session import SessionLocal, init_db
from app.models import Question, QuestionOption, Term
from app.seed.data import SEED_TERMS


def _sync_options(db: Session, question: Question, options: list[tuple[str, str, bool, str | None]]) -> None:
    existing = {option.option_label: option for option in db.query(QuestionOption).filter(QuestionOption.question_id == question.id).all()}
    keep_labels = set()
    for order, (label, body, is_correct, misconception_type) in enumerate(options, start=1):
        keep_labels.add(label)
        option = existing.get(label)
        if not option:
            option = QuestionOption(question_id=question.id, option_label=label)
            db.add(option)
        option.body = body
        option.is_correct = is_correct
        option.misconception_type = misconception_type
        option.default_order = order
    for label, option in existing.items():
        if label not in keep_labels:
            db.delete(option)


def _upsert_question(
    db: Session,
    term: Term,
    *,
    phase: str,
    question_type: str,
    body: str,
    expected_answer: str,
    expected_keywords: list[str],
    construct_key: str,
    variant_key: str,
    options: list[tuple[str, str, bool, str | None]] | None = None,
) -> Question:
    question = (
        db.query(Question)
        .filter(
            Question.term_id == term.id,
            Question.phase == phase,
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
            expected_keywords=expected_keywords,
            construct_key=construct_key,
            variant_key=variant_key,
        )
        db.add(question)
        db.flush()
    question.question_type = question_type
    question.body = body
    question.expected_answer = expected_answer
    question.expected_keywords = expected_keywords
    question.construct_key = construct_key
    question.variant_key = variant_key
    question.is_active = True
    if options is not None:
        _sync_options(db, question, options)
    return question


def seed_database(db: Session) -> None:
    active_slugs = {item["slug"] for item in SEED_TERMS}
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

        for phase in ("pretest", "retest"):
            qd = item["questions"]["pretest"]
            _upsert_question(
                db,
                term,
                phase=phase,
                question_type="multi_select" if phase == "pretest" else "retest_multi_select",
                body=qd["body"],
                expected_answer=qd["expected"],
                expected_keywords=item["keywords"],
                construct_key=f"{item['slug']}_definition",
                variant_key=f"{phase}_v1",
                options=qd["options"],
            )

        _upsert_question(
            db,
            term,
            phase="l0_check",
            question_type="l0_free_response",
            body=item["questions"].get("l0") or f"{item['label']}について、ヒントなしで説明してください。理由も書いてください。",
            expected_answer=item["questions"]["pretest"]["expected"],
            expected_keywords=item["keywords"],
            construct_key=f"{item['slug']}_l0_check",
            variant_key="l0_check_v1",
        )

        final_q = item["questions"].get("pretest")
        if final_q:
            _upsert_question(
                db,
                term,
                phase="final_test",
                question_type="final_multi_select",
                body=final_q["body"],
                expected_answer=final_q["expected"],
                expected_keywords=item["keywords"],
                construct_key=f"{item['slug']}_final_test",
                variant_key="final_test_v1",
                options=final_q["options"],
            )

        _upsert_question(
            db,
            term,
            phase="transfer",
            question_type="transfer",
            body=item["questions"]["transfer"],
            expected_answer=item["questions"]["pretest"]["expected"],
            expected_keywords=item["keywords"],
            construct_key=f"{item['slug']}_transfer",
            variant_key="transfer_v1",
        )

    for term in db.query(Term).all():
        if term.slug not in active_slugs:
            term.is_active = False
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
