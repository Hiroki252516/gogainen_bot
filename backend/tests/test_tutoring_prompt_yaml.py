from __future__ import annotations

import copy
import hashlib

import pytest
import yaml

from app.ai.tutoring_prompt import PROMPT_TEXT_PATH, _validate_prompt_text, build_tutoring_prompt


def _base_payload() -> dict:
    return {
        "term": {
            "slug": "llm_knowledge",
            "label": "LLMに知識を与える方法",
            "description": "AIへ情報や能力を与える方法です。",
        },
        "component_terms": [],
        "rag_context": {"chunks": []},
        "interaction_history": [],
    }


def _render(payload, *, group, expected_type, strategies, retry_context=None) -> str:
    return build_tutoring_prompt(
        payload,
        retry_context=retry_context,
        group=group,
        expected_type=expected_type,
        term_label=payload["term"]["label"],
        teaching_strategies=strategies,
    )


def test_prompt_yaml_is_valid_and_rejects_missing_required_sections():
    raw = yaml.safe_load(PROMPT_TEXT_PATH.read_text(encoding="utf-8"))
    assert _validate_prompt_text(raw) == raw

    invalid = copy.deepcopy(raw)
    del invalid["tutoring"]["group_rules"]["proposed"]
    with pytest.raises(ValueError, match="group_rules.proposed"):
        _validate_prompt_text(invalid)


def test_rendered_prompt_matches_expected_contract_hashes():
    rendered = {}

    payload = _base_payload()
    rendered["control_annotation"] = _render(
        payload,
        group="control",
        expected_type=None,
        strategies=["general_explanation"],
    )

    payload = _base_payload()
    payload["glossary_reference"] = {
        "version": "learning-glossary-v2",
        "entries": [{"id": "weights", "term": "重み", "definition": "学習で調整される内部数値です。"}],
    }
    rendered["control_integrated"] = _render(
        payload,
        group="control",
        expected_type=None,
        strategies=["general_explanation"],
    )

    payload = _base_payload()
    payload.update(
        {
            "misconception_taxonomy": {
                "M1": {"definition": "誤信念"},
                "M3": {"definition": "カテゴリー誤り"},
                "unknown": {"definition": "基礎説明"},
            },
            "active_misconception_type": "M1",
            "learning_scope": {"topics": ["検索"], "selected_errors": ["例を見せれば学習する"]},
            "pretest_targets": [{"claim_id": "c1"}],
            "diagnostic_evidence": {"selected_options": [{"body": "例を見せれば学習する"}]},
        }
    )
    rendered["proposed_m1_retry_counted"] = _render(
        payload,
        group="proposed",
        expected_type="M1",
        strategies=["belief_revision"],
        retry_context={
            "material_length_retry": {"actual_character_count": 599},
            "mandatory_element_retry": {"missing": ["wrong_belief:empty", "teaching_strategy.mismatch"]},
        },
    )

    payload = _base_payload()
    payload.update(
        {
            "glossary_reference": {"version": "learning-glossary-v2", "entries": []},
            "misconception_taxonomy": {"M3": {"definition": "カテゴリー誤り"}},
            "active_misconception_type": "M3",
            "learning_scope": {"topics": ["役割"], "selected_errors": []},
        }
    )
    rendered["proposed_m3_integrated"] = _render(
        payload,
        group="proposed",
        expected_type="M3",
        strategies=["category_reorientation"],
    )

    payload = _base_payload()
    payload.update(
        {
            "misconception_taxonomy": {"unknown": {"definition": "基礎説明"}},
            "active_misconception_type": "unknown",
            "learning_scope": {"topics": ["仕組み"], "selected_errors": []},
        }
    )
    rendered["proposed_unknown_retry_uncounted"] = _render(
        payload,
        group="proposed",
        expected_type="unknown",
        strategies=["foundational_explanation"],
        retry_context={
            "material_length_retry": {"actual_character_count": "bad"},
            "mandatory_element_retry": {"missing": ["definition:empty"]},
        },
    )

    expected_hashes = {
        "control_annotation": "5edbe59e4bff8265a5913dd9a3adaacb9afd57806367a093edeb92f67f686994",
        "control_integrated": "a24bbe64263f8abcb4e4fedf08b17b41c38a2dea10442c8444ceac73ba70c66a",
        "proposed_m1_retry_counted": "2fa8a9de65971995e167ac5ee7d2c8a2cf61be7e70c208dad0392b7927661763",
        "proposed_m3_integrated": "6939f35c48a688d70d60f7ed7cc4b9aceff57526fd19f4d0b659c97b103e1b1e",
        "proposed_unknown_retry_uncounted": "d109b93ffd4ecbf994c2c9cca4b3229205e5cdf6b544dc86515ecf1c2186c18d",
    }
    assert {name: hashlib.sha256(prompt.encode("utf-8")).hexdigest() for name, prompt in rendered.items()} == expected_hashes
