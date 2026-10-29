"""Descriptive metrics for the six hypotheses; no imputation or significance tests."""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

from sqlalchemy.orm import Session

from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID, assert_current_experiment
from app.core.question_sets import STANDARD, question_set_mode
from app.models import Attempt, Participant, ParticipantSurvey, Term, TutorSession, TutorTurn
from app.services.split_assessment import uses_split, split_item_keys
from app.services.research_protocol import MATERIAL_RATING_KEYS, SURVEY_VERSION

METRICS_VERSION = "six-hypotheses-v3-split"
TERM_SLUGS = ("llm_knowledge", "multi_agent", "memory_process")


def _stats(values, total=None):
    values = [v for v in values if v is not None]
    return {"n": len(values), "missing_count": max(0, total - len(values)) if total is not None else 0,
            "mean": mean(values) if values else None, "median": median(values) if values else None}


def _round_number(attempt):
    if attempt.phase == "pretest":
        return 0
    if attempt.phase == "final_test":
        return 1
    # Reusing variant5 does not turn later test opportunities into the same round.
    try:
        return int((attempt.test_round or "retest_1").split("_")[-1]) + max(0, attempt.attempt_index - 1)
    except (ValueError, TypeError):
        return None


def participant_metrics(db: Session, participant: Participant) -> dict:
    assert_current_experiment(participant)
    terms = {t.id: t.slug for t in db.query(Term).filter(Term.slug.in_(TERM_SLUGS)).all()}
    grouped = defaultdict(list)
    split = uses_split(participant)
    expected_count = 6 if split else 3
    attempts = db.query(Attempt).filter(
        Attempt.participant_id == participant.id,
        Attempt.term_id.in_(terms),
        Attempt.phase.in_(("pretest", "retest", "final_test")),
    ).all()
    question_keys = split_item_keys(db, attempts) if split else {}
    def item_key(attempt):
        return question_keys[attempt.question_id] if split else attempt.term_id
    for attempt in attempts:
        grouped[_round_number(attempt)].append(attempt)

    def complete(items):
        return len(terms) == 3 and len(items) == expected_count and len({item_key(a) for a in items}) == expected_count and {a.term_id for a in items} == set(terms) and all(a.is_correct is not None for a in items)

    baseline = grouped.get(0, [])
    initial = grouped.get(1, [])
    pre_complete = complete(baseline)
    paired_complete = pre_complete and complete(initial)
    pre_score = sum(a.is_correct is True for a in baseline) / expected_count if pre_complete else None
    initial_error_terms = {item_key(a): a.misconception_type for a in baseline if a.misconception_type in {"M1", "M3"}}

    def recurrence(items):
        if pre_complete and not initial_error_terms:
            return {"status": "not_applicable_no_initial_m1_m3", "value": None, "numerator": 0, "denominator": 0}
        if not (pre_complete and complete(items)):
            return {"status": "missing_paired_tests", "value": None, "numerator": None, "denominator": len(initial_error_terms)}
        numerator = sum(a.misconception_type == initial_error_terms.get(item_key(a)) for a in items if item_key(a) in initial_error_terms)
        denominator = len(initial_error_terms)
        return {"status": "observed" if denominator else "not_applicable_no_initial_m1_m3",
                "value": numerator / denominator if denominator else None,
                "numerator": numerator, "denominator": denominator}

    rounds = []
    first_mastery_at = None
    first_mastery_round = None
    for number in sorted(n for n in grouped if n is not None and n > 0):
        items = grouped[number]
        done = complete(items)
        score = sum(a.is_correct is True for a in items) / expected_count if done else None
        rounds.append({"round": number, "phase": items[0].phase, "complete": done,
                       "score_rate": score, "gain_pt": (score - pre_score) * 100 if done and pre_complete else None,
                       "recurrence": recurrence(items)})
        if first_mastery_at is None and score == 1:
            first_mastery_at = max(a.updated_at for a in items)
            first_mastery_round = number

    sessions = db.query(TutorSession).filter_by(participant_id=participant.id).all()
    session_ids = [s.id for s in sessions]
    turns_by_session = defaultdict(list)
    for turn in db.query(TutorTurn).filter(TutorTurn.tutor_session_id.in_(session_ids)).all() if session_ids else []:
        turns_by_session[turn.tutor_session_id].append(turn)
    displayed = []
    repetitions = defaultdict(list)
    session_details = []
    for session in sessions:
        turns = turns_by_session[session.id]
        display_times = [t.material_viewed_at for t in turns if t.material_viewed_at is not None]
        if display_times:
            displayed.append((session.id, min(display_times)))
        answered = [t for t in turns if t.learner_response is not None and isinstance((t.grading_json or {}).get("is_sufficient"), bool)]
        if answered and session.term_id in terms:
            wrong = sum((t.grading_json or {})["is_sufficient"] is False for t in answered)
            repetitions[terms[session.term_id]].append(wrong)
            session_details.append({"session_id": session.id, "term_slug": terms[session.term_id],
                                    "wrong_count": wrong, "answered_count": len(answered),
                                    "ended": session.ended_at is not None})
    term_means = {slug: mean(counts) for slug, counts in repetitions.items()}

    survey = db.query(ParticipantSurvey).filter_by(participant_id=participant.id, survey_version=SURVEY_VERSION).order_by(ParticipantSurvey.created_at.desc(), ParticipantSurvey.id.desc()).first()
    ratings = ((survey.responses_json or {}).get("material_ratings") if survey else None) if displayed else None
    ratings = ratings if isinstance(ratings, dict) and all(type(ratings.get(k)) is int and 1 <= ratings[k] <= 10 for k in MATERIAL_RATING_KEYS) else None
    reached = first_mastery_at is not None
    h2_value = sum(shown_at <= first_mastery_at for _, shown_at in displayed) if reached else None
    h1_value = next((r["gain_pt"] for r in rounds if r["round"] == 1), None) if paired_complete else None
    h3_value = mean(term_means.values()) if term_means else None
    censoring_reason = None
    if not reached:
        if participant.completion_reason == "give_up":
            censoring_reason = "give_up"
        elif participant.completion_reason == "completed":
            censoring_reason = "completed_without_mastery"
        elif participant.completion_reason is None and participant.completed_at is None and participant.current_step != "finish":
            censoring_reason = "in_progress"
        else:
            censoring_reason = "other"
    return {
        "metrics_version": METRICS_VERSION, "protocol_id": CURRENT_PROTOCOL_ID,
        "participant_id": participant.id, "display_code": participant.display_code,
        "question_set_mode": question_set_mode(participant.question_set_mode),
        "scoring_unit": "subquestion" if split else "term", "questions_per_test": expected_count,
        "group_condition": participant.group_condition, "completion_reason": participant.completion_reason,
        "route": "initial_perfect_final_test" if pre_score == 1 else "learning_retest" if pre_complete else "pretest_incomplete",
        "has_viewed_material": bool(displayed), "rounds": rounds,
        "h1": {"value": h1_value, "status": "observed" if h1_value is not None else "missing_paired_tests", "pretest_score": pre_score},
        "h2": {"value": h2_value, "status": "attained" if reached else "not_attained",
               "censoring_reason": censoring_reason,
               "observed_session_count": len(displayed), "first_mastery_round": first_mastery_round,
               "first_mastery_at": first_mastery_at.isoformat() if reached else None,
               "attained_without_learning": reached and h2_value == 0},
        "h3": {"value": h3_value, "status": "observed" if term_means else "missing_no_learning_answers" if displayed else "not_applicable_no_learning",
               "term_means": term_means, "sessions": session_details},
        "h4": recurrence(initial),
        "h5": {"value": mean(ratings.values()) if ratings else None, "items": ratings,
               "status": "observed" if ratings else "missing_survey" if displayed else "not_applicable_not_viewed"},
        "h6": {"value": int(reached), "attained": reached},
    }


def current_metrics(db: Session, mode: str = STANDARD) -> list[dict]:
    mode = question_set_mode(mode)
    participants = db.query(Participant).filter_by(experiment_spec_version=CURRENT_EXPERIMENT_SPEC_VERSION,
                                                  protocol_id=CURRENT_PROTOCOL_ID, consent_checked=True).order_by(Participant.created_at, Participant.id).all()
    return [participant_metrics(db, p) for p in participants if question_set_mode(p.question_set_mode) == mode]


def _group(rows):
    n = len(rows)
    result = {"participant_count": n}
    for key in ("h1", "h2", "h3", "h4", "h5", "h6"):
        result[key] = _stats([r[key]["value"] for r in rows], n)
        result[key]["not_applicable_count"] = sum(r[key].get("status", "").startswith("not_applicable") for r in rows)
        result[key]["missing_count"] -= result[key]["not_applicable_count"]
    nonattainers = [r["h2"] for r in rows if not r["h6"]["attained"]]
    result["h2"].update({"not_attained_count": len(nonattainers),
                           "censored_count": len(nonattainers),
                           "censoring_breakdown": {
                               reason: _stats([r["observed_session_count"] for r in nonattainers if r["censoring_reason"] == reason])
                               for reason in ("give_up", "in_progress", "completed_without_mastery", "other")
                           },
                           "observed_nonattainer_sessions": _stats([r["h2"]["observed_session_count"] for r in rows if not r["h6"]["attained"]]),
                           "attained_without_learning_count": sum(r["h2"]["attained_without_learning"] for r in rows)})
    eligible_h4 = [r["h4"] for r in rows if r["h4"]["value"] is not None]
    denom = sum(r["denominator"] for r in eligible_h4)
    numerator = sum(r["numerator"] for r in eligible_h4)
    result["h4"].update({"pooled_numerator": numerator, "pooled_denominator": denom,
                           "pooled_rate": numerator / denom if denom else None})
    result["h5"].update({"viewed_count": sum(r["has_viewed_material"] for r in rows),
                           "items": {k: _stats([(r["h5"]["items"] or {}).get(k) for r in rows if r["has_viewed_material"]], sum(r["has_viewed_material"] for r in rows)) for k in MATERIAL_RATING_KEYS}})
    result["h6"].update({"numerator": sum(r["h6"]["value"] for r in rows), "denominator": n,
                           "rate": mean(r["h6"]["value"] for r in rows) if n else None})
    result["completion_reasons"] = {reason: sum((r["completion_reason"] or "in_progress") == reason for r in rows) for reason in {r["completion_reason"] or "in_progress" for r in rows}}
    result["rounds"] = [
        {"round": number, "gain": _stats([next((rd["gain_pt"] for rd in r["rounds"] if rd["round"] == number), None) for r in rows], n),
         "recurrence": _stats([next((rd["recurrence"]["value"] for rd in r["rounds"] if rd["round"] == number), None) for r in rows], n)}
        for number in sorted({rd["round"] for r in rows for rd in r["rounds"]})
    ]
    return result


def group_metrics(rows: list[dict], mode: str = STANDARD) -> dict:
    mode = question_set_mode(mode)
    rows = [row for row in rows if row.get("question_set_mode", STANDARD) == mode]
    groups = [{"group_condition": group, **_group([r for r in rows if r["group_condition"] == group])} for group in ("control", "proposed")]
    differences = {key: groups[1][key]["mean"] - groups[0][key]["mean"] if all(g[key]["mean"] is not None for g in groups) else None for key in ("h1", "h2", "h3", "h4", "h5", "h6")}
    item_differences = {k: groups[1]["h5"]["items"][k]["mean"] - groups[0]["h5"]["items"][k]["mean"] if all(g["h5"]["items"][k]["mean"] is not None for g in groups) else None for k in MATERIAL_RATING_KEYS}
    routes = {route: [{"group_condition": group, **_group([r for r in rows if r["group_condition"] == group and r["route"] == route])} for group in ("control", "proposed")] for route in ("initial_perfect_final_test", "learning_retest", "pretest_incomplete")}
    return {"metrics_version": METRICS_VERSION, "protocol_id": CURRENT_PROTOCOL_ID, "question_set_mode": mode, "groups": groups,
            "differences_proposed_minus_control": differences, "material_item_differences": item_differences,
            "routes": routes, "descriptive_only": True}


def write_metrics_csv(path: Path, rows: list[dict], *, grouped: bool, mode: str = STANDARD) -> Path:
    """Long-form, spreadsheet-safe numeric exports with denominators and status."""
    fields = ["metrics_version", "protocol_id", "group_condition", "participant_id", "display_code", "route", "metric", "value", "n", "mean", "median", "numerator", "denominator", "missing_count", "not_applicable_count", "status", "details_json"]
    import json
    records = []
    mode = question_set_mode(mode)
    rows = [row for row in rows if row.get("question_set_mode", STANDARD) == mode]
    source = group_metrics(rows, mode)
    if grouped:
        for group in source["groups"]:
            for key in ("h1", "h2", "h3", "h4", "h5", "h6"):
                stats = group[key]
                records.append({"group_condition": group["group_condition"], "metric": key, **{k: v for k, v in stats.items() if k in fields}, "details_json": json.dumps(stats, ensure_ascii=False)})
            for item, stats in group["h5"]["items"].items():
                records.append({"group_condition": group["group_condition"], "metric": f"h5.{item}", **stats})
        for key, value in source["differences_proposed_minus_control"].items():
            records.append({"group_condition": "proposed_minus_control", "metric": key, "value": value})
        # Includes route-specific and round-specific denominators without changing fixed log CSVs.
        records.append({"metric": "group_details", "details_json": json.dumps(source, ensure_ascii=False)})
    else:
        for row in rows:
            base = {k: row[k] for k in ("group_condition", "participant_id", "display_code", "route")}
            for key in ("h1", "h2", "h3", "h4", "h5", "h6"):
                metric = row[key]
                records.append({**base, "metric": key, **{k: v for k, v in metric.items() if k in fields}, "details_json": json.dumps(metric, ensure_ascii=False)})
            for item, value in (row["h5"]["items"] or {}).items():
                records.append({**base, "metric": f"h5.{item}", "value": value, "status": "observed"})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in records:
            details = json.loads(record.get("details_json") or "{}")
            record["details_json"] = json.dumps({**details, "question_set_mode": mode}, ensure_ascii=False)
            writer.writerow({"metrics_version": METRICS_VERSION, "protocol_id": CURRENT_PROTOCOL_ID, **record})
    return path
