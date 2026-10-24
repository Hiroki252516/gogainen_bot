from __future__ import annotations

from typing import Any

from app.ai.backend import strategy_for
from app.ai.interaction_history import project_model_payload
from app.ai.mandatory_elements import (
    expected_mandatory_type,
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
            transfer_check = (
                f"新しい例でも、{(target or {}).get('corrected_claim') or description}に当てはまるかを説明します。"
            )
            message = (
                f"## {label}\n\n"
                + "\n\n".join(
                    f"### {heading}\n" + "\n".join(f"- {mandatory_elements[field]}" for field in fields)
                    for heading, fields in _mock_sections(label, mandatory_type)
                )
                + f"\n- {transfer_check}"
            )
            mechanism = (
                (target or {}).get("mechanism_explanation")
                or mandatory_elements.get("reason")
                or mandatory_elements.get("boundary_criterion")
                or mandatory_elements.get("role")
                or "構成要素と役割の関係を確認します。"
            )
            contrast = (target or {}).get("contrast_example") or mandatory_elements.get("counterexample") or mandatory_elements.get("contrast_example")
            message += f"\n- 仕組み: {mechanism}"
            if mandatory_type in {"M1", "M3"}:
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
        else:
            message = (
                f"## {label}\n\n"
                f"### {label}の働きを整理する\n"
                f"- **{label}**: {description}\n"
                "- 構成要素の役割と情報の流れを対応させて確認します。\n\n"
                "### 事例から使い分けを考える\n"
                f"- {label}の構成要素が、役割を分担して働く場面を考えます。\n"
                "- 似た仕組みとの違いは、用語名ではなく役割と処理範囲から判断します。"
            )
        result = {
            "tutor_message": _pad_tutoring_material(message + _history_note(payload), beginner=payload.get("explanation_level") == "beginner"),
            "teaching_strategy": strategy_for(mandatory_type, None, group),
        }
        if mandatory_elements:
            result["mandatory_elements"] = mandatory_elements
            result["teaching_contract"] = teaching_contract
        return result


    async def generate_correct_answer_summary(self, payload: dict[str, Any]) -> dict[str, Any]:
        term = payload.get("term") or {}
        label = payload.get("focus_label") or term.get("label", "この概念")
        if payload.get("explanation_level") == "beginner":
            return {"summary": f"## 今回の要点\n\n- **{label}**で何をするかを区別できました。\n- 今回の考え方を、学校や買物など別の場面でも使ってみましょう。"}
        return {
            "summary": (
                "## 今回の要点\n\n"
                f"- **{label}**の役割と処理対象を区別できていることが要点です。\n"
                "- 教材で確認した定義と具体例を結び付けて考えられています。"
                + _history_note(payload, feedback=True)
            )
        }

    async def explain_selected_distractor(self, payload: dict[str, Any]) -> dict[str, Any]:
        term = payload.get("term") or {}
        label = term.get("label", "対象概念")
        selected = payload.get("selected_option_bodies") or payload.get("selected_option_body") or "選択した説明"
        if isinstance(selected, list):
            selected = " / ".join(str(item) for item in selected)
        if payload.get("explanation_level") == "beginner":
            return {"feedback": f"## どこが違うか\n\n- 選んだ説明では、**{label}**が何をするかの区別を見直す必要があります。\n\n## 見直す観点\n\n- 教材の身近な例で、何を渡して何を行うかを確かめましょう。", "remediation_focus": "何をする仕組みかを確かめる。", "general_knowledge_supplement": None}
        return {
            "feedback": (
                "## どこが違うか\n\n"
                f"- 「{selected}」は、**{label}**の役割や処理範囲と一致しません。\n\n"
                "## 見直す観点\n\n"
                "- 教材の定義、構成要素の役割、情報の流れを確認してください。"
                + _history_note(payload, feedback=True)
            ),
            "remediation_focus": "定義、構成要素の役割、情報の流れを確認する。",
            "general_knowledge_supplement": None,
        }


def _mock_sections(label: str, misconception_type: str) -> list[tuple[str, tuple[str, ...]]]:
    """Deterministic test outlines merge evidence without imposing production headings."""
    return {
        "M1": [
            (f"{label}について見直す点", ("wrong_belief", "correct_belief")),
            ("事例と仕組みを結び付ける", ("counterexample", "reason")),
        ],
        "M3": [
            (f"{label}はどの種類か", ("wrong_category", "correct_category")),
            ("使い分けの基準を確かめる", ("contrast_example", "boundary_criterion")),
        ],
        "unknown": [
            (f"{label}の意味と仕組み", ("definition",)),
        ],
    }[misconception_type]


def _history_note(payload: dict[str, Any], *, feedback: bool = False) -> str:
    history = project_model_payload(payload, proposed=payload.get("group_condition", "proposed") == "proposed", feedback=feedback)["interaction_history"]
    if not history:
        return ""
    if history[-1].get("is_correct"):
        return "\n- 以前の回答で確認できた点を、別の例にも結び付けて整理します。"
    return "\n- 以前の回答で見直す必要があった点は、定義と処理の違いを対応させて確認します。"


def _pad_tutoring_material(message: str, *, beginner: bool = False) -> str:
    """Keep deterministic mock material inside the production contract range."""
    additions = (
        "定義だけでなく、構成要素がどの役割を担い、情報がどの順で処理されるかを確認します。",
        "具体例では入力、処理、出力を対応付け、似た概念と違う点を言葉にします。",
        "最後に別の場面へ当てはめ、同じ判断基準で説明できるかを確かめます。",
    )
    if beginner:
        additions = (
            "たとえば学校や買物の相談を考えます。AIに何を伝えるか、伝えた情報をどこで使うかを順に確かめましょう。",
            "似た名前の仕組みでも、することが同じとは限りません。名前だけで決めず、実際にどんな作業を行うかを比べます。",
            "説明を読んだら、自分の言葉で短く言い直してみましょう。別の場面でも同じ考え方が使えるかを考えると整理できます。",
        )
    index = 0
    while len(message) < MATERIAL_TARGET_CHARACTERS:
        message += f"\n\n{additions[index % len(additions)]}"
        index += 1
    return message
