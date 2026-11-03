from pathlib import Path

import pytest
import yaml

from app.seed.import_split_assessment_draft import parse_draft, validate


DRAFT = Path(__file__).parents[1] / "app/seed/content/standard/split_assessment_v1.yml"


def test_draft_contains_all_rounds_terms_and_three_four_choice_questions():
    data = yaml.safe_load(DRAFT.read_text(encoding="utf-8"))
    assert data["status"] == "active_standard_split_v1"
    validate(data["rounds"])
    assert sum(len(section["questions"]) for terms in data["rounds"].values() for section in terms.values()) == 27
    first = data["rounds"]["pretest_v1"]["llm_knowledge"]["questions"][0]
    assert first["choices"]["M1"]["body"].startswith("問い合わせに関係する取扱説明書を回答時に参照させる。")
    assert first["choices"]["unknown"]["body"] == "わからない。"


def test_import_preserves_paragraphs_and_choice_text():
    text = """## 問題1：例
### 共通の場面
一段落。

二段落。
### 設問1：見出し
最も適切なものを1つ選びなさい。
- A【正解】正しい。
- B【M1】誤り1。
- C【M3】誤り3。
- D【わからない】わからない。
"""
    section = parse_draft(text, "pretest_v1")["pretest_v1"]["llm_knowledge"]
    assert section["scenario"] == "一段落。\n\n二段落。"
    assert section["questions"][0]["choices"][2] == {"role": "M3", "label": "C", "body": "誤り3。"}


def test_import_preserves_duplicate_roles_in_six_choice_drafts():
    text = """## 問題1：例
### 共通の場面
場面。
### 設問1：見出し
最も適切なものを1つ選びなさい。
- A【正解】正しい。
- B【M1】誤り1。
- C【M1】誤り2。
- D【M3】誤り3。
- E【M3】誤り4。
- F【わからない】わからない。
"""
    section = parse_draft(text, "pretest_v1")["pretest_v1"]["llm_knowledge"]
    choices = section["questions"][0]["choices"]
    assert [choice["label"] for choice in choices] == list("ABCDEF")
    assert [choice["role"] for choice in choices] == ["correct", "M1", "M1", "M3", "M3", "unknown"]


def test_invalid_draft_is_rejected():
    with pytest.raises(ValueError):
        validate({"pretest_v1": {}})
