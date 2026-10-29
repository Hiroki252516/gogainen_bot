from copy import deepcopy
import hashlib

import pytest
import yaml
from admin_client import AuthenticatedTestClient as TestClient
from sqlalchemy.orm import Session
from split_api_support import assert_learning_flow, assert_retest_flow

from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID
from app.core.question_sets import ASSESSMENT_BANK_VERSIONS, LEARNING_CONTENT_VERSIONS
from app.db.session import SessionLocal
from app.main import app
from app.models import Participant, TutorSession, TutorTurn
from app.seed import content_loader
from app.seed.content_loader import assessment_question_spec, learning_question_spec, load_content, load_learning_content
from app.services.interaction_history import build_interaction_history
from app.services.prefetch import wait_for_prefetch_tasks


EXPECTED = {
    "learning_round_v1": {
        "variant_key": "learning_round_v1",
        "scenario_type": "application",
        "scenario": "大学が、学生からの履修登録に関する質問に回答するAIを開発している。今年度は履修規程が改訂され、履修登録の変更手続きや提出期限が以前と異なっている。学生への回答は「必要な手続き・提出期限・注意点」の順にそろえたいが、質問によって説明の仕方にばらつきがある。また、担当職員が内容を確認した過去の質問と回答の例も用意しており、回答の改善に活用したい。",
        "task": "これらの目的を実現する開発担当者の対応として、適切なものを3つ選びなさい。",
        "choices": {
            "correct": [
                "学生から履修登録の変更期限を尋ねられたとき、改訂後の履修規程から質問に関係する箇所を検索し、見つけた内容をAIに示して、その情報を参考に案内を作成させる。",
                "学生への回答を「必要な手続き・提出期限・注意点」の順にそろえるため、AIへ渡す指示文（プロンプト）に説明の順序を指定し、問い合わせへの回答時にその指示を利用する。",
                "担当職員が確認した履修登録の質問と適切な回答の組を学習用データとしてまとめ、その例を使ってAIモデルを追加訓練し、回答の構成や表現を調整する。"
            ],
            "M1": [
                "改訂後の履修規程を開発時に一度AIへ入力すれば、その内容がモデルの重みに記憶されると考え、学生からの新しい問い合わせで規程を検索する仕組みは設けない。",
                "職員が確認した質問と回答の例を学生の問い合わせのたびにAIへ渡せば、回答を重ねるうちにモデルの重みも更新されると考え、別の追加訓練は行わない。",
                "「必要な手続き・提出期限・注意点」の順に説明する指示文をAIへ与えると、その順序がモデルの重みに定着すると考え、以後の問い合わせには同じ指示を与えずに回答させる。"
            ],
            "M3": [
                "職員が確認した質問と回答の例を文書検索の対象として登録し、似た質問が来たときに取り出せるようにする処理を、回答方法を覚えさせる追加訓練と同じ仕組みとして扱う。",
                "学生が履修変更の期限を質問したとき、改訂後の履修規程から該当する箇所を探す文書検索の仕組みの代わりに、ファインチューニングを検索機能として組み込む。",
                "改訂後の履修規程の本文をAIへの指示文（プロンプト）に書き込み、そのプロンプトそのものを、規程を継続的に保存したり必要な条文を検索したりする文書データベースとして扱う。"
            ]
        }
    },
    "learning_round_v2": {
        "variant_key": "learning_round_v2",
        "scenario_type": "prediction",
        "scenario": "大学が、学生に学内施設の利用方法を案内するAIを開発している。開発担当者は、同じAIモデルに「自習室の利用方法を教えて」という質問を与え、回答形式を変えて比較することにした。1回目は「手順と注意点を表でまとめて」と指示し、2回目は「同じ内容を一段落の文章で説明して」と指示する。どちらも同じAIモデルを使用し、回答形式の指示以外は変更せず、追加訓練も行っていない。",
        "task": "回答形式の指示を変えた場合に起こり得る変化と、モデルの学習との違いについて、適切な説明を3つ選びなさい。",
        "choices": {
            "correct": [
                "同じAIモデルでも、「表でまとめて」と指示すれば内容を表に整理し、「一段落で説明して」と指示すれば文章にまとめるなど、モデルの重みを変更せずに回答形式を変えられる。",
                "開発担当者は、学生への回答を表形式にしたい場合、AIに渡す指示文（プロンプト）で表の形式を指定できるため、モデルを追加訓練せずに回答の見せ方を調整できる。",
                "表形式の回答方法をモデルの重みに反映させたい場合は、適切な回答例などを学習用データとして用意し、そのデータを使ってモデルを追加訓練する工程が必要になる。"
            ],
            "M1": [
                "「表でまとめて」という指示で表形式の回答が生成された場合、AIがその回答方法を新たに学習したと考え、出力形式が変わったことをモデルの重みも更新された証拠として扱う。",
                "一度「表でまとめて」と指示して表形式の回答が得られれば、その形式はモデル自身に記憶されると考え、別の日の新しい会話でも同じ指示を与えずに表形式で回答させる。",
                "AIが自習室の利用方法について新しい説明文を生成すると、その文章は回答を作成した時点でモデルの重みに保存されると考え、次回の質問ではその内容を学習済みの情報として利用する。"
            ],
            "M3": [
                "「表でまとめて」というプロンプトの指示によって回答形式を変える操作を、表形式の回答例を学習用データにしてモデルを追加訓練する工程と同じ種類の仕組みとして扱う。",
                "表形式で回答するようモデルを追加訓練する工程を、質問に「表で答えて」という指示を書き加えるプロンプトの設定と同じ種類の操作として扱い、両者を区別せずに設計する。",
                "「表でまとめて」と指示したAIと「一段落で説明して」と指示したAIは、使っているモデルが同じでも回答形式が異なるため、それぞれ別の学習済みモデルとして扱う。"
            ]
        }
    },
    "retest_v1": {
        "variant_key": "retest_v1",
        "scenario": "企業が、社員からの「パスワードを忘れた」「社内Wi-Fiにつながらない」「パソコンの電源が入らない」といった問い合わせに対応するAIを開発している。このAIは、問い合わせを「アカウント」「ネットワーク」「機器」の3種類に分類し、分類結果と対応手順を決められた形式で案内する。最近、社内の対応手順書が改訂されたため、開発担当者は新しい手順を案内に反映したい。また、担当者が正しく分類した過去の問い合わせ事例を利用して、AIの分類精度も改善したいと考えている。",
        "task": "これらの目的を実現するための開発担当者の対応として、適切なものを3つ選びなさい。",
        "choices": {
            "correct": [
                "社員が「社内Wi-Fiにつながらない」と相談したら、改訂後の対応手順書から関係する箇所を検索し、見つけた情報をAIに示して、その内容を参考に案内を作成させる。",
                "問い合わせを「アカウント」「ネットワーク」「機器」のいずれかに分類し、分類名と対応手順を指定した順番で表示するよう、AIへ渡すプロンプトに指示を加える。",
                "担当者が「パスワードを忘れた→アカウント」などと確認した問い合わせ文と分類結果の組を学習用データにし、対応モデルを追加訓練して分類方法を調整する。"
            ],
            "M1": [
                "担当者が分類した過去の問い合わせ事例を開発時に一度AIへ渡しておけば、その判断基準がモデルの重みに記憶されると考え、その後は事例を提示せずに分類させる。",
                "参照用フォルダーに保存した対応手順書を最新版に差し替えると、それに合わせてAIの学習済みの重みも更新されると考え、回答時には文書を検索させない。",
                "問い合わせを3種類に分類するよう毎回同じ指示をAIへ送れば、分類を繰り返すうちにモデルの重みも調整されると考え、担当者が確認した事例を使う追加訓練は行わない。"
            ],
            "M3": [
                "担当者が分類した問い合わせ事例を文書検索用の索引に登録し、似た質問を探せるようにする処理を、モデルの分類方法を学習させる追加訓練と同じ仕組みとして扱う。",
                "改訂された対応手順書から、社員の問い合わせに必要な箇所を探すため、モデルを追加訓練するファインチューニングを文書検索の機能として組み込む。",
                "改訂後の対応手順書の本文をAIへの共通プロンプトに記載し、そのプロンプト自体を、手順書を継続的に保存し、必要な箇所を探す文書データベースとして扱う。"
            ]
        }
    },
    "retest_v2": {
        "variant_key": "retest_v2",
        "scenario": "企業が、会議の文字起こしをもとに議事録を作成するAIを開発している。\n\n議事録には、会議で決まった内容を「決定事項・担当者・期限」の3項目に整理して記載したい。また、会議で使われた社内の略称は、改訂される用語集に載っている正式表記に統一したいと考えている。\n\n現在は、AIが作成する議事録の文章構成や表現にばらつきがあるため、担当者が内容を確認した過去の文字起こしと完成済みの議事録も改善に活用したい。",
        "task": "これらの目的を実現する開発担当者の対応として、適切なものを3つ選びなさい。",
        "choices": {
            "correct": [
                "会議の文字起こしに社内の略称が出てきた場合は、最新の用語集からその正式表記を検索し、見つかった情報をAIに参照させて議事録を作成する仕組みを設ける。",
                "文字起こしから議事録を作る際、「決定事項・担当者・期限」の順に内容を整理するよう、AIに渡す指示文（プロンプト）に書式や説明の順番を指定する。",
                "担当者が内容を確認した文字起こしと完成した議事録の組を学習用データにまとめ、追加訓練に対応するモデルを使って、議事録の文章構成やまとめ方を調整する。"
            ],
            "M1": [
                "最新の用語集を開発時に一度AIに読ませておけば、そこにある正式表記がモデルの重みに保存されると考え、その後の会議では用語集を参照させずに議事録を作る。",
                "担当者が完成させた議事録を毎回プロンプトに見本として含めて回答させれば、使用するたびにモデルの重みも調整されると考え、別途の追加訓練は行わない。",
                "最初の会議で「決定事項・担当者・期限」の順に書くよう指示すると、その書式がモデルの重みに定着すると考え、次の独立した会話では同じ指示を与えずに議事録を作らせる。"
            ],
            "M3": [
                "過去の文字起こしと完成済みの議事録を検索対象に登録し、似た会議の事例を取り出して参照させる処理を、モデルに議事録の書き方を学習させる追加訓練と同じ種類の仕組みとして扱う。",
                "議事録に社内の略称が出てきたとき、ファインチューニングの仕組みにその語を渡せば最新の用語集から正式表記を検索できると考え、文書検索機能の代わりに組み込む。",
                "最新の用語集の本文をAIへの共通の指示文（プロンプト）に含め、そのプロンプト自体を、用語集を継続的に保存・管理し、必要な表記を検索する文書データベースとして扱う。"
            ]
        }
    }
}


def test_v12_and_assessment_v5_only_change_the_four_requested_questions():
    assert load_learning_content(content_version=12)["version"] == 12
    assert hashlib.sha256(content_loader.LEARNING_V11_CONTENT_PATH.read_bytes()).hexdigest() == "538638dd055c1e535c51b0beb43777b18337f8b6fa5583df5323259f07a1bb4a"
    assert hashlib.sha256(content_loader.SCENARIO_ACTIONS_V4_CONTENT_PATH.read_bytes()).hexdigest() == "57f89f9d9cbe2f8d7c019fa5f24f08998b7761e7c956fa11f3c22a58ca71d9d5"
    previous_learning = deepcopy(load_learning_content(content_version=11))
    previous_learning["version"] = 12
    previous_learning["terms"]["llm_knowledge"]["variants"][:2] = [EXPECTED["learning_round_v1"], EXPECTED["learning_round_v2"]]
    assert load_learning_content(content_version=12) == previous_learning
    previous_assessment = yaml.safe_load(content_loader.SCENARIO_ACTIONS_V4_CONTENT_PATH.read_text(encoding="utf-8"))
    previous_assessment["assessment_bank_version"] = "scenario-actions-v5"
    previous_assessment["terms"][0]["questions"]["retest"] = [EXPECTED["retest_v1"], EXPECTED["retest_v2"]]
    adopted = yaml.safe_load(content_loader.SCENARIO_ACTIONS_V5_CONTENT_PATH.read_text(encoding="utf-8"))
    assert adopted == previous_assessment


@pytest.mark.parametrize("key", list(EXPECTED))
@pytest.mark.parametrize("stage", ["enrichment", "conceptual_change"])
def test_exact_question_text_roles_and_paragraphs(key, stage):
    index = int(key[-1])
    if key.startswith("learning"):
        spec = learning_question_spec("llm_knowledge", stage, index, content_version=12)
    else:
        adopted = yaml.safe_load(content_loader.SCENARIO_ACTIONS_V5_CONTENT_PATH.read_text(encoding="utf-8"))
        term = next(term for term in adopted["terms"] if term["slug"] == "llm_knowledge")
        source = term["questions"]["retest"][index - 1]
        spec = {"body": source["scenario"] + "\n\n" + source["task"], "options": content_loader._assessment_options(source)}
    expected = EXPECTED[key]
    assert spec["body"] == expected["scenario"] + "\n\n" + expected["task"]
    assert len(spec["body"].split("\n\n")) == (4 if key == "retest_v2" else 2)
    assert "**" not in spec["body"] and "問題：" not in spec["body"]
    for role, labels in (("correct", "ABC"), ("M1", "DEF"), ("M3", "GHI")):
        selected = [option for option in spec["options"] if option["label"] in labels]
        assert [option["body"] for option in selected] == expected["choices"][role]
        assert all(option["is_correct"] == (role == "correct") for option in selected)
        assert all(option["misconception_type"] == (None if role == "correct" else role) for option in selected)
    assert {key: spec["options"][-1][key] for key in content_loader.UNKNOWN_OPTION} == content_loader.UNKNOWN_OPTION
    assert assessment_question_spec("llm_knowledge", "final_test")["body"] == assessment_question_spec("llm_knowledge", "retest", 1)["body"]


def test_missing_v12_and_wrong_mode_do_not_fall_back(tmp_path, monkeypatch):
    try:
        with monkeypatch.context() as patch:
            patch.setattr(content_loader, "LEARNING_V12_CONTENT_PATH", tmp_path / "missing.yml")
            load_learning_content.cache_clear()
            with pytest.raises(FileNotFoundError):
                load_learning_content(content_version=12)
    finally:
        load_learning_content.cache_clear()
    with pytest.raises(ValueError, match="version"):
        load_learning_content("easy", 12)


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def _selected(question, source, labels):
    bodies = {option["body"] for option in source["options"] if option["label"] in labels}
    return [option["option_id"] for option in question["options"] if option["body"] in bodies]


def _answer_test(client, pid, phase, labels, index=1):
    route = "final-test" if phase == "final_test" else phase
    questions = _ok(client.get(f"/api/experiment/{pid}/{route}"))["questions"]
    llm = next(question for question in questions if question["term_slug"] == "llm_knowledge")
    if phase != "pretest":
        expected = assessment_question_spec("llm_knowledge", phase, index)
        assert llm["body"] == expected["body"]
    for question in questions:
        assert all(set(option) == {"option_id", "label", "body", "exclusive"} for option in question["options"])
        source = assessment_question_spec(question["term_slug"], phase, index)
        selected = labels if question["term_slug"] == "llm_knowledge" else "ABC"
        _ok(client.post("/api/attempts", json={"participant_id": pid, "question_id": question["question_id"],
                                             "selected_option_ids": _selected(question, source, selected)}))
    return llm


@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
@pytest.mark.parametrize("initial", ["J", "DEF", "GHI"])
@pytest.mark.parametrize("labels,expected_type", [("ABC", None), ("DEF", "M1"), ("GHI", "M3"), ("ADH", "M3"), ("J", "unknown")])
def test_natural_two_learning_rounds_feedback_history_and_retests(group, layout, initial, labels, expected_type):
    assert_learning_flow("llm_knowledge", group, layout, initial, labels, expected_type, index=2)


@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
@pytest.mark.parametrize("final_labels", ["ABC", "GHI"])
def test_pretest_perfect_uses_revised_shared_final_test(group, layout, final_labels):
    assert_retest_flow("llm_knowledge", group, layout, "final_test", final_labels, None if final_labels == "ABC" else "M3")
