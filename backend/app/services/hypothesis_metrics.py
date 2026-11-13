"""Descriptive metrics for the four current hypotheses; no imputation or significance tests."""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

from sqlalchemy.orm import Session

from app.core.experiment_spec import (
    CURRENT_EXPERIMENT_SPEC_VERSION,
    CURRENT_PROTOCOL_ID,
    can_resume,
    assert_current_experiment,
)
from app.models import Attempt, Participant, ParticipantSurvey, Term, TutorSession, TutorTurn
from app.services.split_assessment import uses_split, split_item_keys
from app.services.first_question_only import enabled as first_question_enabled, question_numbers
from app.services.research_protocol import MATERIAL_RATING_KEYS, SURVEY_VERSION
from app.services.test_content_mode import mode_label as test_content_mode_label, participant_mode as participant_test_content_mode
from app.seed.content_loader import ACTIVE_TERM_SLUGS, FOUR_TOPIC_TERM_SLUGS

METRICS_VERSION = "four-hypotheses-v1"
SPEC52_METRICS_PROTOCOLS = {
    "experiment-plan-2026-11-12-four-topic-instruction-tuning-posttest-material-amount-v1": "posttest-5point-v3",
    "experiment-plan-2026-11-12-posttest-system-clarity-removal-v1": "posttest-5point-v4",
}
TERM_SLUGS = ACTIVE_TERM_SLUGS
H4_NUMERIC_KEYS = ("clarity", "readability", "japanese_clarity", "learning_usefulness")
CENTERED_RATING_KEYS = ("difficulty_appropriateness", "amount_appropriateness")
METRICS_CSV_COLUMNS = [
    "metrics_version", "experiment_spec_version", "protocol_id", "survey_version", "test_content_mode",
    "group_condition", "participant_id", "display_code", "route",
    "metric", "value", "n", "mean", "median", "numerator", "denominator", "eligible_count", "missing_count",
    "not_applicable_count", "status", "details_json",
]


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


def _mode_term_slugs(mode: str) -> tuple[str, ...]:
    return FOUR_TOPIC_TERM_SLUGS if mode == "four_topic_fundamentals" else ACTIVE_TERM_SLUGS


def _questions_per_test(mode: str, first_only: bool) -> int:
    if mode == "four_topic_fundamentals":
        return 4
    return 3 if first_only else 6


def metrics_eligible(participant: Participant) -> bool:
    """Allow current participants and the two spec-52 cohorts for analytics only."""
    if can_resume(participant):
        assert_current_experiment(participant)
        return True
    return (
        participant.experiment_spec_version == 52
        and participant.protocol_id in SPEC52_METRICS_PROTOCOLS
    )


def participant_metrics(db: Session, participant: Participant) -> dict:
    if not metrics_eligible(participant):
        assert_current_experiment(participant)
    mode = participant_test_content_mode(participant)
    term_slugs = _mode_term_slugs(mode)
    terms = {t.id: t.slug for t in db.query(Term).filter(Term.slug.in_(term_slugs)).all()}
    grouped = defaultdict(list)
    split = uses_split(participant)
    expected_count = len(term_slugs) * len(question_numbers(participant)) if split else len(term_slugs)
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

    expected_keys = {(term_id, number) for term_id in terms for number in question_numbers(participant)} if split else set(terms)

    def complete(items):
        return len(terms) == len(term_slugs) and len(items) == expected_count and {item_key(a) for a in items} == expected_keys and all(a.is_correct is not None for a in items)

    baseline = grouped.get(0, [])
    initial = grouped.get(1, [])
    pre_complete = complete(baseline)
    paired_complete = pre_complete and complete(initial)
    pre_score = sum(a.is_correct is True for a in baseline) / expected_count if pre_complete else None
    pretest_perfect_early_exit = pre_complete and pre_score == 1
    initial_error_items = {item_key(a): a.misconception_type for a in baseline if a.misconception_type in {"M1", "M3"}}

    def same_type_reselection(items):
        if pretest_perfect_early_exit:
            return {"status": "not_applicable_pretest_mastery", "value": None, "numerator": 0, "denominator": 0}
        if not pre_complete:
            return {"status": "missing_pretest", "value": None, "numerator": None, "denominator": None}
        if not initial_error_items:
            return {"status": "not_applicable_no_initial_m1_m3", "value": None, "numerator": 0, "denominator": 0}
        if not (pre_complete and complete(items)):
            return {"status": "missing_paired_tests", "value": None, "numerator": None, "denominator": len(initial_error_items)}
        numerator = sum(a.misconception_type == initial_error_items.get(item_key(a)) for a in items if item_key(a) in initial_error_items)
        denominator = len(initial_error_items)
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
                       "same_type_reselection": same_type_reselection(items)})
        if first_mastery_at is None and score == 1:
            first_mastery_at = max(a.updated_at for a in items)
            first_mastery_round = number

    displayed = db.query(TutorSession.id).join(TutorTurn).filter(
        TutorSession.participant_id == participant.id,
        TutorTurn.material_viewed_at.is_not(None),
    ).distinct().all()
    expected_survey_version = (
        SURVEY_VERSION
        if can_resume(participant)
        else SPEC52_METRICS_PROTOCOLS[participant.protocol_id]
    )
    survey = db.query(ParticipantSurvey).filter(
        ParticipantSurvey.participant_id == participant.id,
        ParticipantSurvey.phase == "posttest",
        ParticipantSurvey.survey_version == expected_survey_version,
    ).order_by(ParticipantSurvey.created_at.desc(), ParticipantSurvey.id.desc()).first()
    raw_ratings = ((survey.responses_json or {}).get("material_ratings") if survey else None) if displayed else None
    ratings = None
    if isinstance(raw_ratings, dict):
        ratings = {
            key: raw_ratings.get(key)
            if (type(raw_ratings.get(key)) is int and 1 <= raw_ratings[key] <= 5)
            or raw_ratings.get(key) == "not_applicable"
            else None
            for key in MATERIAL_RATING_KEYS
        }
    reached = first_mastery_at is not None
    h1_value = next((r["gain_pt"] for r in rounds if r["round"] == 1), None) if paired_complete else None
    h2 = same_type_reselection(initial)
    h3_applicable = pre_complete and not pretest_perfect_early_exit
    h3_value = int(reached) if h3_applicable else None
    if not displayed:
        h4_status = "not_applicable_not_viewed"
    elif survey is None or ratings is None:
        h4_status = "missing_survey"
    else:
        h4_status = "observed"
    return {
        "metrics_version": METRICS_VERSION, "protocol_id": participant.protocol_id,
        "experiment_spec_version": participant.experiment_spec_version,
        "survey_version": survey.survey_version if survey else expected_survey_version,
        "participant_id": participant.id, "display_code": participant.display_code,
        "scoring_unit": "subquestion" if split else "term", "questions_per_test": expected_count,
        "first_question_only": first_question_enabled(participant),
        "test_content_mode": participant_test_content_mode(participant),
        "test_content_mode_label": test_content_mode_label(participant_test_content_mode(participant)),
        "group_condition": participant.group_condition, "completion_reason": participant.completion_reason,
        "route": "pretest_perfect_early_exit" if pretest_perfect_early_exit else "learning_retest" if pre_complete else "pretest_incomplete",
        "has_viewed_material": bool(displayed), "rounds": rounds,
        "pretest_perfect_early_exit": pretest_perfect_early_exit,
        "h1": {"value": None if pretest_perfect_early_exit else h1_value,
               "status": "not_applicable_pretest_mastery" if pretest_perfect_early_exit else "observed" if h1_value is not None else "missing_paired_tests",
               "pretest_score": pre_score,
               "first_retest_score": next((r["score_rate"] for r in rounds if r["round"] == 1), None)},
        "h2": h2,
        "h3": {"value": h3_value,
               "attained": bool(h3_value) if h3_value is not None else None,
               "status": "observed" if h3_applicable else "not_applicable_pretest_mastery" if pretest_perfect_early_exit else "not_applicable_pretest_incomplete",
               "pretest_score": pre_score,
               "first_mastery_round": first_mastery_round,
               "first_mastery_at": first_mastery_at.isoformat() if reached else None,
               "retest_completed": bool(initial and complete(initial))},
        "h4": {"status": h4_status, "items": ratings,
               "viewed": bool(displayed), "survey_present": survey is not None},
    }


def current_metrics(db: Session) -> list[dict]:
    from sqlalchemy import and_, or_

    spec52_conditions = [
        and_(Participant.experiment_spec_version == 52, Participant.protocol_id == protocol)
        for protocol in SPEC52_METRICS_PROTOCOLS
    ]
    participants = db.query(Participant).filter(
        Participant.consent_checked.is_(True),
        or_(
            and_(Participant.experiment_spec_version == CURRENT_EXPERIMENT_SPEC_VERSION,
                 Participant.protocol_id == CURRENT_PROTOCOL_ID),
            *spec52_conditions,
        ),
    ).order_by(Participant.created_at, Participant.id).all()
    return [participant_metrics(db, participant) for participant in participants]


def _group(rows):
    n = len(rows)
    result = {
        "participant_count": n,
        "pretest_incomplete_count": sum(r.get("route") == "pretest_incomplete" for r in rows),
        "pretest_perfect_early_exit_count": sum(r.get("pretest_perfect_early_exit", r.get("route") == "pretest_perfect_early_exit") for r in rows),
    }
    for key in ("h1", "h2", "h3"):
        result[key] = _stats([r[key]["value"] for r in rows], n)
        result[key]["not_applicable_count"] = sum(r[key].get("status", "").startswith("not_applicable") for r in rows)
        result[key]["missing_count"] -= result[key]["not_applicable_count"]
        result[key]["eligible_count"] = n - result[key]["not_applicable_count"]

    h2_observed = [r["h2"] for r in rows if r["h2"]["value"] is not None]
    h2_numerator = sum(r["numerator"] for r in h2_observed)
    h2_denominator = sum(r["denominator"] for r in h2_observed)
    result["h2"].update({
        "participant_numerator": h2_numerator,
        "participant_denominator": h2_denominator,
        "pooled_rate": h2_numerator / h2_denominator if h2_denominator else None,
        "paired_complete_count": len(h2_observed),
        "no_initial_m1_m3_count": sum(r["h2"]["status"] == "not_applicable_no_initial_m1_m3" for r in rows),
    })

    h3_eligible = [r for r in rows if r["h3"]["status"] == "observed"]
    h3_values = [r["h3"]["value"] for r in h3_eligible]
    result["h3"].update({
        "eligible_count": len(h3_eligible),
        "numerator": sum(h3_values),
        "denominator": len(h3_values),
        "rate": mean(h3_values) if h3_values else None,
        "pretest_incomplete_count": sum(r["h3"]["status"] == "not_applicable_pretest_incomplete" for r in rows),
    })

    viewed_rows = [r for r in rows if r["has_viewed_material"]]
    item_stats = {}
    for key in MATERIAL_RATING_KEYS:
        values = [(row["h4"].get("items") or {}).get(key) for row in viewed_rows]
        numeric_values = [value for value in values if type(value) is int and 1 <= value <= 5]
        not_evaluable_count = sum(value == "not_applicable" for value in values)
        distribution = {str(value): sum(item == value for item in numeric_values) for value in range(1, 6)}
        distribution["not_applicable"] = not_evaluable_count
        distribution["missing"] = len(viewed_rows) - len(numeric_values) - not_evaluable_count
        stats = _stats(numeric_values, len(viewed_rows))
        stats["not_applicable_count"] = not_evaluable_count
        stats["missing_count"] = distribution["missing"]
        stats["distribution"] = distribution
        if key in CENTERED_RATING_KEYS:
            stats["mean"] = None
            stats["median"] = None
        stats["eligible_count"] = len(viewed_rows)
        item_stats[key] = stats
    result["h4"] = {
        "viewed_count": len(viewed_rows),
        "not_viewed_count": sum(not r["has_viewed_material"] for r in rows),
        "missing_survey_count": sum(r["h4"]["status"] == "missing_survey" for r in viewed_rows),
        "items": item_stats,
    }
    for key, stats in item_stats.items():
        stats["not_viewed_count"] = result["h4"]["not_viewed_count"]
        stats["missing_survey_count"] = result["h4"]["missing_survey_count"]
        stats["item_label"] = key
    result["h4"]["numeric_items"] = list(H4_NUMERIC_KEYS)
    result["h4"]["centered_items"] = list(CENTERED_RATING_KEYS)
    result["completion_reasons"] = {reason: sum((r["completion_reason"] or "in_progress") == reason for r in rows) for reason in {r["completion_reason"] or "in_progress" for r in rows}}
    round_numbers = sorted({rd["round"] for r in rows for rd in r["rounds"]})
    result["rounds"] = []
    for number in round_numbers:
        round_items = [next((rd for rd in row["rounds"] if rd["round"] == number), None) for row in rows]
        early_exit_count = sum(bool(row.get("pretest_perfect_early_exit")) for row in rows)
        gain = _stats([rd["gain_pt"] if rd else None for rd in round_items], n)
        gain["not_applicable_count"] = early_exit_count
        gain["eligible_count"] = n - early_exit_count
        gain["missing_count"] = n - early_exit_count - gain["n"]
        reselection_values = [rd["same_type_reselection"]["value"] if rd else None for rd in round_items]
        reselection_na_count = sum(
            bool(row.get("pretest_perfect_early_exit"))
            or bool(round_item and round_item["same_type_reselection"]["status"].startswith("not_applicable"))
            for row, round_item in zip(rows, round_items)
        )
        reselection = _stats(reselection_values, n)
        reselection["not_applicable_count"] = reselection_na_count
        reselection["eligible_count"] = n - reselection_na_count
        reselection["missing_count"] = n - reselection_na_count - reselection["n"]
        result["rounds"].append({"round": number, "gain": gain, "same_type_reselection": reselection})
    return result


def group_metrics(rows: list[dict]) -> dict:
    conditions = sorted({row.get("first_question_only", False) is True for row in rows}) or [True]
    modes = sorted({row.get("test_content_mode") or "application" for row in rows}) or ["application"]
    protocols = sorted({row.get("protocol_id") or CURRENT_PROTOCOL_ID for row in rows}) or [CURRENT_PROTOCOL_ID]
    if len(conditions) > 1 or len(modes) > 1 or len(protocols) > 1:
        strata_keys = sorted({
            (row.get("first_question_only") is True, row.get("test_content_mode") or "application",
             row.get("protocol_id") or CURRENT_PROTOCOL_ID)
            for row in rows
        }) or [(True, "application", CURRENT_PROTOCOL_ID)]
        return {"metrics_version": METRICS_VERSION, "protocol_id": None,
                "groups": [], "routes": {},
                "differences_proposed_minus_control": {}, "h4_item_differences": {},
                "strata": [
                    group_metrics([
                        row for row in rows
                        if (row.get("first_question_only") is True) == condition
                        and (row.get("test_content_mode") or "application") == mode
                        and (row.get("protocol_id") or CURRENT_PROTOCOL_ID) == protocol
                    ])
                    for condition, mode, protocol in strata_keys
                ],
                "descriptive_only": True}
    first_only = conditions[0] if conditions else False
    mode = modes[0] if modes else "application"
    groups = [{"group_condition": group, **_group([r for r in rows if r["group_condition"] == group])} for group in ("control", "proposed")]
    differences = {key: groups[1][key]["mean"] - groups[0][key]["mean"] if all(g[key]["mean"] is not None for g in groups) else None for key in ("h1", "h2", "h3")}
    item_differences = {
        key: groups[1]["h4"]["items"][key]["mean"] - groups[0]["h4"]["items"][key]["mean"]
        if key in H4_NUMERIC_KEYS and all(g["h4"]["items"][key]["mean"] is not None for g in groups)
        else None
        for key in MATERIAL_RATING_KEYS
    }
    routes = {route: [{"group_condition": group, **_group([r for r in rows if r["group_condition"] == group and r["route"] == route])} for group in ("control", "proposed")] for route in ("pretest_perfect_early_exit", "learning_retest", "pretest_incomplete")}
    return {"metrics_version": METRICS_VERSION, "protocol_id": protocols[0],
            "experiment_spec_version": next((row.get("experiment_spec_version") for row in rows), CURRENT_EXPERIMENT_SPEC_VERSION),
            "survey_version": next((row.get("survey_version") for row in rows if row.get("survey_version")), None),
            "groups": groups,
            "test_content_mode": mode, "test_content_mode_label": test_content_mode_label(mode),
            "first_question_only": first_only, "questions_per_test": _questions_per_test(mode, first_only),
            "differences_proposed_minus_control": differences, "h4_item_differences": item_differences,
            "routes": routes, "descriptive_only": True}


def metrics_export_rows(rows: list[dict], *, grouped: bool) -> list[dict]:
    """Return the canonical long-form records used by CSV and Excel exports."""
    import json

    records = []
    source = group_metrics(rows)
    if grouped and source.get("strata"):
        return [record for stratum in source["strata"] for record in metrics_export_rows(
            [row for row in rows
             if (row.get("first_question_only") is True) == stratum["first_question_only"]
             and (row.get("test_content_mode") or "application") == stratum["test_content_mode"]
             and (row.get("protocol_id") or CURRENT_PROTOCOL_ID) == stratum["protocol_id"]],
            grouped=True,
        )]
    if grouped:
        for group in source["groups"]:
            for key in ("h1", "h2", "h3"):
                stats = group[key]
                records.append({"test_content_mode": source["test_content_mode"], "group_condition": group["group_condition"], "metric": key, **{k: v for k, v in stats.items() if k in METRICS_CSV_COLUMNS}, "details_json": json.dumps(stats, ensure_ascii=False)})
            records.append({"test_content_mode": source["test_content_mode"], "group_condition": group["group_condition"], "metric": "h4",
                            "status": "item_level_summary", "details_json": json.dumps(group["h4"], ensure_ascii=False)})
            for item, stats in group["h4"]["items"].items():
                records.append({"test_content_mode": source["test_content_mode"], "group_condition": group["group_condition"], "metric": f"h4.{item}",
                                "n": stats["n"], "mean": stats["mean"], "median": stats["median"],
                                "missing_count": stats["missing_count"], "not_applicable_count": stats["not_applicable_count"],
                                "status": "observed" if stats["n"] else "no_numeric_responses",
                                "details_json": json.dumps(stats, ensure_ascii=False)})
        for key, value in source["differences_proposed_minus_control"].items():
            records.append({"test_content_mode": source["test_content_mode"], "group_condition": "proposed_minus_control", "metric": key, "value": value})
        for key, value in source["h4_item_differences"].items():
            records.append({"test_content_mode": source["test_content_mode"], "group_condition": "proposed_minus_control", "metric": f"h4.{key}", "value": value})
        # Includes route-specific and round-specific denominators without changing fixed log CSVs.
        records.append({"test_content_mode": source["test_content_mode"], "metric": "group_details", "details_json": json.dumps(source, ensure_ascii=False)})
    else:
        for row in rows:
            base = {k: row[k] for k in ("group_condition", "participant_id", "display_code", "route",
                                        "protocol_id", "experiment_spec_version", "survey_version")}
            base["test_content_mode"] = row.get("test_content_mode") or "application"
            base["first_question_only"] = row.get("first_question_only") is True
            for key in ("h1", "h2", "h3"):
                metric = row[key]
                records.append({**base, "metric": key, **{k: v for k, v in metric.items() if k in METRICS_CSV_COLUMNS}, "details_json": json.dumps(metric, ensure_ascii=False)})
            records.append({**base, "metric": "h4", "status": row["h4"]["status"], "details_json": json.dumps(row["h4"], ensure_ascii=False)})
            for item in MATERIAL_RATING_KEYS:
                value = (row["h4"]["items"] or {}).get(item)
                status = "not_viewed" if not row["h4"]["viewed"] else "not_applicable" if value == "not_applicable" else "observed" if type(value) is int else "missing"
                records.append({**base, "metric": f"h4.{item}", "value": value if type(value) is int or value == "not_applicable" else None, "status": status})

    output = []
    for record in records:
        details = json.loads(record.get("details_json") or "{}")
        first_only = record.pop("first_question_only", source.get("first_question_only", False))
        mode = record.get("test_content_mode") or source.get("test_content_mode", "application")
        protocol_id = record.get("protocol_id") or source.get("protocol_id") or CURRENT_PROTOCOL_ID
        survey_version = record.get("survey_version") or source.get("survey_version")
        spec_version = record.get("experiment_spec_version") or source.get("experiment_spec_version", CURRENT_EXPERIMENT_SPEC_VERSION)
        record["details_json"] = json.dumps({
            **details,
            "test_content_mode": mode,
            "first_question_only": first_only,
            "questions_per_test": _questions_per_test(mode, first_only),
            "experiment_spec_version": spec_version,
            "survey_version": survey_version,
        }, ensure_ascii=False)
        output.append({"metrics_version": METRICS_VERSION, "protocol_id": protocol_id,
                       "experiment_spec_version": spec_version, "survey_version": survey_version, **record})
    return output


def write_metrics_csv(path: Path, rows: list[dict], *, grouped: bool) -> Path:
    """Write long-form numeric exports with denominators and status."""
    records = metrics_export_rows(rows, grouped=grouped)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=METRICS_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(records)
    return path
