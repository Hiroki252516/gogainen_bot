"""Import the supplied split-question drafts without activating them."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

TERMS = ("llm_knowledge", "multi_agent", "memory_process")
CHOICE_ROLES = {"正解": "correct", "M1": "M1", "M3": "M3", "わからない": "unknown"}


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
            item = {"number": int(match.group(1)), "title": match.group(2), "task": "", "choices": {}}
            section["questions"].append(item)
            continue
        if in_scenario:
            scenario_lines.append(raw.rstrip())
            continue
        match = re.match(r"- ([ABCD])【(正解|M1|M3|わからない)】(.*)", line)
        if match and item is not None:
            label, role, body = match.groups()
            item["choices"][CHOICE_ROLES[role]] = {"label": label, "body": body.strip()}
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
            if not section["scenario"] or [q["number"] for q in section["questions"]] != [1, 2, 3]:
                raise ValueError(f"{phase}.{term} must have a scenario and three questions")
            for question in section["questions"]:
                choices = question["choices"]
                if not question["task"] or set(choices) != set(CHOICE_ROLES.values()):
                    raise ValueError(f"{phase}.{term}.{question['number']} has incomplete choices")
                if [choices[role]["label"] for role in ("correct", "M1", "M3", "unknown")] != list("ABCD"):
                    raise ValueError(f"{phase}.{term}.{question['number']} has incorrect labels")
                bodies = [choice["body"] for choice in choices.values()]
                if any(not body for body in bodies) or len(set(bodies)) != 4:
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
