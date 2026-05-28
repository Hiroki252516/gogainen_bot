from sqlalchemy.orm import Session

from app.db.session import SessionLocal, init_db
from app.models import Question, QuestionOption, Term
from app.seed.data import SEED_TERMS


def seed_database(db: Session) -> None:
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
        for phase in ("pretest", "retest"):
            qd = item["questions"][phase]
            construct_key = f"{item['slug']}_definition"
            variant_key = f"{phase}_v1"
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
                for order, (label, body, is_correct, misconception_type) in enumerate(qd["options"], start=1):
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
        for phase, qtype in (("l0_check", "l0_free_response"), ("transfer", "transfer")):
            question = (
                db.query(Question)
                .filter(
                    Question.term_id == term.id,
                    Question.phase == phase,
                    Question.variant_key == f"{phase}_v1",
                )
                .one_or_none()
            )
            if not question:
                body = item["questions"]["transfer"] if phase == "transfer" else f"{item['label']}について、ヒントなしで説明してください。理由も書いてください。"
                db.add(
                    Question(
                        term_id=term.id,
                        phase=phase,
                        question_type=qtype,
                        body=body,
                        expected_answer=item["questions"]["pretest"]["expected"],
                        expected_keywords=item["keywords"],
                        construct_key=f"{item['slug']}_{phase}",
                        variant_key=f"{phase}_v1",
                    )
                )
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
