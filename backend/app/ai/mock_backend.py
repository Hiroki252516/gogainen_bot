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
        level = state.get("scaffolding_level") if state.get("scaffolding_level") in {"L3", "L2", "L1"} else "L2"
        strategy = state.get("teaching_strategy") or strategy_for(state.get("primary_misconception"), state.get("current_status"), group)

        if group == "control":
            message = f"{term['label']}は、専門分野で決まった意味を持つ用語です。例とあわせて確認しましょう。"
        elif level == "L3":
            message = "訓練データはモデルが学習に使ったデータ、未知データは学習に使っていない新しいデータです。過学習は、訓練データにはよく合う一方で、未知データへの性能が下がる状態です。"
        elif level == "L2":
            message = "過学習かどうかは、訓練データでの性能だけでは判断できません。訓練データでは高く、未知データでは低いという差が重要です。"
        else:
            message = "判断の中心は、訓練データと未知データの性能差です。答えを丸暗記せず、その差を根拠として説明しましょう。"

        questions = {
            "L3": "過学習を判断するときに見るべき2つのデータは何ですか？",
            "L2": "訓練データ99%と未知データ55%を比べると、どちらの性能に問題がありますか？",
            "L1": "このモデルが過学習だと言える理由を、訓練データと未知データの差に触れて一文で説明してください。",
        }
        expected = {
            "L3": "訓練データと未知データ",
            "L2": "未知データで性能が下がっている",
            "L1": "訓練データにはよく合っているが、未知データで性能が低いから",
        }

        return {
            "tutor_message": message,
            "teaching_strategy": strategy,
            "scaffolding_level": level,
            "requires_learner_response": True,
            "learner_prompt": questions[level],
            "practice_question": {
                "body": questions[level],
                "expected_answer": expected[level],
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
        response = payload.get("learner_response") or ""
        current_level = payload.get("learner_state", {}).get("scaffolding_level") or "L2"
        correct = any(word in response for word in ["訓練", "未知", "性能", "下が"])
        next_by_level = {"L3": "L2", "L2": "L1", "L1": "L1"}
        return {
            "feedback": "説明の中で判断基準に触れられています。" if correct else "もう一度、訓練データと未知データの差に注目してください。",
            "next_action": "move_next" if correct and current_level == "L1" else "continue",
            "next_scaffolding_level": next_by_level.get(current_level, "L2"),
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
