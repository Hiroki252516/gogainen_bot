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

    invalid = copy.deepcopy(raw)
    invalid["tutoring"]["group_rules"]["control"] = ["control-only instruction"]
    with pytest.raises(ValueError, match="group_rules.control is not supported"):
        _validate_prompt_text(invalid)


def test_tutoring_prompt_rejects_unsupported_group():
    with pytest.raises(ValueError, match="Unsupported tutoring group"):
        _render(
            _base_payload(),
            group="unexpected",
            expected_type=None,
            strategies=["general_explanation"],
        )


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
        "control_annotation": "c8c8af0baf80e2b2373ecbb7be74a11024160bfcec3c334dd27216521369195a",
        "control_integrated": "1721e6b58cfc0a3b7e9b0858c276eda6bbf61030c687f482d499bc979f910b39",
        "proposed_m1_retry_counted": "8fb509032ffff35d8609ddba255041f3ccc9703be5ffbb13364e94737eaadb46",
        "proposed_m3_integrated": "371bef7de24f009149588d9c4a714b7b23c60d0be5b02593f3e9df625fbed15b",
        "proposed_unknown_retry_uncounted": "360a8bf46a59071d1c7d681a121ff495873d42af4a9fc56ae203d0e5304a5076",
    }
    assert {name: hashlib.sha256(prompt.encode("utf-8")).hexdigest() for name, prompt in rendered.items()} == expected_hashes

    control_prompt = rendered["control_annotation"]
    for removed_rule in (
        "通常のAIチューターとして、共通の用語情報、教材コンテキスト、interaction_historyを使い、今回の学習対象を説明する。",
        "general_explanation は、共通の用語情報、教材コンテキスト、回答履歴に基づいて学習対象を説明する通常の教授方略を意味する。",
        "teaching_strategy は general_explanation に固定する。",
        "teaching_strategy はbackendで指定された general_explanation に固定する。",
    ):
        assert removed_rule not in control_prompt
    assert "教材には意味や仕組みの解説を含める。" in control_prompt

    proposed_prompt = rendered["proposed_m1_retry_counted"]
    assert "teaching_strategy はbackendで指定された belief_revision に固定する。" in proposed_prompt
