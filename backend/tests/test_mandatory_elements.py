from __future__ import annotations

import asyncio

from app.services import experiment as experiment_service
from app.ai.mandatory_elements import (
    expected_mandatory_type,
    mandatory_element_headings,
    mandatory_elements_schema,
    validate_mandatory_elements,
)
from app.ai.codex_app_server_backend import CodexAppServerBackend
from app.ai.mock_backend import MockAIBackend
from app.ai.teaching_contract import teaching_contract_schema, validate_teaching_contract
from app.seed.content_loader import ACTIVE_TERM_SLUGS, load_content, teaching_target_for_option


def _payload(misconception_type: str, stage: str) -> dict:
    payload = {
        "group_condition": "proposed",
        "active_misconception_type": misconception_type,
        "learning_stage": stage,
        "term": {
            "label": "記憶プロセス",
            "description": "情報を保存し、検索して現在の処理へ渡し、必要に応じて更新する仕組みです。",
        },
        "fixed_practice_question": {"body": "適切な説明を選びなさい。"},
    }
    if misconception_type == "M1":
        target = {
            "claim_id": "memory_process:pretest:E",
            "observed_claim": "保存した情報は常に正しい。",
            "corrected_claim": "保存した情報は検証して使う。",
            "mechanism_explanation": "保存情報には誤りや古さがあり、確認が必要です。",
            "contrast_example": "根拠を確認する記憶と無条件に信じる記憶を比較します。",
        }
        payload["pretest_targets"] = [target]
        payload["pretest_target"] = target
    elif misconception_type == "M3":
        target = {
            "claim_id": "memory_process:pretest:G",
            "observed_claim": "記憶は重みと同じです。",
            "corrected_claim": "記憶は外部情報を管理する処理です。",
            "mechanism_explanation": "保存と検索はモデルの重み更新とは別に行います。",
            "contrast_example": "外部記憶と重み更新を比較します。",
            "wrong_category": "モデル内部の重み",
            "correct_category": "外部情報の管理処理",
            "boundary_criterion": "重み更新か外部保存かで分けます。",
        }
        payload["pretest_targets"] = [target]
        payload["pretest_target"] = target
    return payload


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
            if option.get("misconception_type") in {"M1", "M3"}:
                target = teaching_target_for_option(term["slug"], option["label"])
                assert target is not None
                assert target["corrected_claim"]
                assert target["mechanism_explanation"]
                assert target["contrast_example"]
                if option["misconception_type"] == "M3":
                    assert target["wrong_category"]
                    assert target["correct_category"]
                    assert target["boundary_criterion"]


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
        contract_validation = validate_teaching_contract(result, misconception_type, payload, payload["term"]["label"])
        assert contract_validation["valid"], contract_validation
        assert result["teaching_contract"]["target_addressed"] is True
        assert "### 要点" not in result["tutor_message"]
        assert "### 具体例" not in result["tutor_message"]
        assert "### 注意点" not in result["tutor_message"]
        for heading in mandatory_element_headings(misconception_type).values():
            assert f"### {heading}" in result["tutor_message"]


def test_validator_rejects_evidence_not_present_in_visible_material():
    backend = MockAIBackend()
    payload = _payload("M1", "conceptual_change")
    result = asyncio.run(backend.generate_tutoring_turn(payload))
    result["mandatory_elements"]["counterexample"] = "教材本文に存在しない反例です。"

    validation = validate_mandatory_elements(result, "M1", payload["term"]["label"])

    assert not validation["valid"]
    assert "counterexample:evidence_not_in_tutor_message" in validation["missing"]


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

    async def capture(purpose, prompt, output_schema):
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
    assert "expected_answer" not in schema["properties"]["practice_question"]["properties"]
    nested_schema = schema["properties"]["mandatory_elements"]
    assert set(nested_schema["required"]) == set(nested_schema["properties"])
    assert "wrong_category" not in nested_schema["properties"]
    assert "wrong_belief" in captured["prompt"]
    assert "counterexample" in captured["prompt"]


def test_teaching_contract_rejects_unknown_claim_and_empty_refutation():
    payload = _payload("M1", "conceptual_change")
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
    from app.ai.teaching_contract import validate_tutoring_material_safety

    validation = validate_tutoring_material_safety(result, ["A、B、Cをすべて選択し、それ以外を選ばない。"])
    assert validation["valid"]
    result["tutor_message"] += "\nA、B、Cをすべて選択し、それ以外を選ばない。"
    validation = validate_tutoring_material_safety(result, ["A、B、Cをすべて選択し、それ以外を選ばない。"])
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
