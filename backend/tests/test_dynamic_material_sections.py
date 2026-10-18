import asyncio
import copy

import pytest
from fastapi import HTTPException

from app.ai.codex_app_server_backend import CodexAppServerBackend
from app.ai.material_structure import validate_material_structure
from app.ai.mandatory_elements import validate_mandatory_elements
from app.ai.mock_backend import MockAIBackend
from app.ai.teaching_contract import validate_teaching_contract
from app.services import experiment


def payload(kind="M1", group="proposed"):
    return {
        "group_condition": group,
        "active_misconception_type": kind,
        "term": {"label": "記憶プロセス", "slug": "memory_process", "description": "情報を保存し、検索して利用する仕組みです。"},
    }


@pytest.mark.parametrize("kind", ["M1", "M3", "unknown"])
@pytest.mark.parametrize("count", [1, 2, 3, 6])
def test_arbitrary_order_count_and_merged_evidence_are_valid(kind, count):
    data = payload(kind)
    result = asyncio.run(MockAIBackend().generate_tutoring_turn(data))
    elements = result["mandatory_elements"]
    evidence = [value for field, value in elements.items() if field != "type"]
    evidence += [value for field, value in result["teaching_contract"].items()
                 if field in {"corrected_claim", "mechanism_explanation", "contrast_example", "transfer_check"} and value]
    evidence.reverse()
    headings = ["要点", "具体例", "注意点", "どう働くか", "別の場面で考える", "まとめ"]
    result["tutor_message"] = "## 記憶プロセス\n\n" + "\n\n".join(
        f"### {headings[index]}\n" + ("\n".join(f"- {value}" for value in evidence[index::count]) or "- 用語の意味と働きを整理します。")
        for index in range(count)
    )
    assert validate_mandatory_elements(result, kind, "記憶プロセス")["valid"]
    assert validate_teaching_contract(result, kind, data, "記憶プロセス")["valid"]
    structure = validate_material_structure(result, "記憶プロセス")
    assert structure["valid"], structure
    assert structure["headings"] == headings[:count]
    assert [section["index"] for section in structure["sections"]] == list(range(1, count + 1))
    assert all(structure["evidence_placements"]["mandatory_elements"].values())
    if count == 1:
        assert all(indices == [1] for indices in structure["evidence_placements"]["mandatory_elements"].values())


@pytest.mark.parametrize("object_name,field", [("mandatory_elements", "counterexample"), ("teaching_contract", "transfer_check")])
def test_heading_only_evidence_is_rejected(object_name, field):
    data = payload()
    result = asyncio.run(MockAIBackend().generate_tutoring_turn(data))
    evidence = "この文章は見出しだけに存在する検証用の説明です。"
    result[object_name][field] = evidence
    result["tutor_message"] += f"\n\n### {evidence}\nセクションの本文です。"
    validation = (validate_mandatory_elements(result, "M1", "記憶プロセス") if object_name == "mandatory_elements"
                  else validate_teaching_contract(result, "M1", data, "記憶プロセス"))
    assert not validation["valid"]
    assert f"{field}:evidence_not_in_section" in validation["missing"]


@pytest.mark.parametrize("placement", ["title_intro", "fenced_code", "html"])
def test_evidence_outside_rendered_section_body_is_rejected(placement):
    data = payload()
    result = asyncio.run(MockAIBackend().generate_tutoring_turn(data))
    evidence = "これはセクションの本文には表示されない証拠です。"
    result["mandatory_elements"]["reason"] = evidence
    if placement == "title_intro":
        result["tutor_message"] = result["tutor_message"].replace("## 記憶プロセス", f"## 記憶プロセス\n\n{evidence}", 1)
    elif placement == "fenced_code":
        result["tutor_message"] += f"\n\n```\n{evidence}\n```"
    else:
        result["tutor_message"] += f"\n\n<!-- {evidence} -->"
    validation = validate_mandatory_elements(result, "M1", "記憶プロセス")
    assert not validation["valid"]
    assert "reason:evidence_not_in_section" in validation["missing"]


@pytest.mark.parametrize("message", [
    "## 記憶プロセス\n\n本文中の ### 見出し はセクションではない。",
    "## 記憶プロセス\n\n```\n### 偽の見出し\n偽の本文\n```",
    "## 記憶プロセス\n\n> ### 引用内の見出し\n> 引用内の本文",
    "## 記憶プロセス\n\n### 空の節\n\n### 本文のある節\n説明。",
    "## 記憶プロセス\n\n### \n説明。",
    "前置き\n\n## 記憶プロセス\n\n### 概要\n説明。",
    "## 別の用語\n\n### 概要\n説明。",
    "## 記憶プロセス\n\n#### 深すぎる見出し\n説明。",
])
def test_invalid_or_empty_markdown_sections_are_rejected(message):
    assert not validate_material_structure({"tutor_message": message}, "記憶プロセス")["valid"]


def test_repeated_heading_names_are_audited_by_position():
    result = {"tutor_message": "## 記憶プロセス\n\n### 事例\n最初の具体例。\n\n### 事例\n次の具体例。",
              "mandatory_elements": {"counterexample": "次の具体例。"}}
    structure = validate_material_structure(result, "記憶プロセス")
    assert structure["valid"]
    assert structure["headings"] == ["事例", "事例"]
    assert structure["evidence_placements"]["mandatory_elements"]["counterexample"] == [2]


@pytest.mark.parametrize("group,kind", [("control", None), ("proposed", "M1"), ("proposed", "M3"), ("proposed", "unknown")])
def test_both_groups_prompt_allows_free_outline_without_fixed_headings(group, kind):
    data = payload(kind, group)
    backend = CodexAppServerBackend()
    captured = {}

    async def capture(purpose, prompt, output_schema, **kwargs):
        captured.update(prompt=prompt, schema=output_schema)
        return await MockAIBackend().generate_tutoring_turn(data)

    backend._run_structured_turn = capture
    asyncio.run(backend.generate_tutoring_turn(data))
    prompt = captured["prompt"]
    assert "小見出しの文言・数・順序・セクションのまとめ方" in prompt
    for old in ("### 要点", "### 正しい考え", "### 定義", "この順序", "順番どおり"):
        assert old not in prompt
    assert "material_structure" not in captured["schema"]["properties"]
    if group == "control":
        assert "mandatory_elements" not in prompt
        assert "teaching_contract" not in prompt
        assert "misconception_taxonomy" not in prompt
        assert "active_misconception_type" not in prompt


@pytest.mark.parametrize("group,kind", [("control", None), ("proposed", "M1")])
def test_invalid_outline_retries_with_same_backend_and_stops_at_three(monkeypatch, group, kind):
    data = payload(kind, group)
    valid = asyncio.run(MockAIBackend().generate_tutoring_turn(data))
    invalid = copy.deepcopy(valid)
    invalid["tutor_message"] += "\n\n### 空のセクション"
    requests = []

    async def fake_call(db, purpose, request):
        requests.append(copy.deepcopy(request))
        return invalid if len(requests) == 1 else valid

    monkeypatch.setattr(experiment, "_ai_call", fake_call)
    result, validation = asyncio.run(experiment._generate_validated_tutoring_turn(None, data))
    assert result == valid
    assert validation["attempts"] == 2
    assert validation["material_structure"]["valid"]
    assert requests[1]["mandatory_element_retry"]["missing"] == ["tutor_message:section_body_empty:3"]

    async def always_invalid(db, purpose, request):
        requests.append(request)
        return invalid

    requests.clear()
    monkeypatch.setattr(experiment, "_ai_call", always_invalid)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(experiment._generate_validated_tutoring_turn(None, data))
    assert caught.value.status_code == 503
    assert len(requests) == 3


def test_control_retry_gets_structure_errors_without_diagnostic_contract():
    data = {**payload(None, "control"), "mandatory_element_retry": {"missing": ["tutor_message:sections_missing"]}}
    backend = CodexAppServerBackend()

    async def capture(purpose, prompt, output_schema, **kwargs):
        assert "tutor_message:sections_missing" in prompt
        assert "mandatory_elements" not in prompt
        assert "teaching_contract" not in prompt
        return await MockAIBackend().generate_tutoring_turn(data)

    backend._run_structured_turn = capture
    asyncio.run(backend.generate_tutoring_turn(data))
