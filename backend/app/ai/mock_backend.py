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
        previous_question = (payload.get("previous_practice_question") or "").strip()
        previous_response = (payload.get("previous_learner_response") or "").strip()
        previous_feedback = (payload.get("previous_feedback_for_learner") or "").strip()
        learning_stage = payload.get("learning_stage") or "concept_understanding"
        component_term = payload.get("component_term")
        component_index = int(payload.get("component_index") or 0)
        component_total = int(payload.get("component_total") or 0)

        if learning_stage == "term_understanding" and component_term:
            message = _component_message(term["label"], component_term)
            question = f"{component_term}とは何かを、{term['label']}との関係が分かるように説明してください。"
            expected = _component_expected(term.get("slug", ""), component_term)
            if previous_question:
                message = f"前の問題: {previous_question}\nあなたの回答: {previous_response}\n前の回答を踏まえて、{previous_feedback} 今回は{component_term}を確認します。\n\n{message}"
            return {
                "tutor_message": message,
                "teaching_strategy": "general_explanation" if group == "control" else strategy,
                "scaffolding_level": level,
                "requires_learner_response": True,
                "learner_prompt": question,
                "practice_question": {
                    "body": question,
                    "expected_answer": expected,
                    "question_type": "component_term",
                },
                "forbidden_help_given": False,
            }

        if learning_stage == "concept_understanding":
            spec = dict(spec)
            spec["questions"] = dict(spec["questions"])
            spec["expected"] = dict(spec["expected"])
            spec["questions"][level] = _concept_question(term.get("slug", ""), term["label"], payload.get("component_terms") or [])
            spec["expected"][level] = spec["core"]

        if group == "control":
            message = f"{term['label']}は、専門分野で決まった意味を持つ用語です。{spec['core']}"
            strategy = "general_explanation"
        else:
            message = spec["messages"][level]
        previous_parts = []
        if previous_question:
            previous_parts.append(f"前の問題: {previous_question}")
        if previous_response:
            previous_parts.append(f"あなたの回答: {previous_response}")
        if previous_feedback:
            previous_parts.append(f"前の回答を踏まえて、{previous_feedback} 今回は{spec['focus']}を確認します。")
        if previous_parts:
            message = "\n".join(previous_parts) + f"\n\n{message}"

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
        if payload.get("learning_stage") == "term_understanding" and payload.get("component_term"):
            keywords = _component_keywords(slug, payload["component_term"])
        else:
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
    "transformer": {
        "core": "AttentionレイヤーとFFNレイヤーを重ね、トークン間の関係性と特徴変換を繰り返す構造として確認します。",
        "focus": "AttentionとFFNの役割",
        "messages": {
            "L3": "Transformerは、Attentionレイヤーでトークン間の関係性を扱い、FFNレイヤーで各トークンの特徴を変換する構造です。RNNのように順番の隠れ状態だけに頼る構造ではありません。",
            "L2": "Transformerを見るときは、Attentionが関係性を扱い、FFNが特徴変換を行うという役割分担に注目します。",
            "L1": "着目点は、AttentionとFFNを重ねてトークン間の関係性と特徴変換を扱うことです。",
        },
        "questions": {
            "L3": "Transformerでは、AttentionレイヤーとFFNレイヤーがそれぞれ何を扱いますか？",
            "L2": "TransformerをRNNと同じ順番処理だけの構造と説明すると、どの点が不足しますか？",
            "L1": "Transformerの基本構造を、AttentionとFFNに触れて一文で説明してください。",
        },
        "expected": {
            "L3": "Attentionはトークン間の関係性、FFNは各トークンの特徴変換を扱う",
            "L2": "AttentionとFFNで関係性と特徴変換を扱う点が不足している",
            "L1": "AttentionとFFNを重ね、関係性と特徴変換を繰り返す構造",
        },
    },
    "attention": {
        "core": "入力中のトークン同士の関係を重み付けして、必要な情報を利用する仕組みとして確認します。",
        "focus": "トークン間の関係と重み付け",
        "messages": {
            "L3": "Attentionは、人間の集中ではなく、入力中のトークン同士の関係を計算し、重要度に応じて情報を重み付けして使う仕組みです。",
            "L2": "Attentionでは、各トークンが他のトークンとどの程度関係するかを見ることが重要です。単に目立つ単語を探す処理ではありません。",
            "L1": "着目点は、トークン同士の関係と、その関係に応じた重み付けです。",
        },
        "questions": {
            "L3": "Attentionで重み付けされるのは、入力中の何と何の関係ですか？",
            "L2": "Attentionを『重要語を探すだけ』と説明すると、どの点が不足しますか？",
            "L1": "Attentionの役割を、トークン間の関係と重み付けに触れて一文で説明してください。",
        },
        "expected": {
            "L3": "入力中のトークン同士の関係",
            "L2": "トークン同士の関係を計算して重み付けする点が不足している",
            "L1": "入力中のトークン同士の関係を計算し、重要度に応じて情報を重み付けして使う仕組み",
        },
    },
    "llm_training_process": {
        "core": "LLMの主な学習プロセスを、事前学習、インストラクションチューニング、事後学習の3段階として確認します。",
        "focus": "3つの学習段階の役割",
        "messages": {
            "L3": "LLMの学習段階は、基盤能力を作る事前学習、指示応答を学ぶインストラクションチューニング、安全性や有用性を調整する事後学習に分けて捉えます。",
            "L2": "LLMの学習過程では、各段階が何を目的にしているかを区別することが重要です。",
            "L1": "着目点は、事前学習、インストラクションチューニング、事後学習の順と役割です。",
        },
        "questions": {
            "L3": "LLMの主な学習プロセスを3段階で挙げ、それぞれの目的を説明してください。",
            "L2": "事前学習、インストラクションチューニング、事後学習は何が違いますか？",
            "L1": "LLMの主な学習プロセスを3段階で説明してください。",
        },
        "expected": {
            "L3": "事前学習、インストラクションチューニング、事後学習",
            "L2": "基盤能力、指示応答、安全性や有用性の調整という目的が違う",
            "L1": "事前学習、インストラクションチューニング、事後学習に分けられる",
        },
    },
    "pretraining": {
        "core": "大規模で多様なデータから、言語理解・生成能力や一般的知識の基盤を獲得する段階として確認します。",
        "focus": "大規模データと基盤能力",
        "messages": {
            "L3": "事前学習は、大規模で多様なテキストなどから、言語理解・生成能力や一般的知識の基盤を獲得する段階です。安全性だけを最後に整える工程ではありません。",
            "L2": "事前学習では、どのようなデータからどのような基盤能力を獲得するかに注目します。",
            "L1": "着目点は、大規模で多様なデータから基盤能力を獲得することです。",
        },
        "questions": {
            "L3": "LLMの事前学習では、どのようなデータから何を獲得しますか？",
            "L2": "事前学習をインストラクションチューニングと同じと説明すると、どの点が不足しますか？",
            "L1": "事前学習の目的を、大規模データと基盤能力に触れて説明してください。",
        },
        "expected": {
            "L3": "大規模で多様なデータから言語理解・生成能力や一般的知識の基盤を獲得する",
            "L2": "質問と回答ペアだけでなく、大規模で多様なデータから基盤能力を獲得する点",
            "L1": "大規模データから基盤能力を獲得する段階",
        },
    },
    "post_training": {
        "core": "人間評価や報酬モデルなどを用いて、出力を安全で有用なものに近づける段階として確認します。",
        "focus": "人間評価、安全性、有用性",
        "messages": {
            "L3": "事後学習は、LLMの出力を人間の価値観や安全性・有用性に合うよう、人間評価や報酬モデルなどを使って調整する段階です。",
            "L2": "事後学習では、回答後のログ保存ではなく、出力の安全性や有用性を調整する点に注目します。",
            "L1": "着目点は、人間評価などで出力をより安全で有用に調整することです。",
        },
        "questions": {
            "L3": "事後学習では、何を使ってLLMの出力をどのように調整しますか？",
            "L2": "事後学習を単なるログ保存と説明すると、どの点が不足しますか？",
            "L1": "事後学習の目的を、人間評価や安全性・有用性に触れて説明してください。",
        },
        "expected": {
            "L3": "人間評価や報酬モデルで安全性・有用性に合うよう出力を調整する",
            "L2": "安全性や有用性に合うよう出力を調整する点",
            "L1": "人間評価などを使って出力を安全で有用に近づける段階",
        },
    },
}

_SUFFICIENCY_KEYWORDS = {
    "transformer": ["Attention", "FFN", "関係"],
    "attention": ["トークン", "関係", "重み"],
    "llm_training_process": ["事前学習", "インストラクション", "事後学習"],
    "pretraining": ["大規模", "多様", "基盤"],
    "post_training": ["人間評価", "安全", "有用"],
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


_COMPONENT_KEYWORDS = {
    "transformer": {
        "Attention": ["Attention", "関係"],
        "FFN": ["FFN", "特徴", "変換"],
        "トークン間の関係性": ["トークン", "関係"],
    },
    "attention": {
        "トークン": ["トークン"],
        "関係": ["関係"],
        "重み付け": ["重み"],
        "重要度": ["重要", "重み"],
    },
    "llm_training_process": {
        "事前学習": ["事前学習", "基盤"],
        "インストラクションチューニング": ["インストラクション", "指示"],
        "事後学習": ["事後学習", "安全", "有用"],
    },
    "pretraining": {
        "大規模データ": ["大規模", "データ"],
        "多様なデータ": ["多様", "データ"],
        "次単語予測": ["次", "予測"],
        "基盤能力": ["基盤", "能力"],
    },
    "post_training": {
        "人間評価": ["人間", "評価"],
        "報酬モデル": ["報酬", "モデル"],
        "安全性": ["安全"],
        "有用性": ["有用"],
    },
}


def _component_keywords(slug: str, component_term: str) -> list[str]:
    return _COMPONENT_KEYWORDS.get(slug, {}).get(component_term, [component_term])


def _component_expected(slug: str, component_term: str) -> str:
    return "、".join(_component_keywords(slug, component_term))


def _component_message(term_label: str, component_term: str) -> str:
    return f"今回は{term_label}を理解するための構成用語として、{component_term}を確認します。用語単体の意味だけでなく、{term_label}の説明でどの役割を持つかに注目してください。"


def _concept_question(slug: str, term_label: str, component_terms: list[str]) -> str:
    joined = "、".join(component_terms) if component_terms else term_label
    questions = {
        "transformer": "Attention、FFN、トークン間の関係性を用いてTransformerの構造を説明してください。",
        "attention": "トークン同士の関係、重み付け、重要度に触れてAttentionの役割を説明してください。",
        "llm_training_process": "事前学習、インストラクションチューニング、事後学習の3段階でLLMの学習プロセスを説明してください。",
        "pretraining": "大規模で多様なデータ、次単語予測、基盤能力に触れて事前学習の目的を説明してください。",
        "post_training": "人間評価、報酬モデル、安全性、有用性に触れて事後学習の目的を説明してください。",
    }
    return questions.get(slug, f"{joined}を用いて{term_label}を説明してください。")
