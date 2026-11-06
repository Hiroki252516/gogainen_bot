"""Explicit retired-bank fixtures; fresh databases contain only active banks."""

from app.core.question_sets import assessment_construct_key
from app.models import Term
from app.seed.content_loader import load_content, _assessment_options
from app.seed.seed_questions import _upsert_question


def seed_scenario_bank(db):
    bank = load_content()
    for item in bank["terms"]:
        term = db.query(Term).filter_by(slug=item["slug"]).one()
        for phase in ("pretest", "retest"):
            for variant in item["questions"][phase]:
                row = _upsert_question(
                    db, term, phase=phase, question_type="multi_select",
                    body=f"{variant['scenario']}\n\n{variant['task']}", expected_answer="A、B、C",
                    construct_key=assessment_construct_key(term.slug, phase, bank_version=bank["assessment_bank_version"]),
                    variant_key=variant["variant_key"],
                    options=[(o["label"], o["body"], o["is_correct"], o["misconception_type"]) for o in _assessment_options(variant)],
                )
                row.is_active = False
    db.commit()
