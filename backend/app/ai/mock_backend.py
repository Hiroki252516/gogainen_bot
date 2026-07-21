from __future__ import annotations

from typing import Any

from app.ai.backend import initial_level, strategy_for


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
        label = term.get("label", "Transformer")
        stage = payload.get("learning_stage") or "conceptual_change"
        group = payload.get("group_condition", "proposed")
        if stage == "enrichment":
            message = "Transformerの基本を確認します。Attentionはトークン間の関係性を重みづけし、FFNは各トークン表現を変換します。"
        else:
            message = "Transformerをアプリや人間の知能主体ではなく、AttentionとFFNなどからなるモデル構造として捉え直します。"
        if group == "control":
            message = f"{label}について、基本構造を確認します。{message}"
        return {
            "tutor_message": message,
            "teaching_strategy": "general_explanation" if group == "control" else payload.get("learner_state", {}).get("teaching_strategy") or "belief_revision",
            "scaffolding_level": payload.get("learner_state", {}).get("scaffolding_level") or "L3",
            "requires_learner_response": True,
            "learner_prompt": "Transformerについて、適切だと思うものをすべて選びなさい。",
            "practice_question": {
                "body": "Transformerについて、適切だと思うものをすべて選びなさい。",
                "expected_answer": "A、B、Cをすべて選択し、それ以外を選ばない。",
                "question_type": "learning_multi_select",
            },
            "forbidden_help_given": False,
        }

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
        is_sufficient = all(word in response for word in ["Attention", "FFN"])
        mtype = None if is_sufficient else ("unknown" if "わからない" in response else "M1")
        return {
            "feedback": "要点を押さえられています。" if is_sufficient else "Transformerの構造として、AttentionとFFNの役割を確認してください。",
            "is_sufficient": is_sufficient,
            "next_action": "move_next" if is_sufficient else "continue",
            "next_scaffolding_level": "L2" if is_sufficient else "L3",
            "learning_misconception_type": mtype,
            "learning_misconception_confidence": 0.8,
            "learning_misconception_reason": "MockAIBackendによる決定論的判定です。",
            "strategy_changed": False,
            "state_update_reason": "mock_feedback",
        }

    async def summarize_learner_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        label = payload.get("term", {}).get("label", "Transformer")
        return {
            "summary_for_admin": f"{label}の現在状態を要確認。",
            "summary_for_learner": f"{label}について重点的に確認します。",
            "risk_flags": [],
            "recommended_next_focus": "AttentionとFFNの役割を確認する",
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
