from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token


@dataclass(frozen=True)
class MaterialSection:
    index: int
    heading: str
    heading_line: int
    body: str


def _visible_text(token: Token) -> str:
    return "".join(
        "\n" if child.type in {"softbreak", "hardbreak"} else child.content
        for child in token.children or []
        if child.type in {"text", "code_inline", "softbreak", "hardbreak"}
    )


def parse_material(message: str) -> tuple[list[MaterialSection], list[str]]:
    """Use rendered Markdown blocks, not heading-like text inside code/quotes."""
    tokens = MarkdownIt("commonmark").parse(message)
    sections: list[MaterialSection] = []
    missing: list[str] = []
    heading: tuple[str, int] | None = None
    body: list[str] = []

    def finish_section() -> None:
        if heading is not None:
            sections.append(MaterialSection(len(sections) + 1, *heading, "\n\n".join(body)))

    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            finish_section()
            heading = None
            body = []
            if token.tag == "h3" and token.markup == "###" and token.level == 0:
                heading = (_visible_text(tokens[index + 1]).strip(), token.map[0] + 1)
            elif not (index == 0 and token.tag == "h2" and token.markup == "##" and token.level == 0):
                missing.append(f"tutor_message:unsupported_heading:line_{token.map[0] + 1}")
        elif token.type == "inline" and heading is not None:
            if index > 0 and tokens[index - 1].type == "heading_open":
                continue
            text = _visible_text(token).strip()
            if text:
                body.append(text)
    finish_section()
    return sections, missing


def evidence_sections(message: str, evidence: str) -> list[int]:
    if not isinstance(evidence, str):
        return []
    normalized = normalize_evidence(evidence)
    if not normalized:
        return []
    sections, _ = parse_material(message)
    return [section.index for section in sections if normalized in normalize_evidence(section.body)]


def normalize_evidence(value: str) -> str:
    return re.sub(r"[\s*_`#>\[\]]+", "", value or "")


def validate_material_structure(result: dict[str, Any], term_label: str | None) -> dict[str, Any]:
    message = result.get("tutor_message")
    message = message if isinstance(message, str) else ""
    tokens = MarkdownIt("commonmark").parse(message)
    sections, missing = parse_material(message)
    if (
        not tokens
        or tokens[0].type != "heading_open"
        or tokens[0].tag != "h2"
        or tokens[0].markup != "##"
        or (term_label and _visible_text(tokens[1]).strip() != term_label)
    ):
        missing.append("tutor_message:term_heading_missing")
    if not sections:
        missing.append("tutor_message:sections_missing")
    for section in sections:
        if not section.heading:
            missing.append(f"tutor_message:section_heading_empty:{section.index}")
        if not section.body.strip():
            missing.append(f"tutor_message:section_body_empty:{section.index}")
    if re.search(r"(?<![A-Za-z0-9])(?:M[1-4]|unknown)(?![A-Za-z0-9])", message):
        missing.append("tutor_message:internal_label_exposed")

    evidence_placements = {
        object_name: {
            field: evidence_sections(message, value)
            for field, value in (result.get(object_name) or {}).items()
            if field in evidence_fields and isinstance(value, str) and value.strip()
        }
        for object_name, evidence_fields in (
            ("mandatory_elements", {
                "wrong_belief", "correct_belief", "counterexample", "reason",
                "wrong_category", "correct_category", "boundary_criterion", "contrast_example",
                "definition", "components", "role", "decision_criterion", "positive_example", "non_example",
            }),
            ("teaching_contract", {"corrected_claim", "mechanism_explanation", "contrast_example", "transfer_check"}),
        )
        if isinstance(result.get(object_name), dict)
    }
    return {
        "valid": not missing,
        "missing": missing,
        "section_count": len(sections),
        "headings": [section.heading for section in sections],
        "sections": [
            {"index": section.index, "heading": section.heading, "heading_line": section.heading_line,
             "body_character_count": len(section.body)}
            for section in sections
        ],
        "evidence_placements": evidence_placements,
    }
