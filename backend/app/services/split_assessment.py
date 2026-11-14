"""Split-assessment content and grading, separate from historical ten-choice banks."""

from __future__ import annotations

from collections import Counter
import re
from typing import Any
from pathlib import Path
from functools import lru_cache

import yaml
from fastapi import HTTPException

from app.core.question_sets import ASSESSMENT_BANK_VERSIONS, STANDARD
from app.seed.content_loader import four_topic_terms, teaching_target_for_option
from app.seed.import_split_assessment_draft import validate


TERMS = ("llm_knowledge", "multi_agent", "memory_process")
FOUR_TOPIC_BANK_VERSION = "split-actions-four-topic-v4"
PREVIOUS_FOUR_TOPIC_BANK_VERSION = "split-actions-four-topic-v3"
HISTORICAL_FOUR_TOPIC_BANK_VERSION = "split-actions-four-topic-v2"
OLDEST_FOUR_TOPIC_BANK_VERSION = "split-actions-four-topic-v1"
FOUR_TOPIC_BANK_VERSIONS = (
    OLDEST_FOUR_TOPIC_BANK_VERSION,
    HISTORICAL_FOUR_TOPIC_BANK_VERSION,
    PREVIOUS_FOUR_TOPIC_BANK_VERSION,
    FOUR_TOPIC_BANK_VERSION,
)
ROLES = ("correct", "M1", "M3", "unknown")
SPLIT_ROLE_COUNTS = Counter({"correct": 1, "M1": 2, "M3": 2, "unknown": 1})


def split_data_error(code: str = "split_question_unavailable") -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "error_code": code,
            "message": "設問の保存情報に不整合があります。処理を中止しました。管理者に連絡してください。",
        },
    )


def parse_split_variant(value: Any) -> tuple[str, int]:
    match = re.fullmatch(r"(pretest_v1|retest_v[12])_q([12])", value) if isinstance(value, str) else None
    if match is None:
        raise split_data_error()
    return match.group(1), int(match.group(2))


def split_questions_for_attempts(db: Any, attempts: list) -> dict:
    """Load and validate only the referenced questions, including retired rows."""
    from app.models import Question

    ids = {attempt.question_id for attempt in attempts}
    if not ids:
        return {}
    questions = {q.id: q for q in db.query(Question).filter(Question.id.in_(ids)).all()}
    for attempt in attempts:
        question = questions.get(attempt.question_id)
        if question is None or question.term_id != attempt.term_id:
            raise split_data_error()
        round_key, _ = parse_split_variant(question.variant_key)
        expected_phase = "pretest" if attempt.phase == "pretest" else "retest"
        if question.phase != expected_phase or not round_key.startswith(f"{expected_phase}_"):
            raise split_data_error()
    return questions


def split_item_keys(db: Any, attempts: list) -> dict:
    return {
        q.id: (q.term_id, parse_split_variant(q.variant_key)[1])
        for q in split_questions_for_attempts(db, attempts).values()
    }


def require_confirmation_spec(practice: Any) -> dict:
    """Reject damaged snapshots without rebuilding them from a live bank."""
    error = split_data_error("split_confirmation_snapshot_unavailable")
    if not isinstance(practice, dict):
        raise error
    index = practice.get("learning_variant_index", 1)
    if not isinstance(index, int) or isinstance(index, bool) or index not in (1, 2, 3):
        raise error
    if "stage_meta" in practice and not isinstance(practice["stage_meta"], dict):
        raise error
    spec = practice.get("source_spec")
    if not isinstance(spec, dict) or spec.get("selection_mode") not in {"grouped_single", "multiple"}:
        raise error
    groups, options = spec.get("questions"), spec.get("options")
    if not isinstance(groups, list) or not 1 <= len(groups) <= 2 or not isinstance(options, list):
        raise error
    if not isinstance(spec.get("body"), str) or not spec["body"].strip():
        raise error
    group_ids, displayed = set(), []
    for group in groups:
        if not isinstance(group, dict):
            raise error
        question_id, choices = group.get("question_id"), group.get("options")
        if not isinstance(question_id, str) or not question_id or question_id in group_ids:
            raise error
        if not isinstance(group.get("body"), str) or not group["body"].strip():
            raise error
        expected_counts = {10} if spec["selection_mode"] == "multiple" else {4, 6}
        if not isinstance(choices, list) or len(choices) not in expected_counts:
            raise error
        if any(not isinstance(choice, dict) for choice in choices):
            raise error
        expected_labels = list("ABCDEFGHIJ") if len(choices) == 10 else list("ABCD") if len(choices) == 4 else list("ABCDEF")
        if len(choices) != 10 and [choice.get("label") for choice in choices] != expected_labels:
            raise error
        if len(choices) == 10 and (len({choice.get("label") for choice in choices}) != 10 or {choice.get("label") for choice in choices} != set(expected_labels)):
            raise error
        group_ids.add(question_id)
        displayed.extend((question_id, choice) for choice in choices)
    by_id = {}
    for option in options:
        if not isinstance(option, dict):
            raise error
        option_id = option.get("option_id")
        if not isinstance(option_id, str) or not option_id or option_id in by_id:
            raise error
        if not isinstance(option.get("question_id"), str) or option["question_id"] not in group_ids or not isinstance(option.get("is_correct"), bool):
            raise error
        allowed_labels = tuple("ABCDEFGHIJ") if spec["selection_mode"] == "multiple" else tuple("ABCDEF")
        if option.get("label") not in allowed_labels:
            raise error
        kind = option.get("misconception_type")
        if kind not in (None, "M1", "M3", "unknown") or option["is_correct"] != (kind is None):
            raise error
        by_id[option_id] = option
    displayed_ids = []
    for question_id, choice in displayed:
        option_id = choice.get("option_id")
        if not isinstance(option_id, str) or option_id not in by_id:
            raise error
        source = by_id[option_id]
        if source["question_id"] != question_id or not isinstance(choice.get("body"), str) or not choice["body"].strip() or source.get("body") != choice["body"]:
            raise error
        if choice.get("exclusive") is not (source.get("misconception_type") == "unknown"):
            raise error
        displayed_ids.append(option_id)
    if len(displayed_ids) != len(set(displayed_ids)) or set(displayed_ids) != set(by_id):
        raise error
    for question_id in group_ids:
        roles = Counter("correct" if o["is_correct"] else o["misconception_type"] for o in options if o["question_id"] == question_id)
        if roles not in (Counter(ROLES), SPLIT_ROLE_COUNTS, Counter({"correct": 3, "M1": 3, "M3": 3, "unknown": 1})):
            raise error
    if spec["selection_mode"] == "multiple" and (
        len(groups) != 1
        or spec.get("min_selections") != 3
        or spec.get("max_selections") != 3
        or len(options) != 10
    ):
        raise error
    if practice.get("questions") != groups or practice.get("options") != [choice for _, choice in displayed]:
        raise error
    return spec


def uses_split(participant: Any) -> bool:
    version = getattr(participant, "experiment_spec_version", None)
    return isinstance(version, int) and not isinstance(version, bool) and 27 <= version <= 58


@lru_cache
def split_bank(bank_version: str = "split-actions-v5") -> dict:
    bank_paths = {
        "split-actions-v1": "split_assessment_v1.yml",
        "split-actions-v2": "split_assessment_v2.yml",
        "split-actions-v3": "split_assessment_v3.yml",
        "split-actions-v4": "split_assessment_v4.yml",
        "split-actions-v5": "split_assessment_v5.yml",
        "split-actions-v6": "split_assessment_v6.yml",
        "split-actions-basic-v1": "split_assessment_basic_v1.yml",
    }
    filename = bank_paths.get(bank_version)
    if filename is None:
        raise ValueError(f"unsupported split assessment bank: {bank_version}")
    path = Path(__file__).parents[1] / "seed/content/standard" / filename
    rounds = yaml.safe_load(path.read_text(encoding="utf-8"))["rounds"]
    validate(rounds)
    return rounds


def split_specs(term_slug: str, round_key: str, bank_version: str | None = None) -> list[dict]:
    if bank_version in FOUR_TOPIC_BANK_VERSIONS:
        term = next((item for item in four_topic_terms(bank_version) if item["slug"] == term_slug), None)
        if term is None or round_key not in {"pretest_v1", "retest_v1", "retest_v2"}:
            raise ValueError("unsupported four-topic assessment term or round")
        return [{
            "variant_key": f"{round_key}_q1",
            "question_number": 1,
            "body": term["question"],
            "question_type": "multi_select",
            "options": [
                (option["label"], option["body"], option["role"] == "correct", None if option["role"] == "correct" else option["role"])
                for option in term["options"]
            ],
        }]
    section = split_bank(bank_version or ASSESSMENT_BANK_VERSIONS[STANDARD])[round_key][term_slug]
    def choices_for(
        question: dict,
    ) -> list[
        tuple[str, str, bool, str | None]
        | tuple[str, str, bool, str | None, str]
    ]:
        choices = question["choices"]
        entries = (
            [{"role": role, **choices[role]} for role in ROLES]
            if isinstance(choices, dict)
            else choices
        )
        return [
            (choice["label"], choice["body"], choice["role"] == "correct", None if choice["role"] == "correct" else choice["role"])
            + ((choice["rationale"],) if choice.get("rationale") else ())
            for choice in entries
        ]
    return [
        {"variant_key": f"{round_key}_q{q['number']}", "question_number": q["number"],
         "body": "\n\n".join(part for part in (
             section["scenario"].strip(),
             f"設問{q['number']}：{q['title']}",
             q["task"],
         ) if part),
         "options": choices_for(q)}
        for q in section["questions"] if q["number"] in {1, 2}
    ]


def primary_type(types: list[str | None]) -> str | None:
    return next((kind for kind in ("unknown", "M3", "M1") if kind in types), None)


def latest_failed_attempts(db: Any, participant: Any, term_id: str) -> list:
    from app.models import Attempt
    attempts = db.query(Attempt).filter(Attempt.participant_id == participant.id, Attempt.term_id == term_id, Attempt.is_correct.is_not(None), Attempt.phase.in_(["pretest", "retest", "final_test"])).order_by(Attempt.created_at.desc(), Attempt.id.desc()).all()
    if not attempts:
        return []
    questions = split_questions_for_attempts(db, attempts)
    variants = {qid: parse_split_variant(question.variant_key) for qid, question in questions.items()}
    round_names = {"pretest_v1": "test", "retest_v1": "retest_1", "retest_v2": "retest_2"}
    rounds = {}
    for attempt in attempts:
        variant, _ = variants[attempt.question_id]
        expected_round = round_names[variant]
        # Per-question attempt_index is 1 in both retests, so it cannot repair a missing round.
        if attempt.test_round != expected_round or (attempt.phase == "final_test" and variant != "retest_v1"):
            raise split_data_error("split_test_round_unavailable")
        rounds[attempt.id] = expected_round
    # A scored round advances even when wall-clock timestamps tie or move backwards.
    round_order = {"test": 0, "retest_1": 1, "retest_2": 2}
    latest = max(attempts, key=lambda a: (round_order[rounds[a.id]], a.created_at, a.id))
    failed = [a for a in attempts if a.phase == latest.phase and rounds[a.id] == rounds[latest.id] and not a.is_correct]
    return sorted(failed, key=lambda a: variants[a.question_id][1])


def learning_spec(db: Any, participant: Any, term: Any) -> dict:
    from app.models import QuestionOption
    from app.services.experiment import _displayed_options
    failed = latest_failed_attempts(db, participant, term.id)
    if not failed:
        raise ValueError("no failed split questions to confirm")
    questions = split_questions_for_attempts(db, failed)
    groups, options = [], []
    for attempt in failed:
        question = questions[attempt.question_id]
        displayed = attempt.option_order_snapshot or _displayed_options(db, participant, question)
        source = db.query(QuestionOption).filter_by(question_id=question.id).all()
        for option in source:
            options.append({"option_id": option.id, "label": option.option_label, "body": option.body, "is_correct": option.is_correct, "misconception_type": option.misconception_type, "question_id": question.id})
        groups.append({"question_id": question.id, "body": attempt.question_body_snapshot or question.body, "options": displayed})
    if getattr(participant, "test_content_mode", None) == "four_topic_fundamentals":
        if len(groups) != 1 or len(options) != 10:
            raise split_data_error("split_confirmation_snapshot_unavailable")
        return {"body": groups[0]["body"], "question_type": "split_confirmation_multi_select", "selection_mode": "multiple", "min_selections": 3, "max_selections": 3, "questions": groups, "options": options, "expected_answer": "", "variant_key": "split_confirmation"}
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
    from app.services.experiment import _selected_options
    failed = latest_failed_attempts(db, participant, term.id)
    kind = primary_type([a.misconception_type for a in failed])
    topics, history, targets = [], [], []
    questions = split_questions_for_attempts(db, failed)
    for attempt in failed:
        question = questions[attempt.question_id]
        if getattr(participant, "test_content_mode", None) == "four_topic_fundamentals":
            topic = question.body
            topics.append(topic)
            if kind == "unknown":
                continue
            for option in _selected_options(db, attempt):
                if option.is_correct or option.misconception_type not in {"M1", "M3"}:
                    continue
                metadata = teaching_target_for_option(term.slug, option.option_label)
                if not metadata:
                    raise split_data_error("split_correction_unavailable")
                history.append({"source_type": "test", "phase": attempt.phase, "test_round": attempt.test_round, "question_body": topic, "is_correct": False, "selected_options": [{"label": option.option_label, "body": option.body}]})
                targets.append({"claim_id": f"{question.id}:{option.id}", "term_slug": term.slug, "option_label": option.option_label, "observed_claim": option.body, **metadata, "misconception_type": option.misconception_type, "evidence_source": "latest_test_selected_option", "interpretation": "observed_choice_not_confirmed_belief"})
            continue
        correction_draft = CORRECTION_DRAFTS.get((term.slug, parse_split_variant(question.variant_key)[1]))
        if correction_draft is None:
            raise split_data_error("split_correction_unavailable")
        correction, example = correction_draft
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
        if len(options) != 6 or Counter(option.get("role") for option in options) != SPLIT_ROLE_COUNTS:
            raise ValueError("a question must contain one correct, two M1, two M3, and one unknown option")
        option_ids = [str(option.get("option_id") or "") for option in options]
        if "" in option_ids or len(set(option_ids)) != 6:
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
