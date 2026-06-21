from __future__ import annotations

from typing import Any

from app.ai.backend import initial_level, strategy_for


class MockAIBackend:
    provider = "mock"

    def _learning_diagnosis(self, payload: dict[str, Any], is_passed: bool) -> dict[str, Any]:
        answer = (payload.get("learner_answer") or "").strip()
        if payload.get("group_condition") == "control":
            return {}
        if "ambiguous" in answer or "曖昧" in answer:
            status, primary, confidence = "ambiguous", None, 0.6
        elif len(answer) < 4 or "unknown" in answer or "わからない" in answer:
            status, primary, confidence = "unknown", "unknown", 0.9
            is_passed = False
        elif "M1" in answer or "心理" in answer or "翻訳機能" in answer:
            status, primary, confidence = "misconception", "M1", 0.9
            is_passed = False
        elif "M2" in answer or "同じ処理" in answer or "混同" in answer:
            status, primary, confidence = "misconception", "M2", 0.9
            is_passed = False
        elif "M3" in answer or "名前だけ" in answer or "キーワード" in answer:
            status, primary, confidence = "misconception", "M3", 0.9
            is_passed = False
        elif is_passed:
            status, primary, confidence = "resolved", None, 0.9
        else:
            status, primary, confidence = "unknown", "unknown", 0.8
        return {
            "is_passed": is_passed and status == "resolved",
            "diagnosed_status": status,
            "primary_misconception_type": primary,
            "secondary_misconception_type": "M3" if primary == "M2" and "secondary" in answer else None,
            "diagnosis_confidence": confidence,
            "diagnosis_evidence": answer or "回答が空です。",
            "recommended_strategy": strategy_for(primary, status, "proposed"),
            "strategy_override": False,
            "strategy_override_reason": None,
            "requires_manual_review": confidence < 0.5,
        }

    async def diagnose_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        selected = payload.get("selected_option") or {}
        reason = (payload.get("learner_response") or {}).get("reason_text") or ""
        confidence = (payload.get("learner_response") or {}).get("confidence")
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
        elif is_correct:
            status = "stable_correct"
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
            None: "理由も含めておおむね理解できています。",
        }.get(mtype, "回答理由をもう少し確認する必要があります。")
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

    async def generate_prerequisite_material(self, payload: dict[str, Any]) -> dict[str, Any]:
        target = payload["target_term"]["label"]
        prerequisite = payload["fixed_prerequisite"]["label"]
        mode = payload.get("material_mode", "initial")
        return {
            "material": f"{prerequisite}は{target}を理解するための基礎です。{mode}教材として、役割、関係、具体例を整理します。",
            "examples": [f"{prerequisite}を使う簡単な例"],
            "comparisons": [f"{prerequisite}と似た概念の違い"],
            "counterexamples": [f"{prerequisite}ではない例"],
            "rag_sources": [item.get("chunk_id") for item in (payload.get("rag_context") or {}).get("chunks", [])],
            "general_knowledge_supplement": None,
        }

    async def explain_selected_distractor(self, payload: dict[str, Any]) -> dict[str, Any]:
        selected = payload.get("selected_option_body", "選択した説明")
        return {
            "feedback": f"「{selected}」は、対象概念の役割または処理範囲と一致しません。正答そのものではなく、何を処理し何が変わるかを見直してください。",
            "remediation_focus": "概念の種類、類似概念との境界、処理の仕組みを確認する。",
            "general_knowledge_supplement": None,
        }

    async def generate_correct_answer_summary(self, payload: dict[str, Any]) -> dict[str, Any]:
        label = payload.get("focus_label") or payload.get("target_term", {}).get("label", "この概念")
        return {"summary": f"{label}の役割と処理対象を区別できていることが要点です。"}

    async def generate_emergency_question_variant(self, payload: dict[str, Any]) -> dict[str, Any]:
        label = payload.get("focus_label") or payload.get("target_term", {}).get("label", "対象概念")
        return {
            "body": f"{label}について、未使用の観点から最も適切な説明を選んでください。",
            "options": [
                {"body": f"{label}の正しい役割と仕組みを説明している。", "is_correct": True, "misconception_type": None},
                {"body": f"{label}を別の種類のものとして説明している。", "is_correct": False, "misconception_type": "M1"},
                {"body": f"{label}を似た概念と同一視している。", "is_correct": False, "misconception_type": "M2"},
                {"body": f"{label}を名称や表面語だけから説明している。", "is_correct": False, "misconception_type": "M3"},
                {"body": "わからない。", "is_correct": False, "misconception_type": "unknown"},
            ],
        }

    async def generate_prerequisite_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        term = payload["target_term"]
        label = term["label"]
        defaults = {
            "Transformer": ["トークン間の関係", "Attention", "FFN"],
            "Attention": ["トークン", "関係の重み", "文脈情報"],
            "LLMの学習段階": ["事前学習", "インストラクションチューニング", "事後学習"],
            "事前学習": ["大規模データ", "次単語予測", "基盤能力"],
            "事後学習": ["人間評価", "報酬モデル", "安全性と有用性"],
        }
        terms = defaults.get(label, [f"{label}の基本", f"{label}の役割", f"{label}の使い方"])
        return {
            "prerequisites": [
                {
                    "term_label": prereq,
                    "material": f"{prereq}は、{label}を理解するための前提です。教材の内容に沿って、役割と関係を確認します。",
                    "check_question": f"{prereq}が{label}の理解にどう関係するか、自分の言葉で説明してください。",
                    "expected_answer": f"{prereq}の役割と、{label}との関係を説明できている。",
                    "generation_reason": f"{label}の説明に必要な基礎要素として選びました。",
                }
                for prereq in terms[:3]
            ],
            "plan_rationale": f"{label}の理解に必要な前提をMockAIBackendが3件選びました。",
        }

    async def generate_control_prerequisite_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        term = payload["target_term"]
        label = term["label"]
        items = [f"{label}の基本", f"{label}の役割", f"{label}の注意点"]
        return {
            "prerequisites": [
                {
                    "term_label": item,
                    "material": f"{item}について、教材に基づく一般的な確認をします。",
                    "check_question": f"{item}を自分の言葉で短く説明してください。",
                    "expected_answer": f"{item}を教材の範囲で説明できている。",
                    "generation_reason": "統制群のため個別診断を使わず、教材範囲の一般小問として生成しました。",
                }
                for item in items
            ],
            "plan_rationale": f"{label}について、診断情報を使わず一般小問を3件生成しました。",
        }

    async def grade_prerequisite_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        answer = payload.get("learner_answer", "")
        positive_markers = ["pass", "十分", "関係", "役割", "重み", "事前", "事後", "学習", "評価", "安全", "基盤", "トークン", "Attention", "FFN"]
        is_passed = len(answer.strip()) >= 12 and any(marker in answer for marker in positive_markers)
        result = {
            "is_passed": is_passed,
            "score": 0.8 if is_passed else 0.3,
            "feedback": "中核となる関係を説明できています。" if is_passed else "前提用語の役割と対象概念との関係をもう少し具体化してください。",
            "remediation_material": None if is_passed else "より簡単に言うと、この前提用語が何を表し、対象概念のどの部分に関係するかを一文で整理します。例も使ってかまいません。",
            "core_elements_covered": ["役割", "関係"] if is_passed else [],
            "major_errors": [] if is_passed else ["説明が短い、または関係が不明確"],
            "rubric_scores": {
                "core_meaning": 0.8 if is_passed else 0.3,
                "relation_to_target": 0.8 if is_passed else 0.2,
                "misconception_absence": 0.9 if is_passed else 0.5,
                "explanation_clarity": 0.8 if is_passed else 0.3,
            },
        }
        result.update(self._learning_diagnosis(payload, is_passed))
        return result

    async def generate_concept_phase1_material(self, payload: dict[str, Any]) -> dict[str, Any]:
        term = payload["target_term"]
        prereq_labels = [item["term_label"] for item in payload.get("prerequisites", [])]
        joined = "、".join(prereq_labels)
        return {
            "concept_material": f"{term['label']}は、{joined}を組み合わせて理解します。各前提用語がどの役割を持つかをつなげて説明しましょう。",
            "concept_prompt": f"{joined}を使って、{term['label']}を自分の言葉で説明してください。",
            "expected_answer": f"{joined}を使い、{term['label']}の役割を説明できている。",
        }

    async def generate_concept_material(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.generate_concept_phase1_material(payload)

    async def grade_concept_phase1_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        answer = payload.get("learner_answer", "")
        prereq_labels = [item["term_label"] for item in payload.get("prerequisites", [])]
        used = [label for label in prereq_labels if label in answer]
        is_passed = len(answer.strip()) >= 20 and len(used) >= max(1, min(2, len(prereq_labels)))
        missing = [label for label in prereq_labels if label not in used]
        review = missing[:1]
        if len(prereq_labels) > 1 and missing:
            idx = prereq_labels.index(missing[0])
            if idx > 0:
                review.append(prereq_labels[idx - 1])
        result = {
            "is_passed": is_passed,
            "score": 0.85 if is_passed else 0.4,
            "feedback": "前提用語を使って対象概念を説明できています。" if is_passed else "前提用語とのつながりが不足しています。関連する前提用語を確認しましょう。",
            "missing_prerequisite_labels": [] if is_passed else missing[:1],
            "review_prerequisite_labels": [] if is_passed else review[:2],
            "core_elements_covered": used,
            "major_errors": [] if is_passed else ["前提用語の利用不足"],
            "rubric_scores": {
                "core_concept": 0.85 if is_passed else 0.4,
                "prerequisite_use": 0.8 if is_passed else 0.3,
                "misconception_absence": 0.9 if is_passed else 0.5,
                "explanation_clarity": 0.8 if is_passed else 0.4,
            },
            "confirmed_prerequisite_labels": used if is_passed else [],
        }
        result.update(self._learning_diagnosis(payload, is_passed))
        return result

    async def grade_concept_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.grade_concept_phase1_answer(payload)

    async def generate_concept_phase2_prompt(self, payload: dict[str, Any]) -> dict[str, Any]:
        term = payload["target_term"]
        prereq_labels = [item["term_label"] for item in payload.get("prerequisites", [])]
        joined = "、".join(prereq_labels[:3])
        return {
            "phase2_prompt": f"教材を見ずに、{term['label']}を自分の言葉で説明してください。",
            "light_conditions": f"{joined}のうち少なくとも2つを使い、暗記した文ではなく仕組みとして説明してください。",
            "expected_answer": f"{joined}を使って、{term['label']}の仕組みと役割を説明できている。",
        }

    async def grade_concept_phase2_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        answer = payload.get("learner_answer", "")
        prereq_labels = [item["term_label"] for item in payload.get("prerequisites", [])]
        used = [label for label in prereq_labels if label in answer]
        explicit_pass = any(marker in answer for marker in ["phase2pass", "独立", "教材なし", "自力"])
        is_passed = explicit_pass or (len(answer.strip()) >= 24 and len(used) >= max(1, min(2, len(prereq_labels))))
        result = {
            "is_passed": is_passed,
            "score": 0.86 if is_passed else 0.38,
            "feedback": "教材なしでも前提用語を使って説明できています。" if is_passed else "教材なしでは説明のつながりが不足しています。もう一度教材ありの整理に戻ります。",
            "independent_explanation_success": is_passed,
            "return_to_phase1": not is_passed,
            "rubric_scores": {
                "core_concept": 0.86 if is_passed else 0.38,
                "independent_reconstruction": 0.85 if is_passed else 0.3,
                "condition_following": 0.8 if is_passed else 0.35,
                "misconception_absence": 0.9 if is_passed else 0.5,
                "explanation_clarity": 0.82 if is_passed else 0.35,
            },
        }
        result.update(self._learning_diagnosis(payload, is_passed))
        return result

    async def generate_adaptive_support(self, payload: dict[str, Any]) -> dict[str, Any]:
        observation = payload.get("observation") or {}
        mode = payload.get("mode", "remediation")
        strategy = observation.get("applied_strategy") or "foundational_explanation"
        label = (payload.get("target_term") or {}).get("label", "この概念")
        if mode == "clarification":
            feedback = "回答の意図をもう少し確認します。"
            material = "似ている考えを区別するため、役割と仕組みのどちらを説明しているか整理してください。"
        else:
            feedback = f"{label}の理解を、現在の回答で不足している観点から確認します。"
            material = f"{strategy}の方針で、完成回答を示さずに例・比較・反例を使って整理します。"
        return {
            "mode": mode,
            "feedback": feedback,
            "supplemental_material": material,
            "next_check_question": f"{label}について、先ほどとは別の言い方で役割と仕組みを説明してください。",
            "diagnostic_focus": {
                "core_elements": ["役割", "仕組み"],
                "M1_features": ["別カテゴリーとして説明"],
                "M2_features": ["類似概念と同一視"],
                "M3_features": ["名称やキーワードだけで説明"],
                "unknown_criteria": "空欄または説明材料がない",
            },
            "rag_sources": [item.get("chunk_id") for item in (payload.get("rag_context") or {}).get("chunks", [])],
            "general_knowledge_supplement": None,
        }

    async def generate_control_learning_turn(self, payload: dict[str, Any]) -> dict[str, Any]:
        term = payload["target_term"]
        return {
            "tutor_message": f"{term['label']}について、教材に基づく一般的な説明を確認します。{term.get('description') or ''}",
            "learner_prompt": f"{term['label']}を自分の言葉で説明してください。",
            "practice_question": {
                "body": f"{term['label']}の役割を一文で説明してください。",
                "expected_answer": term.get("description") or "",
            },
            "forbidden_help_given": False,
        }

    async def grade_control_learning_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        answer = payload.get("learner_response", "")
        return {
            "feedback": "説明として必要な要素が含まれています。" if len(answer.strip()) >= 12 else "もう少し具体的に、何のための概念かを書いてください。",
            "is_complete": len(answer.strip()) >= 12,
            "forbidden_help_given": False,
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
            mtype = None if is_correct else ("M4" if question.get("phase") == "transfer" else "M3")
        status = "stable_correct" if is_correct else "misconception"
        return {
            "is_correct": is_correct,
            "score": 1.0 if is_correct else 0.0,
            "misconception_type": None if is_correct else (mtype or "M3"),
            "secondary_misconception_type": None,
            "diagnosed_status": status,
            "recurrence_flag": False,
            "l0_success": is_correct if question.get("phase") == "l0_check" else None,
            "transfer_success": is_correct if question.get("phase") == "transfer" else None,
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
