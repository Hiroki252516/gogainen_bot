"""Import the supplied split-question drafts without activating them."""

from __future__ import annotations

import argparse
from collections import Counter
import re
from pathlib import Path

import yaml

TERMS = ("llm_knowledge", "multi_agent", "memory_process")
CHOICE_ROLES = {"正解": "correct", "M1": "M1", "M3": "M3", "わからない": "unknown"}
ROLE_COUNTS = (
    Counter({"correct": 1, "M1": 1, "M3": 1, "unknown": 1}),
    Counter({"correct": 1, "M1": 2, "M3": 2, "unknown": 1}),
)


def _choice_entries(choices: object) -> list[dict]:
    if isinstance(choices, dict):
        if any(not isinstance(choice, dict) for choice in choices.values()):
            raise ValueError("role-map choices must contain choice objects")
        return [{"role": role, **choice} for role, choice in choices.items()]
    if isinstance(choices, list):
        if any(not isinstance(choice, dict) for choice in choices):
            raise ValueError("ordered choices must contain choice objects")
        return choices
    raise ValueError("choices must be a role map or an ordered choice list")


def parse_draft(text: str, initial_phase: str) -> dict:
    phases: dict[str, dict] = {}
    phase = initial_phase
    term = None
    section = None
    item = None
    in_scenario = False
    scenario_lines: list[str] = []

    def finish_scenario() -> None:
        nonlocal in_scenario
        if in_scenario:
            section["scenario"] = "\n".join(scenario_lines).strip()
            in_scenario = False

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## 検討が必要な点"):
            break
        match = re.match(r"再テスト([12])：", line)
        if match:
            finish_scenario()
            phase = f"retest_v{match.group(1)}"
            continue
        match = re.match(r"(?:## )?問題([123])：", line)
        if match:
            finish_scenario()
            term = TERMS[int(match.group(1)) - 1]
            section = phases.setdefault(phase, {}).setdefault(term, {"scenario": "", "questions": []})
            continue
        if line in {"共通の場面", "### 共通の場面"}:
            in_scenario = True
            scenario_lines = []
            continue
        match = re.match(r"(?:### )?設問([123])：(.+)", line)
        if match and section is not None:
            finish_scenario()
            item = {"number": int(match.group(1)), "title": match.group(2), "task": "", "choices": []}
            section["questions"].append(item)
            continue
        if in_scenario:
            scenario_lines.append(raw.rstrip())
            continue
        match = re.match(r"- ([ABCDEF])【(正解|M1|M3|わからない)】(.*)", line)
        if match and item is not None:
            label, role, body = match.groups()
            item["choices"].append({"role": CHOICE_ROLES[role], "label": label, "body": body.strip()})
        elif item is not None and line and not item["task"]:
            item["task"] = line
    finish_scenario()
    return phases


def validate(draft: dict) -> None:
    if set(draft) != {"pretest_v1", "retest_v1", "retest_v2"}:
        raise ValueError("draft must contain the three test rounds")
    for phase, terms in draft.items():
        if set(terms) != set(TERMS):
            raise ValueError(f"{phase} must contain all three terms")
        for term, section in terms.items():
            numbers = [q["number"] for q in section["questions"]]
            standalone = section.get("presentation") == "standalone"
            if (not section["scenario"] and not standalone) or (standalone and section["scenario"]) or numbers not in ([1], [1, 2, 3]):
                raise ValueError(f"{phase}.{term} must have a scenario or standalone presentation and question 1 only or questions 1, 2, and 3")
            for question in section["questions"]:
                choices = question["choices"]
                if not question["task"]:
                    raise ValueError(f"{phase}.{term}.{question['number']} has incomplete choices")
                entries = _choice_entries(choices)
                roles = Counter(entry.get("role") for entry in entries)
                expected_labels = list("ABCD") if roles == ROLE_COUNTS[0] else list("ABCDEF") if roles == ROLE_COUNTS[1] else None
                if expected_labels is None or [entry.get("label") for entry in entries] != expected_labels:
                    raise ValueError(f"{phase}.{term}.{question['number']} has incorrect labels")
                if any(entry.get("role") not in CHOICE_ROLES.values() for entry in entries):
                    raise ValueError(f"{phase}.{term}.{question['number']} has an unsupported choice role")
                bodies = [entry.get("body") for entry in entries]
                if any(not isinstance(body, str) or not body.strip() for body in bodies) or len(set(bodies)) != len(entries):
                    raise ValueError(f"{phase}.{term}.{question['number']} has empty or duplicate choices")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pretest", type=Path)
    parser.add_argument("retests", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    draft = parse_draft(args.pretest.read_text(encoding="utf-8"), "pretest_v1")
    draft.update(parse_draft(args.retests.read_text(encoding="utf-8"), "retest_v1"))
    validate(draft)
    args.output.write_text(yaml.safe_dump({"status": "draft_not_active", "rounds": draft}, allow_unicode=True, sort_keys=False), encoding="utf-8")


if __name__ == "__main__":
    main()
