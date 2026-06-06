from sqlalchemy.orm import Session

from app.db.session import SessionLocal, init_db
from app.models import Question, QuestionOption, Term
from app.seed.data import SEED_TERMS


def seed_database(db: Session) -> None:
    active_slugs = {item["slug"] for item in SEED_TERMS}
    for term in db.query(Term).all():
        term.is_active = term.slug in active_slugs

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
        else:
            term.label = item["label"]
            term.description = item["description"]
            term.display_order = index
            term.is_active = True

        for phase in ("pretest", "retest"):
            qd = item["questions"][phase]
            construct_key = f"{item['slug']}_definition"
            variant_key = "pretest_v1" if phase == "pretest" else "retest_temporary_v1"
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
                    question_type="definition" if phase == "pretest" else "retest_same_construct",
                    body=qd["body"],
                    expected_answer=qd["expected"],
                    expected_keywords=item["keywords"],
                    construct_key=construct_key,
                    variant_key=variant_key,
                )
                db.add(question)
                db.flush()
            else:
                question.question_type = "definition" if phase == "pretest" else "retest_same_construct"
                question.body = qd["body"]
                question.expected_answer = qd["expected"]
                question.expected_keywords = item["keywords"]
                question.construct_key = construct_key
                question.variant_key = variant_key
                question.is_active = True
            existing_options = {
                option.option_label: option
                for option in db.query(QuestionOption).filter(QuestionOption.question_id == question.id).all()
            }
            for order, (label, body, is_correct, misconception_type) in enumerate(qd["options"], start=1):
                option = existing_options.get(label)
                if not option:
                    db.add(
                        QuestionOption(
                            question_id=question.id,
                            option_label=label,
                            body=body,
                            is_correct=is_correct,
                            misconception_type=misconception_type,
                            default_order=order,
                        )
                    )
                else:
                    option.body = body
                    option.is_correct = is_correct
                    option.misconception_type = misconception_type
                    option.default_order = order

            valid_labels = {label for label, *_ in qd["options"]}
            for label, option in existing_options.items():
                if label not in valid_labels:
                    option.body = f"[inactive seed option] {option.body}"
                    option.is_correct = False
                    option.misconception_type = "unknown"
                    option.default_order = 999

        for phase, qtype in (("l0_check", "l0_free_response"), ("transfer", "transfer")):
            variant_key = "l0_temporary_v1" if phase == "l0_check" else "transfer_temporary_v1"
            question = (
                db.query(Question)
                .filter(
                    Question.term_id == term.id,
                    Question.phase == phase,
                    Question.variant_key == variant_key,
                )
                .one_or_none()
            )
            body = item["questions"]["transfer"] if phase == "transfer" else item["questions"]["l0"]
            if not question:
                db.add(
                    Question(
                        term_id=term.id,
                        phase=phase,
                        question_type=qtype,
                        body=body,
                        expected_answer=item["questions"]["pretest"]["expected"],
                        expected_keywords=item["keywords"],
                        construct_key=f"{item['slug']}_{phase}",
                        variant_key=variant_key,
                    )
                )
            else:
                question.question_type = qtype
                question.body = body
                question.expected_answer = item["questions"]["pretest"]["expected"]
                question.expected_keywords = item["keywords"]
                question.construct_key = f"{item['slug']}_{phase}"
                question.variant_key = variant_key
                question.is_active = True
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
