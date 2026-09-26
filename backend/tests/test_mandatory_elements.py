from __future__ import annotations

import asyncio

from app.services import experiment as experiment_service
from app.ai.mandatory_elements import (
    expected_mandatory_type,
    mandatory_element_headings,
    mandatory_elements_schema,
    reconcile_mandatory_elements,
    validate_mandatory_elements,
)
from app.ai.codex_app_server_backend import CodexAppServerBackend
from app.ai.mock_backend import MockAIBackend
from app.ai.teaching_contract import (
    reconcile_teaching_contract,
    teaching_contract_schema,
    validate_teaching_contract,
    validate_tutoring_material_safety,
)
from app.seed.content_loader import ACTIVE_TERM_SLUGS, _validate_teaching_targets, load_content, teaching_target_for_option


def _payload(misconception_type: str | None, stage: str) -> dict:
    return {
        "group_condition": "proposed",
        "active_misconception_type": misconception_type,
        "learning_stage": stage,
        "term": {
            "label": "記憶プロセス",
            "description": "情報を保存し、検索して現在の処理へ渡し、必要に応じて更新する仕組みです。",
        },
        "fixed_practice_question": {"body": "適切な説明を選びなさい。"},
    }


def test_mvp_types_resolve_to_mandatory_operations():
    assert expected_mandatory_type(_payload("M1", "conceptual_change")) == "M1"
    assert expected_mandatory_type(_payload("M3", "conceptual_change")) == "M3"
    assert expected_mandatory_type(_payload("unknown", "enrichment")) == "unknown"


def test_seed_has_researcher_verified_targets_for_all_m1_and_m3_options():
    content = load_content()
    assert tuple(term["slug"] for term in content["terms"]) == ACTIVE_TERM_SLUGS
    for term in content["terms"]:
        options = term["questions"]["pretest"][0]["options"]
        for option in options:
            if option.get("misconception_type") not in {"M1", "M3"}:
                continue
            target = teaching_target_for_option(term["slug"], option["label"])
            assert target is not None
            assert target["corrected_claim"]
            assert target["mechanism_explanation"]
            assert target["contrast_example"]
            if option["misconception_type"] == "M3":
                assert target["wrong_category"]
                assert target["correct_category"]
                assert target["boundary_criterion"]


def test_primary_target_does_not_cross_types_or_fallback_to_unknown():
    targets = [
        {"claim_id": "memory_process:pretest:D", "misconception_type": "M1"},
        {"claim_id": "memory_process:pretest:G", "misconception_type": "M3"},
    ]

    assert experiment_service._primary_pretest_target(targets, "M1")["claim_id"] == "memory_process:pretest:D"
    assert experiment_service._primary_pretest_target(targets, "M3")["claim_id"] == "memory_process:pretest:G"
    assert experiment_service._primary_pretest_target(targets, "unknown") is None


def test_unknown_contract_ignores_stale_pretest_targets():
    payload = _payload("unknown", "enrichment")
    stale_target = {
        "claim_id": "memory_process:pretest:D",
        "misconception_type": "M1",
        "observed_claim": "誤った説明",
    }
    payload["pretest_target"] = stale_target
    payload["pretest_targets"] = [stale_target]

    result = asyncio.run(MockAIBackend().generate_tutoring_turn(payload))
    validation = validate_teaching_contract(result, "unknown", payload, payload["term"]["label"])

    assert validation["valid"], validation
    assert result["teaching_contract"]["target_claim_id"] is None
    assert result["teaching_contract"]["addressed_claim_ids"] == []


def test_m1_or_m3_without_observed_target_uses_generic_contract():
    for misconception_type in ("M1", "M3"):
        payload = _payload(misconception_type, "conceptual_change")
        result = asyncio.run(MockAIBackend().generate_tutoring_turn(payload))

        validation = validate_teaching_contract(result, misconception_type, payload, payload["term"]["label"])

        assert validation["valid"], validation
        assert result["teaching_contract"]["target_claim_id"] is None
        assert result["teaching_contract"]["addressed_claim_ids"] == []


def test_teaching_contract_handles_japanese_labels_and_line_breaks():
    payload = _payload("M1", "conceptual_change")
    result = asyncio.run(MockAIBackend().generate_tutoring_turn(payload))
    corrected_claim = result["teaching_contract"]["corrected_claim"]
    split_at = len(corrected_claim) // 2
    result["tutor_message"] = result["tutor_message"].replace(
        corrected_claim,
        f"{corrected_claim[:split_at]}\n{corrected_claim[split_at:]}",
        1,
    ) + "\n誤概念M1について説明します。"

    validation = validate_teaching_contract(result, "M1", payload, payload["term"]["label"])

    assert not validation["valid"]
    assert "tutor_message:internal_label_exposed" in validation["missing"]
    assert "corrected_claim:evidence_not_in_tutor_message" not in validation["missing"]


def test_empty_pretest_variants_are_safe_during_teaching_target_validation():
    _validate_teaching_targets(
        {
            "terms": [
                {
                    "slug": "memory_process",
                    "questions": {"pretest": []},
                }
            ]
        }
    )


def test_explicit_non_mvp_type_does_not_fall_back_to_previous_diagnosis():
    for active_type in ("M2", "M4", None):
        payload = _payload(active_type, "conceptual_change")
        payload["previous_learning_misconception"] = {"misconception_type": "M1"}
        payload["learner_state"] = {"primary_misconception": "M3"}

        assert expected_mandatory_type(payload) is None


def test_mock_proposed_material_contains_all_mandatory_evidence():
    backend = MockAIBackend()
    for misconception_type, stage in (
        ("M1", "conceptual_change"),
        ("M3", "conceptual_change"),
        ("unknown", "enrichment"),
    ):
        payload = _payload(misconception_type, stage)
        result = asyncio.run(backend.generate_tutoring_turn(payload))
        validation = validate_mandatory_elements(
            result,
            misconception_type,
            payload["term"]["label"],
        )
        assert validation["valid"], validation
        assert result["mandatory_elements"]["type"] == misconception_type
        assert "### 要点" not in result["tutor_message"]
        assert "### 具体例" not in result["tutor_message"]
        assert "### 注意点" not in result["tutor_message"]
        for heading in mandatory_element_headings(misconception_type).values():
            assert f"### {heading}" in result["tutor_message"]


def test_codex_evidence_reconciliation_uses_visible_unknown_sections():
    backend = MockAIBackend()
    payload = _payload("unknown", "enrichment")
    result = asyncio.run(backend.generate_tutoring_turn(payload))
    result["mandatory_elements"]["components"] = "AIが返した別の要約です。"
    result["teaching_contract"]["mechanism_explanation"] = "AIが返した別の仕組みです。"
    result["teaching_contract"]["transfer_check"] = "AIが返した別の適用確認です。"

    reconcile_mandatory_elements(result, "unknown")
    reconcile_teaching_contract(result, "unknown")

    mandatory_validation = validate_mandatory_elements(result, "unknown", payload["term"]["label"])
    contract_validation = validate_teaching_contract(result, "unknown", payload, payload["term"]["label"])
    assert mandatory_validation["valid"], mandatory_validation
    assert contract_validation["valid"], contract_validation
    assert result["mandatory_elements"]["components"] in result["tutor_message"]
    assert result["teaching_contract"]["mechanism_explanation"] in result["tutor_message"]
    assert result["teaching_contract"]["transfer_check"] in result["tutor_message"]


def test_codex_evidence_reconciliation_fills_empty_values():
    backend = MockAIBackend()
    payload = _payload("unknown", "enrichment")
    result = asyncio.run(backend.generate_tutoring_turn(payload))
    result["mandatory_elements"]["components"] = ""

    reconcile_mandatory_elements(result, "unknown")

    validation = validate_mandatory_elements(result, "unknown", payload["term"]["label"])
    assert validation["valid"], validation
    assert result["mandatory_elements"]["components"]


def test_codex_m3_contract_reconciliation_uses_contrast_example():
    backend = MockAIBackend()
    payload = _payload("M3", "conceptual_change")
    result = asyncio.run(backend.generate_tutoring_turn(payload))
    result["teaching_contract"]["contrast_example"] = "AIが返した別のカテゴリー比較です。"

    reconcile_mandatory_elements(result, "M3")
    reconcile_teaching_contract(result, "M3")

    validation = validate_teaching_contract(result, "M3", payload, payload["term"]["label"])
    assert validation["valid"], validation
    assert result["teaching_contract"]["contrast_example"] in result["tutor_message"]


def test_codex_strips_contract_field_labels_from_learner_material():
    backend = CodexAppServerBackend()
    payload = _payload("unknown", "enrichment")
    result = asyncio.run(MockAIBackend().generate_tutoring_turn(payload))
    result["tutor_message"] += (
        "\n\nmechanism_explanation：仕組みを確認します。"
        "\ntransfer_check: 新しい例に適用します。"
        "\nM1誤概念"
        "\nwrong_belief：誤った考え"
    )

    async def capture(purpose, prompt, output_schema, **kwargs):
        return result

    backend._run_structured_turn = capture
    normalized = asyncio.run(backend.generate_tutoring_turn(payload))

    assert "mechanism_explanation：" not in normalized["tutor_message"]
    assert "transfer_check:" not in normalized["tutor_message"]
    assert "M1誤概念" not in normalized["tutor_message"]
    assert "wrong_belief：" not in normalized["tutor_message"]


def test_validator_rejects_evidence_not_present_in_visible_material():
    backend = MockAIBackend()
    payload = _payload("M1", "conceptual_change")
    result = asyncio.run(backend.generate_tutoring_turn(payload))
    result["mandatory_elements"]["counterexample"] = "教材本文に存在しない反例です。"

    validation = validate_mandatory_elements(result, "M1", payload["term"]["label"])

    assert not validation["valid"]
    assert "counterexample:evidence_not_in_tutor_message" in validation["missing"]


def test_validator_requires_markdown_heading_lines_not_inline_markers():
    backend = MockAIBackend()
    payload = _payload("M1", "conceptual_change")
    result = asyncio.run(backend.generate_tutoring_turn(payload))
    result["tutor_message"] = result["tutor_message"].replace(
        "### 正しい考え",
        "本文中で ### 正しい考え と表記します。",
        1,
    )

    validation = validate_mandatory_elements(result, "M1", payload["term"]["label"])

    assert not validation["valid"]
    assert "tutor_message:heading_missing:### 正しい考え" in validation["missing"]
    assert "correct_belief:evidence_not_in_section" in validation["missing"]


def test_validator_ignores_inline_heading_mentions_when_finding_section_end():
    backend = MockAIBackend()
    payload = _payload("M1", "conceptual_change")
    result = asyncio.run(backend.generate_tutoring_turn(payload))
    elements = result["mandatory_elements"]
    headings = mandatory_element_headings("M1")
    sections = ["## 記憶プロセス"]
    for field, heading in headings.items():
        evidence = elements[field]
        if field == "correct_belief":
            evidence = f"本文では ### 反例 と表記する説明も含める。\n- {evidence}"
        sections.append(f"### {heading}\n- {evidence}")
    result["tutor_message"] = "\n\n".join(sections)

    validation = validate_mandatory_elements(result, "M1", payload["term"]["label"])

    assert validation["valid"], validation


def test_validator_rejects_evidence_in_an_empty_heading_section():
    backend = MockAIBackend()
    payload = _payload("M1", "conceptual_change")
    result = asyncio.run(backend.generate_tutoring_turn(payload))
    elements = result["mandatory_elements"]
    headings = mandatory_element_headings("M1")
    sections = ["## 記憶プロセス"]
    for field, heading in headings.items():
        evidence = ""
        if field == "correct_belief":
            evidence = f"- {elements['wrong_belief']}\n- {elements[field]}"
        elif field != "wrong_belief":
            evidence = f"- {elements[field]}"
        sections.append(f"### {heading}\n{evidence}")
    result["tutor_message"] = "\n\n".join(sections)

    validation = validate_mandatory_elements(result, "M1", payload["term"]["label"])

    assert not validation["valid"]
    assert "wrong_belief:evidence_not_in_section" in validation["missing"]


def test_validator_detects_internal_labels_adjacent_to_japanese_text():
    backend = MockAIBackend()
    payload = _payload("M1", "conceptual_change")
    result = asyncio.run(backend.generate_tutoring_turn(payload))
    result["tutor_message"] += "\n\nこの説明はM1誤概念を示すものではありません。"

    validation = validate_mandatory_elements(result, "M1", payload["term"]["label"])

    assert not validation["valid"]
    assert "tutor_message:internal_label_exposed" in validation["missing"]


def test_service_retries_same_backend_when_mandatory_evidence_is_missing(monkeypatch):
    backend = MockAIBackend()
    payload = _payload("M3", "conceptual_change")
    calls: list[dict] = []

    async def fake_ai_call(db, purpose, request_payload):
        assert purpose == "generate_tutoring_turn"
        calls.append(request_payload)
        result = await backend.generate_tutoring_turn(request_payload)
        if len(calls) == 1:
            result["mandatory_elements"]["boundary_criterion"] = "欠落した証拠文"
        return result

    monkeypatch.setattr(experiment_service, "_ai_call", fake_ai_call)
    result, validation = asyncio.run(
        experiment_service._generate_validated_tutoring_turn(None, payload)
    )

    assert validation["valid"]
    assert validation["attempts"] == 2
    assert len(calls) == 2
    assert calls[1]["mandatory_element_retry"]["missing"] == [
        "boundary_criterion:evidence_not_in_tutor_message"
    ]
    assert result["mandatory_elements"]["type"] == "M3"


def test_codex_prompt_schema_requires_m1_evidence(monkeypatch):
    backend = CodexAppServerBackend()
    payload = _payload("M1", "conceptual_change")
    captured: dict[str, object] = {}
    mock_result = asyncio.run(MockAIBackend().generate_tutoring_turn(payload))

    async def capture(purpose, prompt, output_schema, **kwargs):
        captured["purpose"] = purpose
        captured["prompt"] = prompt
        captured["schema"] = output_schema
        return mock_result

    monkeypatch.setattr(backend, "_run_structured_turn", capture)
    asyncio.run(backend.generate_tutoring_turn(payload))

    schema = captured["schema"]
    assert "mandatory_elements" in schema["properties"]
    assert "mandatory_elements" in schema["required"]
    assert "teaching_contract" in schema["properties"]
    assert "teaching_contract" in schema["required"]
    assert set(schema["properties"]["teaching_contract"]["required"]) == set(teaching_contract_schema()["properties"])
    assert "practice_question" not in schema["properties"]
    assert "learner_prompt" not in schema["properties"]
    nested_schema = schema["properties"]["mandatory_elements"]
    assert set(nested_schema["required"]) == set(nested_schema["properties"])
    assert "wrong_category" not in nested_schema["properties"]
    assert "wrong_belief" in captured["prompt"]
    assert "counterexample" in captured["prompt"]


def test_control_tutoring_never_uses_proposed_mandatory_contract(monkeypatch):
    backend = CodexAppServerBackend()
    payload = _payload("M1", "conceptual_change")
    payload.update(
        {
            "group_condition": "control",
            "pretest_target": {"claim_id": "private-claim", "observed_claim": "private claim"},
            "prompt_contract_version": "private-contract-version",
            "generation_attempt": 2,
        }
    )
    captured: dict[str, object] = {}

    def unexpected_mandatory_type(_payload):
        raise AssertionError("control generation must not resolve a proposed-group type")

    async def capture(purpose, prompt, output_schema, **kwargs):
        captured.update(purpose=purpose, prompt=prompt, schema=output_schema, **kwargs)
        return {"tutor_message": "## 記憶プロセス\n\n### 要点\n- 情報を保存し検索します。", "teaching_strategy": "adaptive_scaffolding"}

    monkeypatch.setattr("app.ai.codex_app_server_backend.expected_mandatory_type", unexpected_mandatory_type)
    monkeypatch.setattr(backend, "_run_structured_turn", capture)
    result = asyncio.run(backend.generate_tutoring_turn(payload))

    assert "mandatory_elements" not in captured["schema"]["properties"]
    assert "teaching_contract" not in captured["schema"]["properties"]
    assert "private-claim" not in captured["prompt"]
    assert "private-contract-version" not in captured["prompt"]
    assert result["teaching_strategy"] == "general_explanation"


def test_service_control_validation_skips_proposed_type_resolution(monkeypatch):
    payload = _payload("M1", "conceptual_change")
    payload["group_condition"] = "control"
    calls: list[dict] = []

    def unexpected_mandatory_type(_payload):
        raise AssertionError("control validation must not resolve a proposed-group type")

    async def fake_ai_call(_db, purpose, request_payload):
        assert purpose == "generate_tutoring_turn"
        calls.append(request_payload)
        return {
            "tutor_message": "## 記憶プロセス\n\n### 要点\n- 情報を保存し検索します。",
            "teaching_strategy": "general_explanation",
        }

    monkeypatch.setattr(experiment_service, "expected_mandatory_type", unexpected_mandatory_type)
    monkeypatch.setattr(experiment_service, "_ai_call", fake_ai_call)
    result, validation = asyncio.run(experiment_service._generate_validated_tutoring_turn(None, payload))

    assert validation["valid"]
    assert validation["expected_type"] is None
    assert calls[0]["generation_attempt"] == 1
    assert result["teaching_strategy"] == "general_explanation"


def test_control_audit_keeps_original_contract_and_generation_attempt(monkeypatch):
    backend = CodexAppServerBackend()
    payload = {
        "group_condition": "control",
        "term": {"slug": "memory_process", "label": "記憶プロセス", "description": "情報を保存し検索する仕組みです。"},
        "prompt_contract_version": "audit-contract-v7",
        "taxonomy_version": "audit-taxonomy-v4",
        "generation_attempt": 3,
        "mandatory_element_retry": {"attempt": 2, "missing": ["private-validation-detail"]},
        "learner_state": {"primary_misconception": "PRIVATE-M1"},
        "rag_context": {"query": "common query", "allowed_sections": ["3.2"], "chunks": []},
    }
    captured: dict[str, object] = {}

    async def capture(purpose, prompt, output_schema, **kwargs):
        captured.update(purpose=purpose, prompt=prompt, schema=output_schema, **kwargs)
        return {"tutor_message": "## 記憶プロセス\n\n### 要点\n- 情報を保存し検索します。", "teaching_strategy": "general_explanation"}

    monkeypatch.setattr(backend, "_run_structured_turn", capture)
    asyncio.run(backend.generate_tutoring_turn(payload))

    assert "PRIVATE-M1" not in captured["prompt"]
    assert "audit-contract-v7" not in captured["prompt"]
    assert "private-validation-detail" not in captured["prompt"]
    audit_context = captured["audit_context"]
    assert audit_context["prompt_contract_version"] == "audit-contract-v7"
    assert audit_context["taxonomy_version"] == "audit-taxonomy-v4"
    assert audit_context["generation_attempt"] == 3
    assert audit_context["rag_retrieval"]["query"] == "common query"
    retry_only_audit = backend._audit_context(
        {"mandatory_element_retry": {"attempt": 2}}, generation=True
    )
    assert retry_only_audit["generation_attempt"] == 2


def test_codex_unknown_prompt_has_empty_claim_contract(monkeypatch):
    backend = CodexAppServerBackend()
    payload = _payload("unknown", "enrichment")
    payload["pretest_targets"] = [
        {"claim_id": "memory_process:pretest:D", "misconception_type": "M1"}
    ]
    captured: dict[str, object] = {}
    mock_result = asyncio.run(MockAIBackend().generate_tutoring_turn(payload))

    async def capture(purpose, prompt, output_schema, **kwargs):
        captured["prompt"] = prompt
        captured["schema"] = output_schema
        return mock_result

    monkeypatch.setattr(backend, "_run_structured_turn", capture)
    asyncio.run(backend.generate_tutoring_turn(payload))

    prompt = captured["prompt"]
    assert "unknownのteaching_contractはtarget_claim_idをnull" in prompt
    assert "pretest_targetsの全claim_idをaddressed_claim_idsへ入れる" not in prompt
    assert "memory_process:pretest:D" not in prompt
    assert "teaching_contract" in captured["schema"]["properties"]


def test_control_tutoring_prompt_is_independent_of_participant_diagnostics_and_fixed_questions(monkeypatch):
    backend = CodexAppServerBackend()
    shared_rag = {
        "query": "記憶プロセス 保存 検索",
        "topic_slug": "memory_process",
        "allowed_sections": ["3.2"],
        "chunks": [{"chunk_id": "chunk-1", "text": "保存した情報を検索して利用する。"}],
    }
    prompts: list[str] = []

    async def capture(purpose, prompt, output_schema, **kwargs):
        prompts.append(prompt)
        return {"tutor_message": "## 記憶プロセス\n\n### 要点\n- 情報を保存し検索します。", "teaching_strategy": "general_explanation"}

    monkeypatch.setattr(backend, "_run_structured_turn", capture)
    common = {
        "group_condition": "control",
        "term": {"slug": "memory_process", "label": "記憶プロセス", "description": "情報を保存し、必要な時に検索する仕組みです。"},
        "component_term": "検索",
        "component_index": 1,
        "component_total": 1,
        "component_terms": ["記憶プロセス"],
        "rag_context": shared_rag,
    }
    first = {
        **common,
        "participant_id": "P-ONE",
        "learning_stage": "STAGE-ONE",
        "learner_state": {"primary_misconception": "M1-PRIVATE"},
        "previous_learner_response": "RESPONSE-ONE",
        "fixed_practice_question": {"body": "QUESTION-ONE", "options": ["OPTION-ONE"], "expected_answer": "ANSWER-ONE"},
    }
    second = {
        **common,
        "participant_id": "P-TWO",
        "learning_stage": "STAGE-TWO",
        "learner_state": {"primary_misconception": "M3-PRIVATE"},
        "previous_learner_response": "RESPONSE-TWO",
        "fixed_practice_question": {"body": "QUESTION-TWO", "options": ["OPTION-TWO"], "expected_answer": "ANSWER-TWO"},
        "session_misconception_history": ["HISTORY-TWO"],
    }

    asyncio.run(backend.generate_tutoring_turn(first))
    asyncio.run(backend.generate_tutoring_turn(second))

    assert prompts[0] == prompts[1]
    for private_value in ("P-ONE", "P-TWO", "control", "STAGE-ONE", "STAGE-TWO", "M1-PRIVATE", "M3-PRIVATE", "QUESTION-ONE", "QUESTION-TWO", "OPTION-ONE", "ANSWER-TWO", "RESPONSE-ONE", "HISTORY-TWO"):
        assert private_value not in prompts[0]
    assert "記憶プロセス" in prompts[0]
    assert "chunk-1" in prompts[0]
    assert "通常のAIチューター" in prompts[0]


def test_control_feedback_uses_only_current_feedback_context_for_both_outcomes(monkeypatch):
    backend = CodexAppServerBackend()
    prompts: list[str] = []

    async def capture(purpose, prompt, output_schema, **kwargs):
        prompts.append(prompt)
        if purpose == "generate_correct_answer_summary":
            return {"summary": "## 今回の要点\n- 説明します。"}
        return {"feedback": "## どこが違うか\n- 確認します。", "remediation_focus": "仕組みを確認する。", "general_knowledge_supplement": None}

    monkeypatch.setattr(backend, "_run_structured_turn", capture)
    payload = {
        "participant_id": "P-FEEDBACK",
        "group_condition": "control",
        "term": {"slug": "memory_process", "label": "記憶プロセス", "description": "情報を保存し検索する仕組みです。"},
        "learning_stage": "STAGE-PRIVATE",
        "component_term": "検索",
        "question_body": "CURRENT_QUESTION",
        "selected_option_body": "CURRENT_SELECTION",
        "selected_option_bodies": ["CURRENT_SELECTION"],
        "material": "CURRENT_MATERIAL",
        "rag_context": {"query": "COMMON_QUERY", "allowed_sections": ["3.2"], "chunks": [{"chunk_id": "current-chunk", "text": "COMMON_RAG_TEXT"}]},
        "learner_state": {"primary_misconception": "PRIVATE_DIAGNOSIS"},
        "misconception_taxonomy": {"M1": "PRIVATE_TAXONOMY"},
        "session_misconception_history": ["PRIVATE_HISTORY"],
    }

    asyncio.run(backend.generate_correct_answer_summary(payload))
    asyncio.run(backend.explain_selected_distractor(payload))

    assert len(prompts) == 2
    for prompt in prompts:
        for private_value in ("P-FEEDBACK", "control", "STAGE-PRIVATE", "PRIVATE_DIAGNOSIS", "PRIVATE_TAXONOMY", "PRIVATE_HISTORY"):
            assert private_value not in prompt
        for current_value in ("CURRENT_QUESTION", "CURRENT_SELECTION", "CURRENT_MATERIAL", "COMMON_QUERY", "COMMON_RAG_TEXT"):
            assert current_value in prompt


def test_teaching_contract_rejects_unknown_claim_and_empty_refutation():
    payload = _payload("M1", "conceptual_change")
    target = {
        "claim_id": "memory_process:pretest:E",
        "misconception_type": "M1",
        "observed_claim": "保存した情報は常に正しい。",
        "corrected_claim": "保存した情報は検証して使う。",
        "mechanism_explanation": "保存情報の誤りや古さを確認するためです。",
        "contrast_example": "根拠を確認して使う場合と無条件で信じる場合を比べます。",
    }
    payload["pretest_target"] = target
    payload["pretest_targets"] = [target]
    result = asyncio.run(MockAIBackend().generate_tutoring_turn(payload))
    result["teaching_contract"]["target_claim_id"] = "memory_process:pretest:D"
    result["teaching_contract"]["corrected_claim"] = ""

    validation = validate_teaching_contract(result, "M1", payload, payload["term"]["label"])

    assert not validation["valid"]
    assert "target_claim_id:expected_one_of_memory_process:pretest:E" in validation["missing"]
    assert "corrected_claim:empty" in validation["missing"]


def test_material_safety_rejects_fixed_answer_text():
    payload = _payload("M1", "conceptual_change")
    result = asyncio.run(MockAIBackend().generate_tutoring_turn(payload))
    answer_text = "A、B、Cをすべて選択し、それ以外を選ばない。"

    validation = validate_tutoring_material_safety(result, [answer_text])
    assert validation["valid"]

    result["tutor_message"] += f"\n{answer_text}"
    validation = validate_tutoring_material_safety(result, [answer_text])
    assert not validation["valid"]


def test_mandatory_schema_is_strict_for_each_type():
    expected_fields = {
        "M1": {"type", "wrong_belief", "correct_belief", "counterexample", "reason"},
        "M3": {"type", "wrong_category", "correct_category", "boundary_criterion", "contrast_example"},
        "unknown": {"type", "definition", "components", "role", "decision_criterion", "positive_example", "non_example"},
    }
    for misconception_type in ("M1", "M3", "unknown"):
        schema = mandatory_elements_schema(misconception_type)
        assert set(schema["required"]) == set(schema["properties"])
        assert set(schema["properties"]) == expected_fields[misconception_type]
        assert schema["properties"]["type"]["enum"] == [misconception_type]
