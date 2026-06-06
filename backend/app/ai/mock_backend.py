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
        slug = term.get("slug", "")
        spec = _TERM_TUTORING.get(slug, _generic_tutoring_spec(term))
        previous_feedback = (payload.get("previous_feedback_for_learner") or "").strip()

        if group == "control":
            message = f"{term['label']}は、専門分野で決まった意味を持つ用語です。{spec['core']}"
            strategy = "general_explanation"
        else:
            message = spec["messages"][level]
        if previous_feedback:
            message = f"前の回答を踏まえて、{previous_feedback} 今回は{spec['focus']}を確認します。\n\n{message}"

        return {
            "tutor_message": message,
            "teaching_strategy": strategy,
            "scaffolding_level": level,
            "requires_learner_response": True,
            "learner_prompt": spec["questions"][level],
            "practice_question": {
                "body": spec["questions"][level],
                "expected_answer": spec["expected"][level],
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
        term = payload.get("term") or {}
        slug = term.get("slug", "")
        keywords = _SUFFICIENCY_KEYWORDS.get(slug, [word for word in (term.get("description") or "").split() if word])
        hit_count = sum(1 for keyword in keywords if keyword and keyword in response)
        is_sufficient = hit_count >= max(1, min(2, len(keywords)))
        current_level = payload.get("learner_state", {}).get("scaffolding_level") or "L2"
        next_by_level = {"L3": "L2", "L2": "L1", "L1": "L1"} if is_sufficient else {"L3": "L3", "L2": "L3", "L1": "L2"}
        label = term.get("label", "この用語")
        return {
            "feedback": f"{label}について、判断基準を使って説明できています。" if is_sufficient else f"{label}について、説明に必要な判断基準がまだ足りません。",
            "is_sufficient": is_sufficient,
            "next_action": "move_next" if is_sufficient and current_level == "L1" else "continue",
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

_TERM_TUTORING = {
    "attention": {
        "core": "入力中の要素同士の関係を重み付けして、必要な情報を利用する仕組みとして確認します。",
        "focus": "要素同士の関係と重み付け",
        "messages": {
            "L3": "Attentionは、人間の集中ではなく、入力中のトークン同士の関係を計算し、重要度に応じて情報を重み付けして使う仕組みです。",
            "L2": "Attentionでは、どの入力要素が他の要素と強く関係するかを見ることが重要です。単に目立つ単語を探す処理ではありません。",
            "L1": "着目点は、入力要素同士の関係と、その関係に応じた重み付けです。",
        },
        "questions": {
            "L3": "Attentionで重み付けされるのは、入力中の何と何の関係ですか？",
            "L2": "Attentionを『重要語を探すだけ』と説明すると、どの点が不足しますか？",
            "L1": "Attentionの役割を、関係と重み付けに触れて一文で説明してください。",
        },
        "expected": {
            "L3": "入力中の要素同士の関係",
            "L2": "要素同士の関係を計算して重み付けする点が不足している",
            "L1": "入力要素同士の関係を計算し、重要度に応じて情報を重み付けして使う仕組み",
        },
    },
    "embedding": {
        "core": "単語や文を意味的な関係を扱いやすい数値ベクトルとして表すことを確認します。",
        "focus": "数値ベクトル表現と意味的な近さ",
        "messages": {
            "L3": "Embeddingは、知識の保存場所そのものではなく、単語や文などを数値ベクトルとして表した表現です。意味的な近さを計算しやすくします。",
            "L2": "Embeddingを見るときは、対象を数値ベクトルに変換し、意味的な関係を扱う点に注目します。",
            "L1": "着目点は、数値ベクトルとして表し、意味的な近さを扱うことです。",
        },
        "questions": {
            "L3": "Embeddingは、単語や文をどのような形で表しますか？",
            "L2": "Embeddingを使うと、単語同士のどのような関係を扱いやすくなりますか？",
            "L1": "Embeddingの役割を、数値ベクトルと意味的な近さに触れて一文で説明してください。",
        },
        "expected": {
            "L3": "数値ベクトル",
            "L2": "意味的な近さや関係",
            "L1": "単語や文を数値ベクトルにして、意味的な近さを扱いやすくする表現",
        },
    },
    "overfitting": {
        "core": "訓練データに合いすぎ、未知データで性能が下がる状態として確認します。",
        "focus": "訓練データと未知データの性能差",
        "messages": {
            "L3": "過学習は、訓練データにはよく合う一方で、未知データへの性能が下がる状態です。学習量が多いだけでは判断できません。",
            "L2": "過学習かどうかは、訓練データでの性能だけではなく、未知データで性能が下がるかを見ることが重要です。",
            "L1": "着目点は、訓練データと未知データの性能差です。",
        },
        "questions": {
            "L3": "過学習を判断するときに見るべき2つのデータは何ですか？",
            "L2": "訓練データ99%と未知データ55%を比べると、どちらの性能に問題がありますか？",
            "L1": "このモデルが過学習だと言える理由を、訓練データと未知データの差に触れて一文で説明してください。",
        },
        "expected": {
            "L3": "訓練データと未知データ",
            "L2": "未知データで性能が下がっている",
            "L1": "訓練データにはよく合っているが、未知データで性能が低いから",
        },
    },
    "generalization": {
        "core": "訓練で得た規則を未知データにも適切に使えることを確認します。",
        "focus": "未知データへの適用",
        "messages": {
            "L3": "汎化は、訓練データで学んだ規則を、まだ見ていない未知データにも適切に使えることです。単に細かい違いを無視することではありません。",
            "L2": "汎化を見るときは、訓練で見ていないデータにも学習した規則を使えているかに注目します。",
            "L1": "着目点は、未知データにも学習した規則を適用できるかです。",
        },
        "questions": {
            "L3": "汎化では、学習した内容をどのようなデータにも使えることが重要ですか？",
            "L2": "未知データにも正しく対応できたとき、汎化のどの点が示されていますか？",
            "L1": "汎化の意味を、未知データへの適用に触れて一文で説明してください。",
        },
        "expected": {
            "L3": "未知データ",
            "L2": "学習した規則を未知データにも適用できている点",
            "L1": "訓練で学んだ規則を未知データにも適切に使えること",
        },
    },
}

_SUFFICIENCY_KEYWORDS = {
    "attention": ["関係", "重み", "重要"],
    "embedding": ["数値", "ベクトル", "意味"],
    "overfitting": ["訓練", "未知", "性能"],
    "generalization": ["未知", "適用", "訓練"],
}


def _generic_tutoring_spec(term: dict[str, Any]) -> dict[str, Any]:
    label = term.get("label", "この用語")
    description = term.get("description") or f"{label}の専門的な意味"
    return {
        "core": f"{description}を確認します。",
        "focus": f"{label}の専門的な意味",
        "messages": {
            "L3": f"{label}は、専門分野では次の意味で使います。{description}",
            "L2": f"{label}を説明するときは、日常的な語感ではなく専門的な役割に注目します。",
            "L1": f"着目点は、{label}の専門的な役割です。",
        },
        "questions": {
            "L3": f"{label}の専門的な意味を、自分の言葉で説明してください。",
            "L2": f"{label}を説明するとき、どの専門的な役割に注目しますか？",
            "L1": f"{label}の役割を一文で説明してください。",
        },
        "expected": {
            "L3": description,
            "L2": description,
            "L1": description,
        },
    }
