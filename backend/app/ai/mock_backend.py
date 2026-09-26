from __future__ import annotations

from typing import Any

from app.ai.backend import initial_level, strategy_for
from app.ai.mandatory_elements import (
    expected_mandatory_type,
    mandatory_element_headings,
    mock_mandatory_elements,
)
from app.ai.teaching_contract import mock_teaching_contract


class MockAIBackend:
    provider = "mock"

    async def diagnose_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = _fixed_result(payload)
        level = initial_level(result["diagnosed_status"], result["misconception_type"], None)
        strategy = strategy_for(result["misconception_type"], result["diagnosed_status"], payload.get("group_condition", "proposed"))
        return {
            **result,
            "diagnosis_confidence": 0.9,
            "natural_language_diagnosis": _natural(result),
            "evidence": _evidence(payload),
            "recommended_initial_scaffolding_level": level,
            "recommended_teaching_strategy": strategy,
            "requires_manual_review": False,
        }

    async def generate_tutoring_turn(self, payload: dict[str, Any]) -> dict[str, Any]:
        term = payload.get("term") or {}
        label = term.get("label", "対象用語")
        description = term.get("description") or f"{label}の基本的な定義と役割を確認します。"
        stage = payload.get("learning_stage") or "conceptual_change"
        group = payload.get("group_condition", "proposed")
        fixed_question = payload.get("fixed_practice_question") or {}
        question_body = fixed_question.get("body") or f"{label}について、適切な説明をすべて選びなさい。"
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
        learner_state = payload.get("learner_state") or {}
        result = {
            "tutor_message": message,
            "teaching_strategy": "general_explanation" if group == "control" else learner_state.get("teaching_strategy") or "foundational_explanation",
            "scaffolding_level": learner_state.get("scaffolding_level") or "L3",
            "requires_learner_response": True,
            "learner_prompt": question_body,
            "practice_question": {
                "body": question_body,
                "question_type": fixed_question.get("question_type") or "learning_multi_select",
            },
            "forbidden_help_given": False,
        }
        if mandatory_elements:
            result["mandatory_elements"] = mandatory_elements
            result["teaching_contract"] = teaching_contract
        return result

    async def grade_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = _fixed_result(payload)
        return {
            "is_correct": result["is_correct"],
            "score": result["score"],
            "misconception_type": result["misconception_type"],
            "secondary_misconception_type": None,
            "diagnosed_status": result["diagnosed_status"],
            "recurrence_flag": False,
            "l0_success": result["is_correct"],
            "feedback_for_log": "MockAIBackendによる決定論的採点です。",
            "evidence": _evidence(payload),
            "requires_manual_review": False,
        }

    async def generate_feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = payload.get("learner_response") or ""
        term = payload.get("term") or {}
        label = term.get("label", "対象用語")
        keywords = [str(keyword) for keyword in term.get("keywords") or []]
        is_sufficient = bool(response.strip()) and (not keywords or any(keyword in response for keyword in keywords))
        mtype = None if is_sufficient else ("unknown" if "わからない" in response else "M1")
        feedback = (
            "### 要点\n"
            f"- **{label}**の説明で、中心となる役割を押さえられています。"
            if is_sufficient
            else "### 見直しポイント\n"
            f"- **{label}**の定義と構成要素の役割を、教材の具体例と照らして確認してください。"
        )
        return {
            "feedback": feedback,
            "is_sufficient": is_sufficient,
            "next_action": "move_next" if is_sufficient else "continue",
            "next_scaffolding_level": "L2" if is_sufficient else "L3",
            "learning_misconception_type": mtype,
            "learning_misconception_confidence": 0.8,
            "learning_misconception_reason": "MockAIBackendによる決定論的判定です。",
            "strategy_changed": False,
            "state_update_reason": "mock_feedback",
        }

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

    async def summarize_learner_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        label = payload.get("term", {}).get("label", "対象用語")
        return {
            "summary_for_admin": f"{label}の現在状態を要確認。",
            "summary_for_learner": f"{label}について重点的に確認します。",
            "risk_flags": [],
            "recommended_next_focus": f"{label}の定義と構成要素の役割を確認する",
        }


def _fixed_result(payload: dict[str, Any]) -> dict[str, Any]:
    selected_options = payload.get("selected_options") or []
    if selected_options:
        labels = {option.get("label") for option in selected_options}
        misconceptions = [option.get("initial_misconception_type") for option in selected_options]
        is_correct = labels == {"A", "B", "C"}
        if is_correct:
            status, mtype = "stable_correct", None
        elif "M3" in misconceptions:
            status, mtype = "misconception", "M3"
        elif "M1" in misconceptions:
            status, mtype = "misconception", "M1"
        else:
            status, mtype = "unknown", "unknown"
        return {"is_correct": is_correct, "score": 1.0 if is_correct else 0.0, "diagnosed_status": status, "misconception_type": mtype, "secondary_misconception_type": None}
    selected = payload.get("selected_option") or {}
    is_correct = bool(selected.get("is_correct"))
    mtype = None if is_correct else selected.get("initial_misconception_type") or "unknown"
    status = "stable_correct" if is_correct else ("unknown" if mtype == "unknown" else "misconception")
    return {"is_correct": is_correct, "score": 1.0 if is_correct else 0.0, "diagnosed_status": status, "misconception_type": mtype, "secondary_misconception_type": None}


def _natural(result: dict[str, Any]) -> str:
    if result["is_correct"]:
        return "正しい構造を選択できています。"
    if result["misconception_type"] == "unknown":
        return "基本知識が不足している可能性があります。"
    return "選択内容に誤った捉え方が含まれています。"


def _evidence(payload: dict[str, Any]) -> str:
    selected_options = payload.get("selected_options") or []
    if selected_options:
        return " / ".join(option.get("label") or option.get("body") or "" for option in selected_options)
    selected = payload.get("selected_option") or {}
    return selected.get("body") or payload.get("reason_text") or payload.get("free_text_answer") or ""
