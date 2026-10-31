from __future__ import annotations

import asyncio

import pytest

from app.ai.mock_backend import MockAIBackend
from app.ai.teaching_contract import material_length_contract, validate_tutoring_material_length
from app.ai.tutoring_prompt import build_tutoring_prompt
from app.db.session import SessionLocal
from app.models import AICallLog
from app.services import experiment as experiment_service


@pytest.mark.parametrize(
    "integrated_material,target,maximum",
    [(False, 700, 800), (True, 1000, 1200)],
)
def test_mode_specific_material_length_boundaries(integrated_material, target, maximum):
    contract = material_length_contract(integrated_material=integrated_material)
    assert contract == {
        "target_character_count": target,
        "min_character_count": 600,
        "max_character_count": maximum,
    }

    assert validate_tutoring_material_length(
        {"tutor_message": "あ" * 600}, integrated_material=integrated_material,
    )["valid"]
    assert validate_tutoring_material_length(
        {"tutor_message": "あ" * maximum}, integrated_material=integrated_material,
    )["valid"]
    assert not validate_tutoring_material_length(
        {"tutor_message": "あ" * 599}, integrated_material=integrated_material,
    )["valid"]
    too_long = validate_tutoring_material_length(
        {"tutor_message": "あ" * (maximum + 1)}, integrated_material=integrated_material,
    )
    assert not too_long["valid"]
    assert too_long["max_character_count"] == maximum


def _prompt_payload(*, integrated_material: bool) -> dict:
    payload = {
        "term": {"label": "記憶プロセス", "description": "記録を保存し、必要な情報を処理へ渡す仕組みです。"},
        "component_terms": [],
        "rag_context": {"chunks": []},
        "interaction_history": [],
    }
    if integrated_material:
        payload["glossary_reference"] = {
            "version": "learning-glossary-v2",
            "entries": [{"id": "weights", "term": "重み", "definition": "学習で調整される内部数値です。"}],
        }
    return payload


def _prompt(payload: dict, *, retry_context: dict | None = None) -> str:
    return build_tutoring_prompt(
        payload,
        retry_context=retry_context,
        group="control",
        expected_type=None,
        term_label="記憶プロセス",
        teaching_strategies=["general_explanation"],
    )


def test_prompt_uses_mode_specific_target_range_and_retry_instruction():
    annotation_prompt = _prompt(_prompt_payload(integrated_material=False))
    assert "700文字前後（600〜800文字）" in annotation_prompt
    assert "1000文字前後（600〜1200文字）" not in annotation_prompt

    payload = _prompt_payload(integrated_material=True)
    integrated_prompt = _prompt(payload)
    assert "1000文字前後（600〜1200文字）" in integrated_prompt
    assert "本文600〜1200文字の条件を維持する" in integrated_prompt

    retry_prompt = _prompt(
        payload,
        retry_context={
            "material_length_retry": {
                "target_character_count": 1000,
                "min_character_count": 600,
                "max_character_count": 1200,
                "actual_character_count": 1201,
            }
        },
    )
    assert "前回の教材本文は1201文字" in retry_prompt
    assert "1000文字前後（600〜1200文字）に必ず収める" in retry_prompt


@pytest.mark.parametrize(
    "integrated_material,target,maximum",
    [(False, 700, 800), (True, 1000, 1200)],
)
def test_mock_generation_uses_mode_specific_target(integrated_material, target, maximum):
    payload = {
        "group_condition": "proposed",
        "active_misconception_type": "unknown",
        "learning_stage": "enrichment",
        "term": {"label": "記憶プロセス", "description": "情報を保存し検索して処理へ渡します。"},
        "component_terms": [],
        "rag_context": {"chunks": []},
        "interaction_history": [],
    }
    if integrated_material:
        payload["glossary_reference"] = {
            "version": "learning-glossary-v2",
            "entries": [{"id": "weights", "term": "重み", "definition": "学習で調整される内部数値です。"}],
        }

    result = asyncio.run(MockAIBackend().generate_tutoring_turn(payload))

    assert target <= len(result["tutor_message"]) <= maximum


def test_integrated_material_retry_uses_1200_character_contract(monkeypatch):
    payload = {
        "group_condition": "proposed",
        "active_misconception_type": "M1",
        "learning_stage": "conceptual_change",
        "term": {
            "label": "記憶プロセス",
            "description": "情報を保存して検索し、現在の処理へ渡す仕組みです。",
        },
        "fixed_practice_question": {"body": "適切な説明を選びなさい。"},
        "glossary_reference": {"version": "learning-glossary-v2", "entries": []},
    }
    calls = []

    async def fake_ai_call(db, purpose, request_payload):
        assert purpose == "generate_tutoring_turn"
        calls.append(request_payload)
        result = await MockAIBackend().generate_tutoring_turn(request_payload)
        if len(calls) == 1:
            result["tutor_message"] = "あ" * 1201
        return result

    monkeypatch.setattr(experiment_service, "_ai_call", fake_ai_call)
    result, validation = asyncio.run(
        experiment_service._generate_validated_tutoring_turn(None, payload)
    )

    assert validation["valid"]
    assert validation["attempts"] == 2
    assert validation["material_length"]["target_character_count"] == 1000
    assert validation["material_length"]["max_character_count"] == 1200
    assert len(result["tutor_message"]) >= 1000
    assert calls[1]["material_length_retry"] == {
        "attempt": 2,
        "target_character_count": 1000,
        "min_character_count": 600,
        "max_character_count": 1200,
        "actual_character_count": 1201,
    }


def test_tutoring_output_metrics_use_integrated_material_contract():
    metrics = experiment_service._tutoring_output_metrics(
        {"tutor_message": "あ" * 1100}, integrated_material=True,
    )
    assert metrics["target_character_count"] == 1000
    assert metrics["min_character_count"] == 600
    assert metrics["max_character_count"] == 1200
    assert metrics["character_count_in_target_range"] == 1


@pytest.mark.parametrize(
    "integrated_material,target,maximum",
    [(False, 700, 800), (True, 1000, 1200)],
)
def test_ai_call_persists_mode_specific_material_metrics(monkeypatch, integrated_material, target, maximum):
    class FakeBackend:
        provider = "material-contract-test"

        async def generate_tutoring_turn(self, payload):
            assert ("glossary_reference" in payload) is integrated_material
            character_count = 1100 if integrated_material else 700
            return {"tutor_message": "あ" * character_count}

    monkeypatch.setattr(experiment_service, "get_ai_backend", lambda **_kwargs: FakeBackend())
    payload = {"term": {"label": "検証用語"}}
    if integrated_material:
        payload["glossary_reference"] = {"version": "learning-glossary-v2", "entries": []}

    db = SessionLocal()
    log = None
    try:
        result = asyncio.run(
            experiment_service._ai_call(db, "generate_tutoring_turn", payload)
        )
        log = (
            db.query(AICallLog)
            .filter_by(provider="material-contract-test", purpose="generate_tutoring_turn")
            .order_by(AICallLog.created_at.desc())
            .first()
        )
        assert log is not None
        expected_character_count = 1100 if integrated_material else 700
        for metrics in (result["output_metrics"], log.response_payload["output_metrics"]):
            assert metrics["character_count"] == expected_character_count
            assert metrics["target_character_count"] == target
            assert metrics["min_character_count"] == 600
            assert metrics["max_character_count"] == maximum
            assert metrics["character_count_in_target_range"] == 1
    finally:
        if log is not None:
            db.delete(log)
            db.commit()
        db.close()
