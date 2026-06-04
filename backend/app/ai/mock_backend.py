from __future__ import annotations

from typing import Any

from app.ai.backend import initial_level, strategy_for


class MockAIBackend:
    provider = "mock"

    async def diagnose_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        selected = payload.get("selected_option") or {}
        reason = (payload.get("learner_response") or {}).get("reason_text") or ""
        confidence = None
        initial_m = selected.get("initial_misconception_type")
        is_correct = bool(selected.get("is_correct"))

        mtype = initial_m
        if any(word in reason for word in ["同じ", "同一", "混同"]):
            mtype = "M2"
        if any(word in reason for word in ["言葉", "字", "単語", "名前", "英語"]):
            mtype = "M3"
        if initial_m == "unknown" or selected.get("body") == "わからない。":
            status = "unknown"
            mtype = "unknown"
            is_correct = False
        elif is_correct and len(reason.strip()) >= 10:
            status = "stable_correct"
            mtype = None
        elif is_correct:
            status = "unstable_correct"
            mtype = None
        else:
            status = "misconception"
            mtype = mtype or "M3"

        level = initial_level(status, mtype, confidence)
        strategy = strategy_for(mtype, status, payload.get("group_condition", "proposed"))
        natural = {
            "M1": "概念を別の種類のものとして捉えている可能性があります。",
            "M2": "似ている概念との違いを確認する必要があります。",
            "M3": "言葉の表面ではなく、仕組みや判断基準に注目する必要があります。",
            "unknown": "まず基本的な意味から確認します。",
            None: "選択内容からはおおむね理解できています。",
        }.get(mtype, "選択内容から理解状態をもう少し確認する必要があります。")
        return {
            "is_correct": is_correct,
            "diagnosed_status": status,
            "misconception_type": mtype,
            "secondary_misconception_type": None,
            "diagnosis_confidence": 0.9 if status != "ambiguous" else 0.45,
            "natural_language_diagnosis": natural,
            "evidence": reason or selected.get("body") or "",
            "recommended_initial_scaffolding_level": level,
            "recommended_teaching_strategy": strategy,
            "requires_manual_review": False,
        }

    async def generate_tutoring_turn(self, payload: dict[str, Any]) -> dict[str, Any]:
        term = payload["term"]
        state = payload["learner_state"]
        group = payload.get("group_condition", "proposed")
        level = state.get("scaffolding_level") or "L2"
        strategy = state.get("teaching_strategy") or strategy_for(state.get("primary_misconception"), state.get("current_status"), group)

        if group == "control":
            message = f"{term['label']}は、専門分野で決まった意味を持つ用語です。定義を確認し、例とあわせて理解しましょう。"
            prompt = f"{term['label']}を自分の言葉で一文で説明してください。"
        else:
            m = state.get("primary_misconception")
            if m == "M1":
                message = f"{term['label']}を別の種類のものとして捉えないように、まず「何の種類の概念か」を整理します。"
                prompt = f"{term['label']}は何ではなく、何のための概念ですか。"
            elif m == "M2":
                message = f"{term['label']}は似ている概念との境界が重要です。役割や使う場面の違いに注目します。"
                prompt = f"{term['label']}と混同しやすい概念の違いを1つ説明してください。"
            elif m == "M3":
                message = f"{term['label']}は単語の印象だけで判断せず、仕組みと判断基準に注目します。"
                prompt = "問題文の表面的な言葉ではなく、どの関係や条件を見るべきですか。"
            elif m == "M4":
                message = f"{term['label']}を別の文脈でも使えるよう、共通する構造を取り出します。"
                prompt = "学習時と別文脈で共通している判断基準を説明してください。"
            else:
                message = f"{term['label']}の基本定義を確認し、自分の言葉で説明できるようにします。"
                prompt = f"{term['label']}を、例に頼らず自分の言葉で説明してください。"

        return {
            "tutor_message": message,
            "teaching_strategy": strategy,
            "scaffolding_level": level,
            "requires_learner_response": True,
            "learner_prompt": prompt,
            "practice_question": {
                "body": f"{term['label']}を使う場面を1つ挙げ、なぜその概念が関係するか説明してください。",
                "expected_answer": term.get("description", ""),
                "question_type": "practice",
            },
            "forbidden_help_given": False,
        }

    async def grade_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        selected = payload.get("selected_option") or {}
        question = payload.get("question") or {}
        answer = " ".join(
            [
                payload.get("free_text_answer") or "",
                payload.get("reason_text") or "",
            ]
        )
        keywords = question.get("expected_keywords") or []
        if selected:
            is_correct = bool(selected.get("is_correct"))
            mtype = selected.get("initial_misconception_type")
        else:
            hit_count = sum(1 for keyword in keywords if keyword and keyword in answer)
            is_correct = hit_count >= max(1, min(2, len(keywords)))
            mtype = None if is_correct else "M3"
        status = "stable_correct" if is_correct else "misconception"
        return {
            "is_correct": is_correct,
            "score": 1.0 if is_correct else 0.0,
            "misconception_type": None if is_correct else (mtype or "M3"),
            "secondary_misconception_type": None,
            "diagnosed_status": status,
            "recurrence_flag": False,
            "l0_success": is_correct if question.get("phase") == "l0_check" else None,
            "feedback_for_log": "MockAIBackendによる決定論的採点です。",
            "evidence": answer or selected.get("body") or "",
            "requires_manual_review": False,
        }

    async def generate_feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
        correct = bool(payload.get("is_correct"))
        return {
            "feedback": "説明の中で判断基準に触れられています。" if correct else "もう一度、表面的な言葉ではなく判断基準に注目してください。",
            "next_action": "move_next" if correct else "continue",
            "next_scaffolding_level": payload.get("next_scaffolding_level") or "L2",
            "strategy_changed": bool(payload.get("strategy_changed")),
            "state_update_reason": "MockAIBackend feedback",
        }

    async def summarize_learner_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        label = payload.get("term", {}).get("label", "この用語")
        return {
            "summary_for_admin": f"{label}の現在状態を要確認。",
            "summary_for_learner": f"{label}について重点的に確認します。",
            "risk_flags": [],
            "recommended_next_focus": "自分の言葉で理由を説明する",
        }
