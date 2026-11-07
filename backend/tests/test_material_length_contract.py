from __future__ import annotations

import asyncio

import pytest

from app.ai.mock_backend import MockAIBackend
from app.ai.teaching_contract import material_length_contract, tutoring_material_length_metrics
from app.ai.tutoring_prompt import build_tutoring_prompt
from app.db.session import SessionLocal
from app.models import AICallLog
from app.services import experiment as experiment_service


def test_material_length_contract_contains_only_the_target():
    assert material_length_contract() == {"target_character_count": 800}
    assert tutoring_material_length_metrics({"tutor_message": "あ" * 120}) == {
        "character_count": 120,
        "target_character_count": 800,
    }


def _prompt_payload(*, integrated_material: bool) -> dict:
    payload = {
        "term": {"label": "記憶プロセス", "description": "記録を保存し、必要な情報を処理へ渡す仕組みです。"},
        "component_terms": [],
        "rag_context": {"chunks": []},
        "interaction_history": [],
    }
    if integrated_material:
        payload["glossary_reference"] = {
            "version": "learning-glossary-v4",
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


@pytest.mark.parametrize("integrated_material", [False, True])
def test_prompt_sets_only_the_800_character_target(integrated_material):
    payload = _prompt_payload(integrated_material=integrated_material)
    prompt = _prompt(
        payload,
        retry_context={
            "material_length_retry": {
                "actual_character_count": 1201,
                "min_character_count": 600,
                "max_character_count": 1200,
            }
        },
    )

    assert "800文字程度を目安とする" in prompt
    for obsolete_constraint in ("600〜800", "600〜1200", "許容範囲外", "必ず収める", "上限", "下限"):
        assert obsolete_constraint not in prompt
    if integrated_material:
        assert "定義文をそのまま転載するためではなく、意味を確認する参考情報として使う" in prompt
        assert "辞書の定義文をそのまま引用・転記せず、自分の言葉で言い換える" in prompt


@pytest.mark.parametrize("integrated_material", [False, True])
def test_mock_generation_uses_the_800_character_target(integrated_material):
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
            "version": "learning-glossary-v4",
            "entries": [{"id": "weights", "term": "重み", "definition": "学習で調整される内部数値です。"}],
        }

    result = asyncio.run(MockAIBackend().generate_tutoring_turn(payload))

    assert len(result["tutor_message"]) >= 800


@pytest.mark.parametrize("character_count", [80, 2000])
def test_out_of_target_length_is_accepted_without_retry(monkeypatch, character_count):
    payload = {
        "group_condition": "control",
        "term": {"slug": "memory_process", "label": "記憶プロセス", "description": "情報を保存します。"},
    }
    calls = []
    message = "## 記憶プロセス\n\n### 要点\n\n" + "あ" * (character_count - len("## 記憶プロセス\n\n### 要点\n\n"))

    async def fake_ai_call(_db, purpose, request_payload):
        assert purpose == "generate_tutoring_turn"
        calls.append(request_payload)
        return {"tutor_message": message, "teaching_strategy": "general_explanation"}

    monkeypatch.setattr(experiment_service, "_ai_call", fake_ai_call)
    result, validation = asyncio.run(
        experiment_service._generate_validated_tutoring_turn(None, payload)
    )

    assert result["tutor_message"] == message
    assert validation["valid"]
    assert validation["attempts"] == 1
    assert validation["material_length_metrics"] == {
        "character_count": character_count,
        "target_character_count": 800,
    }
    assert len(calls) == 1
    assert "material_length_retry" not in calls[0]


@pytest.mark.parametrize("character_count", [80, 2000])
def test_ai_call_logs_actual_count_and_target_only(monkeypatch, character_count):
    class FakeBackend:
        provider = "material-contract-test"

        async def generate_tutoring_turn(self, _payload):
            return {"tutor_message": "あ" * character_count}

    monkeypatch.setattr(experiment_service, "get_ai_backend", lambda **_kwargs: FakeBackend())
    db = SessionLocal()
    log = None
    try:
        result = asyncio.run(
            experiment_service._ai_call(db, "generate_tutoring_turn", {"term": {"label": "検証用語"}})
        )
        log = (
            db.query(AICallLog)
            .filter_by(provider="material-contract-test", purpose="generate_tutoring_turn")
            .order_by(AICallLog.created_at.desc(), AICallLog.id.desc())
            .first()
        )
        assert log is not None
        for metrics in (result["output_metrics"], log.response_payload["output_metrics"]):
            assert metrics["character_count"] == character_count
            assert metrics["target_character_count"] == 800
            assert "min_character_count" not in metrics
            assert "max_character_count" not in metrics
            assert "character_count_in_target_range" not in metrics
    finally:
        if log is not None:
            db.delete(log)
            db.commit()
        db.close()
