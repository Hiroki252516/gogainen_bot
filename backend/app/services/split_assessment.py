"""Split-assessment content and grading, separate from historical ten-choice banks."""

from __future__ import annotations

from collections import Counter
from typing import Any
from pathlib import Path
from functools import lru_cache

import yaml

from app.seed.import_split_assessment_draft import validate


TERMS = ("llm_knowledge", "multi_agent", "memory_process")
ROLES = ("correct", "M1", "M3", "unknown")


def uses_split(participant: Any) -> bool:
    return participant.question_set_mode in {None, "standard"} and participant.experiment_spec_version == 27


@lru_cache
def split_bank() -> dict:
    path = Path(__file__).parents[1] / "seed/content/standard/split_assessment_v1.yml"
    rounds = yaml.safe_load(path.read_text(encoding="utf-8"))["rounds"]
    validate(rounds)
    return rounds


def split_specs(term_slug: str, round_key: str) -> list[dict]:
    section = split_bank()[round_key][term_slug]
    return [
        {"variant_key": f"{round_key}_q{q['number']}", "question_number": q["number"],
         "body": f"{section['scenario']}\n\n設問{q['number']}：{q['title']}\n\n{q['task']}",
         "options": [(q["choices"][role]["label"], q["choices"][role]["body"], role == "correct", None if role == "correct" else role) for role in ROLES]}
        for q in section["questions"] if q["number"] in {1, 2}
    ]


def primary_type(types: list[str | None]) -> str | None:
    return next((kind for kind in ("unknown", "M3", "M1") if kind in types), None)


def latest_failed_attempts(db: Any, participant: Any, term_id: str) -> list:
    from app.models import Attempt, Question
    attempts = db.query(Attempt).filter(Attempt.participant_id == participant.id, Attempt.term_id == term_id, Attempt.is_correct.is_not(None), Attempt.phase.in_(["pretest", "retest", "final_test"])).order_by(Attempt.created_at.desc(), Attempt.id.desc()).all()
    if not attempts:
        return []
    latest = attempts[0]
    return sorted([a for a in attempts if a.phase == latest.phase and a.test_round == latest.test_round and not a.is_correct], key=lambda a: db.get(Question, a.question_id).variant_key)


def learning_spec(db: Any, participant: Any, term: Any) -> dict:
    from app.models import Question, QuestionOption
    from app.services.experiment import _displayed_options
    failed = latest_failed_attempts(db, participant, term.id)
    if not failed:
        raise ValueError("no failed split questions to confirm")
    groups, options = [], []
    for attempt in failed:
        question = db.get(Question, attempt.question_id)
        displayed = attempt.option_order_snapshot or _displayed_options(db, participant, question)
        source = db.query(QuestionOption).filter_by(question_id=question.id).all()
        for option in source:
            options.append({"option_id": option.id, "label": option.option_label, "body": option.body, "is_correct": option.is_correct, "misconception_type": option.misconception_type, "question_id": question.id})
        groups.append({"question_id": question.id, "body": attempt.question_body_snapshot or question.body, "options": displayed})
    return {"body": "\n\n".join(g["body"] for g in groups), "question_type": "split_confirmation", "selection_mode": "grouped_single", "min_selections": len(groups), "max_selections": len(groups), "questions": groups, "options": options, "expected_answer": "", "variant_key": "split_confirmation"}


def validate_confirmation(spec: dict, selected: list[dict]) -> None:
    if len(selected) != len(spec["questions"]) or Counter(o["question_id"] for o in selected) != Counter(g["question_id"] for g in spec["questions"]):
        raise ValueError("select exactly one option for each confirmation question")


CORRECTION_DRAFTS = {
    ("llm_knowledge", 1): ("資料を検索して回答時に渡す処理と、訓練で重みを変える処理は別です。最新版の資料を渡すだけで出力の正確さが保証されるわけではなく、必要な条件や注意点を確認します。", "資料を差し替えても重みは変わらず、回答時に新しい資料を取得する必要があります。"),
    ("llm_knowledge", 2): ("入力の指示や例を工夫すると回答を調整できますが、その操作だけで重みは更新されません。指示文は、文書を保存・検索する機構そのものではありません。", "表形式の指示で出力が変わることと、回答例を使う訓練で重みが変わることを区別します。"),
    ("multi_agent", 1): ("目的と判断を担う担当を分けて役割を設定します。担当は異なる結論や候補を出せるため、必要に応じて見直します。回答の見出しを分けるだけでは複数の担当主体にはなりません。", "調査担当が返した候補を計画担当が条件に照らして変更しても、役割分担は成立します。"),
    ("multi_agent", 2): ("担当の役割を決めるだけで結果が自動共有されるわけではありません。次の担当に必要な情報を渡す処理を設計します。資料や検索ツールは、目的を持って判断する担当主体とは区別します。", "検索結果の一覧を調査担当が整理し、その結果を計画担当が利用する流れを設計します。"),
    ("memory_process", 1): ("利用者ごとに必要な要点を保存し、次の相談で取り出して入力へ渡します。会話の全文保存が必須ではなく、保存するだけで自動的に参照されるわけでもありません。重みの追加訓練とは別の処理です。", "希望を短く保存しても、次回に関連する記録を取得すれば回答へ反映できます。"),
    ("memory_process", 2): ("希望が変わったら新旧の記録を照合し、現在有効な希望を判断して更新します。一般資料の検索やAIの提案履歴は、本人の現在の希望の管理と同じものではありません。", "古い電話希望と新しいメール希望がある場合、変更の記録を使って現在の希望をメールとして管理します。"),
}


def generation_scope(db: Any, participant: Any, term: Any) -> tuple[dict, list[dict], list[dict]]:
    from app.models import Question
    from app.services.experiment import _selected_options
    failed = latest_failed_attempts(db, participant, term.id)
    kind = primary_type([a.misconception_type for a in failed])
    topics, history, targets = [], [], []
    for attempt in failed:
        question = db.get(Question, attempt.question_id)
        correction, example = CORRECTION_DRAFTS[(term.slug, int(question.variant_key.rsplit("_q", 1)[1]))]
        topic = question.body.split("\n\n設問", 1)[-1].split("\n\n", 1)[0]
        topics.append(topic)
        if kind == "unknown":
            continue
        selected = _selected_options(db, attempt)
        for option in selected:
            history.append({"source_type": "test", "phase": attempt.phase, "test_round": attempt.test_round, "question_body": topic, "is_correct": False, "selected_options": [{"label": option.option_label, "body": option.body}]})
            targets.append({"claim_id": f"{question.id}:{option.id}", "term_slug": term.slug, "option_label": option.option_label, "observed_claim": option.body, "corrected_claim": correction, "mechanism_explanation": correction, "contrast_example": example, "misconception_type": option.misconception_type, "wrong_category": option.body, "correct_category": correction, "boundary_criterion": correction, "evidence_source": "latest_test_selected_option", "interpretation": "observed_choice_not_confirmed_belief"})
    return {"topics": topics, "selected_errors": [o for row in history for o in row["selected_options"]]}, history, targets


def score_split_batch(questions: list[dict[str, Any]], selections: dict[str, str]) -> dict[str, Any]:
    """Score a complete batch and derive term-level teaching targets.

    Question and option IDs must be stable internal identifiers, not display labels.
    """
    if len(questions) != 6 or Counter(q.get("term_slug") for q in questions) != Counter({term: 2 for term in TERMS}):
        raise ValueError("a batch must contain exactly two questions for each term")
    if any({q.get("question_number") for q in questions if q.get("term_slug") == term} != {1, 2} for term in TERMS):
        raise ValueError("only questions one and two may be scored")
    ids = [str(q.get("question_id") or "") for q in questions]
    if "" in ids or len(set(ids)) != 6 or set(selections) != set(ids):
        raise ValueError("a batch requires exactly one selection for each question")

    results = []
    for question, question_id in zip(questions, ids, strict=True):
        options = question.get("options") or []
        if len(options) != 4 or Counter(option.get("role") for option in options) != Counter(ROLES):
            raise ValueError("a question must contain exactly one option per role")
        option_ids = [str(option.get("option_id") or "") for option in options]
        if "" in option_ids or len(set(option_ids)) != 4:
            raise ValueError("option IDs must be nonempty and unique within a question")
        selected = [option for option in options if str(option["option_id"]) == selections[question_id]]
        if len(selected) != 1:
            raise ValueError("selection does not belong to its question")
        option = selected[0]
        results.append({
            "question_id": question_id,
            "term_slug": question["term_slug"],
            "selected_option_id": str(option["option_id"]),
            "selected_body": option.get("body", ""),
            "role": option["role"],
            "is_correct": option["role"] == "correct",
        })

    targets = []
    for term in TERMS:
        failed = [result for result in results if result["term_slug"] == term and not result["is_correct"]]
        if not failed:
            continue
        roles = {result["role"] for result in failed}
        diagnosis = next(role for role in ("unknown", "M3", "M1") if role in roles)
        targets.append({
            "term_slug": term,
            "diagnosis": diagnosis,
            "confirmation_question_ids": [result["question_id"] for result in failed],
            # Unknown suppresses all wrong-choice evidence for the term.
            "selected_errors": [] if diagnosis == "unknown" else [result for result in failed if result["role"] in {"M1", "M3"}],
        })
    return {"results": results, "correct_count": sum(result["is_correct"] for result in results), "total": 6, "targets": targets}
