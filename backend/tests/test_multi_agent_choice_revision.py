from copy import deepcopy
import hashlib

import pytest

from app.seed import content_loader
from app.seed.content_loader import learning_question_spec, load_learning_content


EXPECTED_CHOICES = {
    "correct": [
        "被害状況や道路の情報を集めるAIが調査結果を避難方法の検討担当へ渡し、その検討結果を避難案内文作成担当に引き継ぐようにすれば、複数のAIが分担した作業を順番に繋げられる。",
        "情報収集担当が被害状況と道路の通行状況を整理して避難方法の検討担当に共有し、検討担当がその情報を自分の作業に利用することで、異なる役割のAIが協力して避難案内を作れる。",
        "避難方法の検討担当から避難経路の候補を受け取った避難案内文作成担当は、その情報を参考にして、住民に何をどのような順番で伝えるかを自分の役割として判断できる。"
    ],
    "M1": [
        "情報収集担当のAIが道路の通行状況を調べて避難方法の検討担当へ渡した場合、検討担当は情報源が十分に確認されていると考え、その報告をもとに避難経路を決める。",
        "情報収集担当、避難方法の検討担当、避難案内文作成担当という役割名を各AIに付ければ、どの情報をどの順番で渡すかも自動的に決まるので、受け渡しの仕組みを設計する必要はない。",
        "情報収集担当が道路の通行状況を報告し、避難案内文作成担当がその情報を使って説明を作る場合でも、両者が同じ回答内容を出さなければ、結果を引き継いで連携することはできない。"
    ],
    "M3": [
        "情報収集担当のAIが被害状況や道路の情報をまとめたファイルは、避難方法の検討担当に情報を渡すために使われるので、そのファイルも連携するAIエージェントの一つとして数える。",
        "1つのAIエージェントに、道路が通れる場合と通れない場合で避難案内内容を切り替える仕組みを設け、案内の方法が2つあるので、AIエージェントも2つ存在する。",
        "性能の高いAIエージェントを1つ用意し、情報収集、避難方法の検討、住民向けの避難案内文作成をすべて担当させれば、複数のエージェントが連携するマルチエージェントの仕組みになる。"
    ]
}


def test_v7_only_replaces_the_nine_choices_in_multi_agent_round_one():
    assert hashlib.sha256(content_loader.LEARNING_V6_CONTENT_PATH.read_bytes()).hexdigest() == "4ea616698585d00b4371f014548634a4f8377f363602a5bcb5f970795a3d35d0"
    expected = deepcopy(load_learning_content(content_version=6))
    expected["version"] = 7
    expected["terms"]["multi_agent"]["variants"][0]["choices"] = EXPECTED_CHOICES
    assert load_learning_content(content_version=7) == expected


@pytest.mark.parametrize("stage", ["enrichment", "conceptual_change"])
def test_v7_preserves_the_scenario_and_role_assignment(stage):
    current = learning_question_spec("multi_agent", stage, content_version=7)
    previous = learning_question_spec("multi_agent", stage, content_version=6)
    assert current["body"] == previous["body"]
    assert current["variant_key"] == previous["variant_key"] == "learning_round_v1"
    assert current["scenario_type"] == previous["scenario_type"] == "application"
    assert current["_content_version"] == 7
    assert len(current["options"]) == 10
    for role, labels in (("correct", "ABC"), ("M1", "DEF"), ("M3", "GHI")):
        options = [option for option in current["options"] if option["label"] in labels]
        assert [option["body"] for option in options] == EXPECTED_CHOICES[role]
        assert all(option["is_correct"] == (role == "correct") for option in options)
        assert all(option["misconception_type"] == (None if role == "correct" else role) for option in options)
    assert current["options"][-1] == previous["options"][-1]
    assert current["options"][-1]["body"] == "わからない。"


def test_missing_v7_does_not_fall_back_to_an_older_bank(tmp_path, monkeypatch):
    try:
        with monkeypatch.context() as patch:
            patch.setattr(content_loader, "LEARNING_V7_CONTENT_PATH", tmp_path / "missing.yml")
            load_learning_content.cache_clear()
            with pytest.raises(FileNotFoundError):
                load_learning_content(content_version=7)
    finally:
        load_learning_content.cache_clear()


def test_easy_mode_cannot_load_standard_v7():
    with pytest.raises(ValueError, match="version"):
        load_learning_content("easy", 7)
