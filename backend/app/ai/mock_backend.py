from __future__ import annotations

from typing import Any

from app.ai.backend import strategy_for
from app.ai.mandatory_elements import (
    expected_mandatory_type,
    mandatory_element_headings,
    mock_mandatory_elements,
)
from app.ai.teaching_contract import (
    MATERIAL_TARGET_CHARACTERS,
    mock_teaching_contract,
)


class MockAIBackend:
    provider = "mock"


    async def generate_tutoring_turn(self, payload: dict[str, Any]) -> dict[str, Any]:
        term = payload.get("term") or {}
        label = term.get("label", "対象用語")
        description = term.get("description") or f"{label}の基本的な定義と役割を確認します。"
        stage = payload.get("learning_stage") or "conceptual_change"
        group = payload.get("group_condition", "proposed")
        mandatory_type = expected_mandatory_type(payload)
        mandatory_elements = None
        teaching_contract = None
        if mandatory_type:
            target = None
            if mandatory_type in {"M1", "M3"}:
                requested_target = payload.get("pretest_target")
                if (
                    isinstance(requested_target, dict)
                    and requested_target.get("misconception_type") in {None, mandatory_type}
                ):
                    target = requested_target
                else:
                    target = next(
                        (
                            item
                            for item in payload.get("pretest_targets") or []
                            if isinstance(item, dict) and item.get("misconception_type") in {None, mandatory_type}
                        ),
                        None,
                    )
            mandatory_elements = mock_mandatory_elements(label, description, mandatory_type, target)
            headings = mandatory_element_headings(mandatory_type)
            transfer_check = (
                f"新しい例でも、{(target or {}).get('corrected_claim') or description}に当てはまるかを説明します。"
            )
            message = (
                f"## {label}\n\n"
                + "\n\n".join(
                    f"### {headings[field]}\n- {mandatory_elements[field]}"
                    for field in headings
                )
                + f"\n\n### 適用確認\n- {transfer_check}"
            )
            mechanism = (
                (target or {}).get("mechanism_explanation")
                or mandatory_elements.get("reason")
                or mandatory_elements.get("boundary_criterion")
                or mandatory_elements.get("role")
                or "構成要素と役割の関係を確認します。"
            )
            contrast = (target or {}).get("contrast_example") or mandatory_elements.get("counterexample") or mandatory_elements.get("contrast_example")
            if mandatory_type in {"M1", "M3"}:
                message += f"\n- 仕組み: {mechanism}"
                if mandatory_type == "M3" and (target or {}).get("corrected_claim"):
                    message += f"\n- 正しい説明: {(target or {})['corrected_claim']}"
            teaching_contract = mock_teaching_contract(
                mandatory_type,
                target,
                corrected_claim=mandatory_elements.get("correct_belief") or mandatory_elements.get("correct_category"),
                mechanism_explanation=mechanism,
                contrast_example=contrast,
                transfer_check=transfer_check,
            )
            if mandatory_type in {"M1", "M3"}:
                teaching_contract["addressed_claim_ids"] = [
                    item["claim_id"]
                    for item in payload.get("pretest_targets") or []
                    if isinstance(item, dict)
                    and item.get("misconception_type") in {None, mandatory_type}
                    and item.get("claim_id")
                ] or teaching_contract["addressed_claim_ids"]
            if mandatory_type == "unknown":
                message += "\n- 定義から構成要素と役割へつなげて、新しい例に適用します。"
        elif stage == "enrichment":
            message = (
                f"## {label}\n\n"
                "### 要点\n"
                f"- **{label}**: {description}\n"
                "- まずは構成要素と役割を分けて確認します。\n\n"
                "### 具体例\n"
                f"- {label}の構成要素が、それぞれの役割を分担して働く場面を考えます。\n\n"
                "### 注意点\n"
                "- 用語名だけで判断せず、役割と情報の流れに注目します。"
            )
        else:
            message = (
                f"## {label}\n\n"
                "### 要点\n"
                f"- **{label}**: {description}\n"
                "- 誤った捉え方と正しい役割の違いを整理します。\n\n"
                "### 具体例\n"
                f"- {label}を、役割と情報の流れに沿って説明する場面を考えます。\n\n"
                "### 注意点\n"
                "- 似た仕組みとの違いを、表面的な言葉ではなく構造から確認します。"
            )
        result = {
            "tutor_message": _pad_tutoring_material(message),
            "teaching_strategy": strategy_for(mandatory_type, None, group),
        }
        if mandatory_elements:
            result["mandatory_elements"] = mandatory_elements
            result["teaching_contract"] = teaching_contract
        return result


    async def generate_correct_answer_summary(self, payload: dict[str, Any]) -> dict[str, Any]:
        term = payload.get("term") or {}
        label = payload.get("focus_label") or term.get("label", "この概念")
        return {
            "summary": (
                "## 今回の要点\n\n"
                f"- **{label}**の役割と処理対象を区別できていることが要点です。\n"
                "- 教材で確認した定義と具体例を結び付けて考えられています。"
            )
        }

    async def explain_selected_distractor(self, payload: dict[str, Any]) -> dict[str, Any]:
        term = payload.get("term") or {}
        label = term.get("label", "対象概念")
        selected = payload.get("selected_option_bodies") or payload.get("selected_option_body") or "選択した説明"
        if isinstance(selected, list):
            selected = " / ".join(str(item) for item in selected)
        return {
            "feedback": (
                "## どこが違うか\n\n"
                f"- 「{selected}」は、**{label}**の役割や処理範囲と一致しません。\n\n"
                "## 見直す観点\n\n"
                "- 教材の定義、構成要素の役割、情報の流れを確認してください。"
            ),
            "remediation_focus": "定義、構成要素の役割、情報の流れを確認する。",
            "general_knowledge_supplement": None,
        }


def _pad_tutoring_material(message: str) -> str:
    """Keep deterministic mock material inside the production contract range."""
    additions = (
        "定義だけでなく、構成要素がどの役割を担い、情報がどの順で処理されるかを確認します。",
        "具体例では入力、処理、出力を対応付け、似た概念と違う点を言葉にします。",
        "最後に別の場面へ当てはめ、同じ判断基準で説明できるかを確かめます。",
    )
    index = 0
    while len(message) < MATERIAL_TARGET_CHARACTERS:
        message += f"\n\n{additions[index % len(additions)]}"
        index += 1
    return message
