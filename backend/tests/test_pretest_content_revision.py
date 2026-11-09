from collections import Counter
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import yaml
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID, can_resume
from app.db import session as db_session
from app.core.question_sets import ASSESSMENT_BANK_VERSIONS, HISTORICAL_ASSESSMENT_BANK_VERSIONS, STANDARD, assessment_construct_key, historical_assessment_bank_versions_for
from app.models import Attempt, Base, Participant, Question, QuestionOption, Term
from app.seed.seed_questions import _upsert_question, seed_database
from app.services.experiment import (
    _displayed_options,
    _test_result_question,
    latest_test_results,
)
from app.services.split_assessment import learning_spec as split_learning_spec, split_bank, split_specs, uses_split


LLM_FINE_TUNING_DISTRACTOR = "改訂後の取扱説明書の内容をもとにAIを追加訓練し、そのAIが学習した内容から回答する方法を、利用者から質問があるたびに説明書の該当箇所を検索して参照する方法と同じ仕組みとして扱う。"
LLM_MANUAL_RETRIEVAL_CORRECT = "利用者から製品の操作方法を質問されたら、対象製品の最新の取扱説明書から関連する操作手順や注意点を検索する。見つけた箇所を質問文と一緒にシステムがAIへ渡し、説明書に基づいた回答を作成させる仕組みを実装する。"
LLM_GENERALIZATION_DISTRACTOR = "担当者が確認した質問と回答の事例を使ってAIを追加訓練し、訓練に使った質問に「結論・操作手順・注意点」の順で答えられれば、初めて受ける質問にも同じ形式で答えられると判断し、未使用の質問での評価は行わない。"
LLM_PROMPT_DATABASE_DISTRACTOR = "取扱説明書の本文をあらかじめAIへのプロンプトに含め、その中から質問に合う情報を選んで回答させる方法を、外部の文書データベースから必要な情報を検索して取り出す方法と同じ仕組みとして扱う。"
LLM_PROMPT_FORMAT_CORRECT = "製品について質問を受けたとき、回答を「結論・操作手順・注意点」の順に示すよう、AIへの指示文（プロンプト）に項目と順序を明記する。その指示文を利用者の質問と一緒に毎回AIへ渡し、指定した構成で案内を作成させる。"
MULTI_AGENT_SCENARIO = """大学が、学生からの本の貸出に関する質問に回答するAIシステムを開発している。

例えば、学生が「統計学の入門書を借りたい。借りられる本はありますか？」と質問した場合、図書館にどのような本があるかだけでなく、その本が現在貸出中かどうかや、館外への貸出が認められているかも確認する必要がある。

開発担当者は、図書館にある本や貸出状況を調べる担当と、本の種類や図書館の貸出規則を確認する担当に仕事を分け、それぞれが調べた情報をもとに学生へ適切な案内を行うAIシステムを作りたいと考えている。"""
MULTI_AGENT_SPLIT_ROLES_CORRECT = "図書館にある本を調べるAIと、貸出条件を確認するAIを別々のエージェントとして設ける。蔵書担当には本の有無や貸出状況の調査を任せ、貸出条件担当には本の種類や貸出規則を確認させるなど、それぞれに異なる仕事を設定する。"
MULTI_AGENT_LOAN_CANDIDATES_CORRECT = "蔵書担当の調査結果を利用条件の確認担当へ渡し、貸出可能な候補を絞り込ませる。"
MULTI_AGENT_DUPLICATE_WORK_DISTRACTOR = "蔵書担当のAIが「その本があるか」を調べ、貸出条件担当のAIが「館外へ貸し出せるか」を調べると、調査内容が異なるため案内を作れないと考え、両方のAIに本の有無と貸出条件を同じように調べさせる。"
MULTI_AGENT_SINGLE_AI_DISTRACTOR = "図書館の案内AIに「本が図書館にあるかを調べる役」と「本を借りられるかを確認する役」の2つの役割を指示し、1つのAIが両方の仕事を行う構成を、2つのAIエージェントが役割分担する仕組みと同じものとして扱う。"
MULTI_AGENT_TOOL_DISTRACTOR = "蔵書担当のAIが、本の一覧や貸出状況を返す検索ツールを使い、そのツールも貸出に関する情報を調べているので、利用条件を確認する別のAIエージェントとして数える。"
MEMORY_SCENARIO = """利用者の食事に関する相談に応じて、献立を提案する健康相談AIを開発している。

ある利用者は、以前の相談で「辛い料理は避けたい」と伝えていたが、その後「最近は少し辛い料理も食べられるようになったので、これからは献立に入れてほしい」と希望を変更した。また、AIが提案した献立について「量が多かったので、次からは少なめにしてほしい」と感想を伝えた。

開発担当者は、この利用者が別の日に新しく相談した際にも、以前に伝えた希望やその後の変更、提案への感想を踏まえて献立を提案できるAIシステムを作りたいと考えている。"""
MEMORY_STALE_PREFERENCE_DISTRACTOR = "利用者が「辛い料理は避けたい」から「少し辛い料理も食べたい」に希望を変更した場合、新しい希望を別の記録として追加し、以前の希望もそのまま残す。次回の相談では、保存した記録を検索すれば、どちらが現在の希望なのかを確認しなくても、AIが新しい希望を使うと考える。"
MEMORY_FINE_TUNING_DISTRACTOR = "利用者が「辛い料理は避けたい」と伝えたとき、その希望に合った献立を回答する質問と回答の例を使ってAIを追加訓練する。この追加訓練を、利用者ごとの希望を保存し、次の相談で取り出す記憶機能と同じ仕組みとして扱う。"
MEMORY_FULL_CONVERSATION_DISTRACTOR = "利用者が「辛い料理は避けたい」と伝えた会話を利用者ごとに全文保存し、次の相談ではAIが保存された会話から必要な希望を自動的に見つけて使えると考え、過去の記録を検索してAIに渡す仕組みは設けない。"
MEMORY_NO_UPDATE_DISTRACTOR = "利用者が「辛い料理は避けたい」という希望を「少し辛い料理も食べたい」に変更した場合、新しい希望をAIに伝えて献立を作らせれば、以前に保存した希望の記録も新しい内容に書き換わると考え、記録を更新する処理は設けない。"
MEMORY_UPDATE_CORRECT = "利用者が以前の「辛い料理は避けたい」を「少し辛い料理も食べたい」に変更したら、利用者別の記録に残る古い希望を確認し、新しい希望が現在の条件となるように更新する。次回の相談では、更新した記録を参照して新しい希望に沿う献立を提案させる。"
MEMORY_SHARED_INSTRUCTION_DISTRACTOR = "利用者が「辛い料理は避けたい」から「少し辛い料理も食べたい」に希望を変更した際、AIがすべての利用者に共通して使う指示文を「少し辛い料理も提案する」に変更し、この設定を、利用者ごとの希望を記憶する仕組みとして利用する。"
V4_EXPECTED = yaml.safe_load((Path(__file__).parent / "fixtures" / "split_assessment_v4_expected.yml").read_text(encoding="utf-8"))
V5_ADDITIONS = yaml.safe_load((Path(__file__).parent / "fixtures" / "split_assessment_v5_added_choices_expected.yml").read_text(encoding="utf-8"))
V5_PR260_WORDING = yaml.safe_load((Path(__file__).parent / "fixtures" / "split_assessment_v5_pr260_wording_expected.yml").read_text(encoding="utf-8"))
V5_CURRENT_WORDING = yaml.safe_load((Path(__file__).parent / "fixtures" / "split_assessment_v5_current_wording_expected.yml").read_text(encoding="utf-8"))
V5_POST_PR264_WORDING = yaml.safe_load((Path(__file__).parent / "fixtures" / "split_assessment_v5_post_pr264_wording_expected.yml").read_text(encoding="utf-8"))


def test_v2_changes_only_the_requested_pretest_content_and_preserves_v1():
    old = split_bank("split-actions-v1")
    revised = split_bank("split-actions-v2")
    expected = deepcopy(old)

    llm = expected["pretest_v1"]["llm_knowledge"]
    llm["questions"][0]["choices"]["M3"]["body"] = LLM_FINE_TUNING_DISTRACTOR
    llm["questions"][1]["choices"]["M1"]["body"] = LLM_GENERALIZATION_DISTRACTOR
    llm["questions"][1]["choices"]["M3"]["body"] = LLM_PROMPT_DATABASE_DISTRACTOR

    multi_agent = expected["pretest_v1"]["multi_agent"]
    multi_agent["scenario"] = MULTI_AGENT_SCENARIO
    multi_agent["questions"][0]["choices"]["M1"]["body"] = MULTI_AGENT_DUPLICATE_WORK_DISTRACTOR
    multi_agent["questions"][0]["choices"]["M3"]["body"] = MULTI_AGENT_SINGLE_AI_DISTRACTOR
    multi_agent["questions"][1]["choices"]["M3"]["body"] = MULTI_AGENT_TOOL_DISTRACTOR

    memory = expected["pretest_v1"]["memory_process"]
    memory["scenario"] = MEMORY_SCENARIO
    memory["questions"][0]["choices"]["M3"]["body"] = MEMORY_STALE_PREFERENCE_DISTRACTOR

    assert revised == expected
    assert split_bank("split-actions-v1") == old
    assert revised["retest_v1"] == old["retest_v1"]
    assert revised["retest_v2"] == old["retest_v2"]
    for slug in ("multi_agent", "memory_process"):
        specs = split_specs(slug, "pretest_v1", bank_version="split-actions-v2")
        assert len(specs) == 2
        assert specs[0]["body"].split("\n\n設問", 1)[0] == specs[1]["body"].split("\n\n設問", 1)[0]


def test_v3_is_preserved_as_the_spec_33_bank():
    v1 = split_bank("split-actions-v1")
    v2 = split_bank("split-actions-v2")
    revised = split_bank("split-actions-v3")
    expected = deepcopy(v2)
    llm = expected["pretest_v1"]["llm_knowledge"]["questions"]
    llm[0]["choices"]["correct"]["body"] = LLM_MANUAL_RETRIEVAL_CORRECT
    llm[1]["choices"]["correct"]["body"] = LLM_PROMPT_FORMAT_CORRECT
    multi_agent = expected["pretest_v1"]["multi_agent"]["questions"]
    multi_agent[0]["choices"]["correct"]["body"] = MULTI_AGENT_SPLIT_ROLES_CORRECT
    assert multi_agent[1]["choices"]["correct"]["body"] == MULTI_AGENT_LOAN_CANDIDATES_CORRECT
    memory = expected["pretest_v1"]["memory_process"]["questions"]
    memory[0]["choices"]["M1"]["body"] = MEMORY_FULL_CONVERSATION_DISTRACTOR
    memory[0]["choices"]["M3"]["body"] = MEMORY_FINE_TUNING_DISTRACTOR
    memory[1]["choices"]["correct"]["body"] = MEMORY_UPDATE_CORRECT
    memory[1]["choices"]["M1"]["body"] = MEMORY_NO_UPDATE_DISTRACTOR
    memory[1]["choices"]["M3"]["body"] = MEMORY_SHARED_INSTRUCTION_DISTRACTOR

    assert revised == expected
    v3_path = Path(__file__).parents[1] / "app/seed/content/standard/split_assessment_v3.yml"
    assert yaml.safe_load(v3_path.read_text(encoding="utf-8"))["status"] == "active_standard_split_v3"
    assert split_bank("split-actions-v1") == v1
    assert split_bank("split-actions-v2") == v2
    assert revised["retest_v1"] == v2["retest_v1"]
    assert revised["retest_v2"] == v2["retest_v2"]
    for role, label in (("M1", "B"),):
        assert revised["pretest_v1"]["memory_process"]["questions"][0]["choices"][role]["label"] == label
    assert revised["pretest_v1"]["memory_process"]["questions"][1]["choices"]["M3"]["label"] == "C"


def test_v4_matches_all_comparison_text_and_preserves_question_structure():
    v1 = split_bank("split-actions-v1")
    v2 = split_bank("split-actions-v2")
    v3 = split_bank("split-actions-v3")
    revised = split_bank("split-actions-v4")
    expected = deepcopy(v3)
    assert sum(len(questions) * 3 for terms in V4_EXPECTED.values() for questions in terms.values()) == 81

    for round_key, terms in V4_EXPECTED.items():
        for term_slug, questions in terms.items():
            for number, choices in questions.items():
                question = next(q for q in expected[round_key][term_slug]["questions"] if q["number"] == number)
                for role, body in choices.items():
                    question["choices"][role]["body"] = body

    assert revised == expected
    v4_path = Path(__file__).parents[1] / "app/seed/content/standard/split_assessment_v4.yml"
    assert yaml.safe_load(v4_path.read_text(encoding="utf-8"))["status"] == "active_standard_split_v4"
    assert split_bank("split-actions-v1") == v1
    assert split_bank("split-actions-v2") == v2
    assert split_bank("split-actions-v3") == v3
    for round_key in ("pretest_v1", "retest_v1", "retest_v2"):
        for term_slug in ("llm_knowledge", "multi_agent", "memory_process"):
            specs = split_specs(term_slug, round_key, bank_version="split-actions-v4")
            assert [spec["question_number"] for spec in specs] == [1, 2]


def test_v5_matches_pr260_wording_and_pr264_review_fixes_while_preserving_v4_structure():
    v4 = split_bank("split-actions-v4")
    revised = split_bank("split-actions-v5")
    expected = deepcopy(v4)
    assert V5_ADDITIONS["source_bank"] == "split-actions-v4"
    assert V5_PR260_WORDING["source_pr"] == 260
    assert V5_POST_PR264_WORDING["source_pr"] == 264
    assert V5_POST_PR264_WORDING["source_commit"] == "0acca907bd3f1362bdc88693a72d577e6449438f"
    assert sum(len(questions) for terms in V5_ADDITIONS["added_choices"].values() for questions in terms.values()) == 27
    overrides = V5_PR260_WORDING["choice_overrides"]
    changed_labels = Counter(
        label for terms in overrides.values() for questions in terms.values()
        for choices in questions.values() for label in choices
    )
    assert changed_labels == {"A": 3, "B": 27, "D": 26}

    for round_key, terms in V5_ADDITIONS["added_choices"].items():
        for term_slug, questions in terms.items():
            expected_questions = {q["number"]: q for q in expected[round_key][term_slug]["questions"]}
            for addition in questions:
                number = addition["number"]
                question = expected_questions[number]
                previous = question["choices"]
                question["choices"] = [
                    {"role": "correct", "label": "A", "body": previous["correct"]["body"]},
                    {"role": "M1", "label": "B", "body": previous["M1"]["body"]},
                    {"role": "M1", "label": "C", "body": addition["M1"]},
                    {"role": "M3", "label": "D", "body": previous["M3"]["body"]},
                    {"role": "M3", "label": "E", "body": addition["M3"]},
                    {"role": "unknown", "label": "F", "body": previous["unknown"]["body"]},
                ]
                for label, body in overrides.get(round_key, {}).get(term_slug, {}).get(number, {}).items():
                    next(choice for choice in question["choices"] if choice["label"] == label)["body"] = body

    assert V5_CURRENT_WORDING["source_commit"] == "7eb4bcd22018aef9a2b2fdaf36728e89807ea969"
    assert V5_POST_PR264_WORDING["source_pr"] == 264
    assert V5_POST_PR264_WORDING["source_commit"] == "0acca907bd3f1362bdc88693a72d577e6449438f"
    assert V5_CURRENT_WORDING["choice_overrides"] == V5_POST_PR264_WORDING["choice_overrides"]
    for round_key, terms in V5_POST_PR264_WORDING["choice_overrides"].items():
        for term_slug, questions in terms.items():
            expected_questions = {q["number"]: q for q in expected[round_key][term_slug]["questions"]}
            for number, choices in questions.items():
                question = expected_questions[number]
                for label, body in choices.items():
                    next(choice for choice in question["choices"] if choice["label"] == label)["body"] = body

    # 理由は内部メタデータとし、設問本文・選択肢・役割・シナリオ・設問3は変更しない。
    assert sum(
        1
        for round_key in ("pretest_v1", "retest_v1", "retest_v2")
        for term_slug in ("llm_knowledge", "multi_agent", "memory_process")
        for question in revised[round_key][term_slug]["questions"]
        if question["number"] == 1
        for choice in question["choices"]
        if choice.get("rationale")
    ) == 54
    content_only = deepcopy(revised)
    for round_key in ("pretest_v1", "retest_v1", "retest_v2"):
        for term_slug in ("llm_knowledge", "multi_agent", "memory_process"):
            question = next(q for q in content_only[round_key][term_slug]["questions"] if q["number"] == 1)
            for choice in question["choices"]:
                choice.pop("rationale", None)
    assert content_only == expected
    assert revised["pretest_v1"]["llm_knowledge"]["questions"][2]["number"] == 3
    assert all(len(question["choices"]) == 6 for terms in revised.values() for section in terms.values() for question in section["questions"])
    for round_key in ("pretest_v1", "retest_v1", "retest_v2"):
        for term_slug in ("llm_knowledge", "multi_agent", "memory_process"):
            assert [item["question_number"] for item in split_specs(term_slug, round_key, bank_version="split-actions-v5")] == [1, 2]


def test_q1_rationales_are_seeded_as_internal_metadata_not_participant_options(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'q1-rationales.db'}")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            seed_database(db)
            participant = Participant(
                display_code="Q1-RATIONALE-TEST",
                group_condition="control",
                current_step="pretest",
                experiment_spec_version=CURRENT_EXPERIMENT_SPEC_VERSION,
                protocol_id=CURRENT_PROTOCOL_ID,
                test_content_mode="application",
                learning_content_version=15,
                option_order_mode="debug_fixed",
            )
            db.add(participant)
            db.flush()

            for round_key in ("pretest_v1", "retest_v1", "retest_v2"):
                phase = "pretest" if round_key == "pretest_v1" else "retest"
                for term_slug in ("llm_knowledge", "multi_agent", "memory_process"):
                    term = db.query(Term).filter_by(slug=term_slug).one()
                    question = db.query(Question).filter_by(
                        term_id=term.id,
                        phase=phase,
                        construct_key=assessment_construct_key(term.slug, phase),
                        variant_key=f"{round_key}_q1",
                    ).one()
                    stored = {
                        option.option_label: option.rationale
                        for option in db.query(QuestionOption).filter_by(question_id=question.id).all()
                    }
                    assert set(stored) == set("ABCDEF")
                    assert all(isinstance(value, str) and value.strip() for value in stored.values())

                    participant_options = _displayed_options(db, participant, question)
                    assert len(participant_options) == 6
                    assert all("rationale" not in option for option in participant_options)
    finally:
        engine.dispose()


def test_init_db_adds_rationale_column_to_existing_question_options_table(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'question-option-schema.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE question_options DROP COLUMN rationale"))
    monkeypatch.setattr(db_session, "engine", engine)

    db_session.init_db()

    columns = {column["name"] for column in inspect(engine).get_columns("question_options")}
    assert "rationale" in columns
    engine.dispose()


def test_split_actions_v6_bank_loads_and_validates_question_1_only():
    bank = split_bank("split-actions-v6")
    assert set(bank) == {"pretest_v1", "retest_v1", "retest_v2"}
    for round_key, terms in bank.items():
        assert set(terms) == {"llm_knowledge", "multi_agent", "memory_process"}
        for term_slug, section in terms.items():
            assert [question["number"] for question in section["questions"]] == [1]
            choices = section["questions"][0]["choices"]
            entries = list(choices.values()) if isinstance(choices, dict) else choices
            assert [choice["label"] for choice in entries] == list("ABCDEF")
            assert Counter(choice["role"] for choice in entries) == Counter({
                "correct": 1, "M1": 2, "M3": 2, "unknown": 1,
            })
            assert [item["question_number"] for item in split_specs(
                term_slug, round_key, bank_version="split-actions-v6",
            )] == [1]


def test_historical_assessment_bank_mapping_accepts_dict_and_falls_back_to_version():
    protocol_id = "experiment-plan-2026-11-07-split-actions-v6-q1-only-v1"
    assert historical_assessment_bank_versions_for({
        "experiment_spec_version": 41,
        "protocol_id": protocol_id,
    }) == {STANDARD: "split-actions-v6"}
    assert historical_assessment_bank_versions_for({
        "experiment_spec_version": 41,
    }) == {STANDARD: "split-actions-v5"}
    assert historical_assessment_bank_versions_for({"protocol_id": protocol_id}) is None
    assert historical_assessment_bank_versions_for(SimpleNamespace()) is None
    assert historical_assessment_bank_versions_for(None) is None


def test_spec_41_v6_protocol_restores_question_and_latest_result(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'spec41-v6-history.db'}")
    Base.metadata.create_all(engine)
    protocol_id = "experiment-plan-2026-11-07-split-actions-v6-q1-only-v1"
    try:
        with Session(engine) as db:
            seed_database(db)
            participant = Participant(
                display_code="PRETEST-V41-V6",
                group_condition="control",
                current_step="finish",
                experiment_spec_version=41,
                protocol_id=protocol_id,
                learning_content_version=15,
                option_order_mode="debug_fixed",
                first_question_only=True,
            )
            db.add(participant)
            db.flush()

            term = db.query(Term).filter_by(slug="memory_process").one()
            spec = split_specs(term.slug, "pretest_v1", bank_version="split-actions-v6")[0]
            question = _upsert_question(
                db,
                term,
                phase="pretest",
                question_type="split_single",
                body=spec["body"],
                expected_answer="A",
                construct_key=assessment_construct_key(
                    term.slug, "pretest", bank_version="split-actions-v6",
                ),
                variant_key=spec["variant_key"],
                options=spec["options"],
            )
            question.is_active = False
            db.flush()

            restored = _test_result_question(db, participant, term, "test", "pretest")
            assert restored is not None
            assert restored.id == question.id
            assert restored.body == spec["body"]
            assert restored.construct_key.endswith("split-actions-v6")

            selected = db.query(QuestionOption).filter_by(
                question_id=question.id, option_label="F",
            ).one()
            attempt = Attempt(
                participant_id=participant.id,
                term_id=term.id,
                question_id=question.id,
                phase="pretest",
                test_round="test",
                selected_option_ids=[selected.id],
                is_correct=False,
                question_body_snapshot=question.body,
                option_order_snapshot=_displayed_options(db, participant, question),
            )
            db.add(attempt)
            db.flush()

            results = latest_test_results(db, participant.id)["results"]
            assert len(results) == 1
            assert results[0]["question_id"] == question.id
            assert results[0]["question_body"] == spec["body"]
            assert results[0]["selected_options"] == [{
                "label": "F",
                "body": selected.body,
            }]
    finally:
        engine.dispose()


def test_spec_43_keeps_mode_banks_and_preserves_previous_read_only_snapshots(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'pretest-revision.db'}")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            seed_database(db)
            assert CURRENT_EXPERIMENT_SPEC_VERSION == 43
            assert CURRENT_PROTOCOL_ID == "experiment-plan-2026-11-08-basic-understanding-question-mode-v1"
            assert ASSESSMENT_BANK_VERSIONS[STANDARD] == "split-actions-v5"
            assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[31][STANDARD] == "split-actions-v1"
            assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[32][STANDARD] == "split-actions-v2"
            assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[33][STANDARD] == "split-actions-v3"
            assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[34][STANDARD] == "split-actions-v4"
            assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[35][STANDARD] == "split-actions-v5"
            assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[36][STANDARD] == "split-actions-v5"
            assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[37][STANDARD] == "split-actions-v5"
            assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[38][STANDARD] == "split-actions-v5"
            assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[39][STANDARD] == "split-actions-v5"
            assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[40][STANDARD] == "split-actions-v5"
            assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[41][STANDARD] == "split-actions-v5"
            assert historical_assessment_bank_versions_for(SimpleNamespace(
                experiment_spec_version=41,
                protocol_id="experiment-plan-2026-11-07-split-actions-v6-q1-only-v1",
            )) == {STANDARD: "split-actions-v6"}

            term = db.query(Term).filter_by(slug="memory_process").one()
            active = db.query(Question).filter_by(
                term_id=term.id,
                phase="pretest",
                construct_key=assessment_construct_key(term.slug, "pretest"),
                variant_key="pretest_v1_q1",
            ).one()
            assert active.is_active
            assert "split-actions-v5" in active.construct_key
            active_m1 = db.query(QuestionOption).filter_by(question_id=active.id, option_label="B").one()
            assert active_m1.body == V5_POST_PR264_WORDING["choice_overrides"]["pretest_v1"]["memory_process"][1]["B"]
            active_added_m1 = db.query(QuestionOption).filter_by(question_id=active.id, option_label="C").one()
            assert active_added_m1.misconception_type == "M1"

            v4_spec = split_specs(term.slug, "pretest_v1", bank_version="split-actions-v4")[0]
            v4_question = _upsert_question(
                db,
                term,
                phase="pretest",
                question_type="split_single",
                body=v4_spec["body"],
                expected_answer="A",
                construct_key=assessment_construct_key(term.slug, "pretest", bank_version="split-actions-v4"),
                variant_key=v4_spec["variant_key"],
                options=v4_spec["options"],
            )
            v4_question.is_active = False
            v4_options = db.query(QuestionOption).filter_by(question_id=v4_question.id).order_by(QuestionOption.option_label).all()
            v4_snapshot = (v4_question.body, [(o.option_label, o.body) for o in v4_options])

            v2_spec = split_specs(term.slug, "pretest_v1", bank_version="split-actions-v2")[0]
            v2_question = _upsert_question(
                db,
                term,
                phase="pretest",
                question_type="split_single",
                body=v2_spec["body"],
                expected_answer="A",
                construct_key=assessment_construct_key(term.slug, "pretest", bank_version="split-actions-v2"),
                variant_key=v2_spec["variant_key"],
                options=v2_spec["options"],
            )
            v2_question.is_active = False
            v2_options = db.query(QuestionOption).filter_by(question_id=v2_question.id).order_by(QuestionOption.option_label).all()
            v2_snapshot = (v2_question.body, [(o.option_label, o.body) for o in v2_options])

            v3_spec = split_specs(term.slug, "pretest_v1", bank_version="split-actions-v3")[0]
            v3_question = _upsert_question(
                db,
                term,
                phase="pretest",
                question_type="split_single",
                body=v3_spec["body"],
                expected_answer="A",
                construct_key=assessment_construct_key(term.slug, "pretest", bank_version="split-actions-v3"),
                variant_key=v3_spec["variant_key"],
                options=v3_spec["options"],
            )
            v3_question.is_active = False
            v3_options = db.query(QuestionOption).filter_by(question_id=v3_question.id).order_by(QuestionOption.option_label).all()
            v3_snapshot = (v3_question.body, [(o.option_label, o.body) for o in v3_options])

            spec32_participant = Participant(
                display_code="PRETEST-V32",
                group_condition="control",
                current_step="finish",
                experiment_spec_version=32,
                protocol_id="experiment-plan-2026-11-01-pretest-content-revision-v1",

                learning_content_version=15,
            )
            spec33_participant = Participant(
                display_code="PRETEST-V33",
                group_condition="control",
                current_step="learning",
                experiment_spec_version=33,
                protocol_id="experiment-plan-2026-11-01-pretest-content-revision-v2",

                learning_content_version=15,
            )
            spec34_participant = Participant(
                display_code="PRETEST-V34",
                group_condition="control",
                current_step="learning",
                experiment_spec_version=34,
                protocol_id="experiment-plan-2026-11-01-split-choice-wording-v1",

                learning_content_version=15,
            )
            spec35_participant = Participant(
                display_code="PRETEST-V35",
                group_condition="control",
                current_step="learning",
                experiment_spec_version=35,
                protocol_id="experiment-plan-2026-11-03-split-added-choices-v1",

                learning_content_version=15,
            )
            spec36_rag_participant = Participant(
                display_code="PRETEST-V36-RAG",
                group_condition="control",
                current_step="learning",
                experiment_spec_version=36,
                protocol_id="experiment-plan-2026-11-04-rag-glossary-v1",

                learning_content_version=15,
            )
            spec36_presurvey_participant = Participant(
                display_code="PRETEST-V36-PRESURVEY",
                group_condition="control",
                current_step="learning",
                experiment_spec_version=36,
                protocol_id="experiment-plan-2026-11-04-presurvey-baseline-v1",

                learning_content_version=15,
            )
            spec37_participant = Participant(
                display_code="PRETEST-V37",
                group_condition="control",
                current_step="learning",
                experiment_spec_version=37,
                protocol_id="experiment-plan-2026-11-04-presurvey-baseline-v2",

                learning_content_version=15,
            )
            spec38_participant = Participant(
                display_code="PRETEST-V38",
                group_condition="control",
                current_step="learning",
                experiment_spec_version=38,
                protocol_id="experiment-plan-2026-11-05-presurvey-baseline-v2-rag-glossary-v1",

                learning_content_version=15,
            )
            spec39_participant = Participant(
                display_code="PRETEST-V39",
                group_condition="control",
                current_step="learning",
                experiment_spec_version=39,
                protocol_id="experiment-plan-2026-11-06-learning-glossary-integrated-default-v1",
                learning_content_version=15,
            )
            spec40_fixed_settings_participant = Participant(
                display_code="PRETEST-V40-FIXED",
                group_condition="control",
                current_step="learning",
                experiment_spec_version=40,
                protocol_id="experiment-plan-2026-11-07-fixed-admin-settings-v1",
                learning_content_version=15,
                first_question_only=True,
                show_pretest_results=False,
                show_retest_results=False,
                show_question_reviews=True,
            )
            spec40_shared_prompt_participant = Participant(
                display_code="PRETEST-V40-PROMPT",
                group_condition="control",
                current_step="learning",
                experiment_spec_version=40,
                protocol_id="experiment-plan-2026-11-07-control-shared-prompt-v1",
                learning_content_version=15,
                first_question_only=False,
                learning_material_glossary_mode="integrated_material",
            )
            db.add_all([
                spec32_participant,
                spec33_participant,
                spec34_participant,
                spec35_participant,
                spec36_rag_participant,
                spec36_presurvey_participant,
                spec37_participant,
                spec38_participant,
                spec39_participant,
                spec40_fixed_settings_participant,
                spec40_shared_prompt_participant,
            ])
            db.flush()
            v2_selected = next(option for option in v2_options if option.option_label == "B")
            v2_attempt = Attempt(
                participant_id=spec32_participant.id,
                term_id=term.id,
                question_id=v2_question.id,
                phase="pretest",
                test_round="test",
                selected_option_ids=[v2_selected.id],
                is_correct=False,
                misconception_type="M1",
                question_body_snapshot=v2_question.body,
                option_order_snapshot=_displayed_options(db, spec32_participant, v2_question),
            )
            v3_selected = next(option for option in v3_options if option.option_label == "B")
            v3_attempt = Attempt(
                participant_id=spec33_participant.id,
                term_id=term.id,
                question_id=v3_question.id,
                phase="pretest",
                test_round="test",
                selected_option_ids=[v3_selected.id],
                is_correct=False,
                misconception_type="M1",
                question_body_snapshot=v3_question.body,
                option_order_snapshot=_displayed_options(db, spec33_participant, v3_question),
            )
            v3_attempt_options = deepcopy(v3_attempt.option_order_snapshot)
            v4_selected = next(option for option in v4_options if option.option_label == "B")
            v4_attempt = Attempt(
                participant_id=spec34_participant.id,
                term_id=term.id,
                question_id=v4_question.id,
                phase="pretest",
                test_round="test",
                selected_option_ids=[v4_selected.id],
                is_correct=False,
                misconception_type="M1",
                question_body_snapshot=v4_question.body,
                option_order_snapshot=_displayed_options(db, spec34_participant, v4_question),
            )
            v5_selected = next(option for option in db.query(QuestionOption).filter_by(question_id=active.id).all() if option.option_label == "C")
            def make_v5_attempt(participant):
                return Attempt(
                    participant_id=participant.id,
                    term_id=term.id,
                    question_id=active.id,
                    phase="pretest",
                    test_round="test",
                    selected_option_ids=[v5_selected.id],
                    is_correct=False,
                    misconception_type="M1",
                    question_body_snapshot=active.body,
                    option_order_snapshot=_displayed_options(db, participant, active),
                )

            v5_attempt = make_v5_attempt(spec35_participant)
            v5_legacy_attempts = [
                make_v5_attempt(spec36_rag_participant),
                make_v5_attempt(spec36_presurvey_participant),
                make_v5_attempt(spec37_participant),
            ]
            v5_current_attempt = Attempt(
                participant_id=spec38_participant.id,
                term_id=term.id,
                question_id=active.id,
                phase="pretest",
                test_round="test",
                selected_option_ids=[v5_selected.id],
                is_correct=False,
                misconception_type="M1",
                question_body_snapshot=active.body,
                option_order_snapshot=_displayed_options(db, spec38_participant, active),
            )
            v5_spec39_attempt = make_v5_attempt(spec39_participant)
            v5_spec40_legacy_attempts = [
                make_v5_attempt(spec40_fixed_settings_participant),
                make_v5_attempt(spec40_shared_prompt_participant),
            ]
            db.add_all([v2_attempt, v3_attempt, v4_attempt, v5_attempt, *v5_legacy_attempts, v5_current_attempt, v5_spec39_attempt, *v5_spec40_legacy_attempts])
            db.commit()

            assert not can_resume(spec33_participant)
            assert not can_resume(spec34_participant)
            assert not can_resume(spec35_participant)
            assert uses_split(spec35_participant)
            assert not can_resume(spec36_rag_participant)
            assert not can_resume(spec36_presurvey_participant)
            assert not can_resume(spec37_participant)
            assert not can_resume(spec38_participant)
            assert not can_resume(spec39_participant)
            assert not can_resume(spec40_fixed_settings_participant)
            assert not can_resume(spec40_shared_prompt_participant)
            assert uses_split(spec36_rag_participant)
            assert uses_split(spec36_presurvey_participant)
            assert uses_split(spec37_participant)
            assert uses_split(spec38_participant)
            assert uses_split(spec40_fixed_settings_participant)
            assert uses_split(spec40_shared_prompt_participant)
            assert not can_resume(spec32_participant)
            assert assessment_construct_key(
                term.slug, "pretest",
                bank_version=HISTORICAL_ASSESSMENT_BANK_VERSIONS[32][STANDARD],
            ) == v2_question.construct_key
            assert assessment_construct_key(
                term.slug, "pretest",
                bank_version=HISTORICAL_ASSESSMENT_BANK_VERSIONS[33][STANDARD],
            ) == v3_question.construct_key
            assert assessment_construct_key(
                term.slug, "pretest",
                bank_version=HISTORICAL_ASSESSMENT_BANK_VERSIONS[34][STANDARD],
            ) == v4_question.construct_key
            assert assessment_construct_key(
                term.slug, "pretest",
                bank_version=HISTORICAL_ASSESSMENT_BANK_VERSIONS[35][STANDARD],
            ) == active.construct_key
            assert assessment_construct_key(term.slug, "pretest") == active.construct_key
            assert latest_test_results(db, spec32_participant.id)["results"][0]["question_body"] == v2_snapshot[0]
            assert latest_test_results(db, spec33_participant.id)["results"][0]["question_body"] == v3_snapshot[0]
            assert latest_test_results(db, spec34_participant.id)["results"][0]["question_body"] == v4_attempt.question_body_snapshot
            assert latest_test_results(db, spec35_participant.id)["results"][0]["question_body"] == v5_attempt.question_body_snapshot
            for participant in (spec36_rag_participant, spec36_presurvey_participant, spec37_participant):
                assert latest_test_results(db, participant.id)["results"][0]["question_body"] == v5_attempt.question_body_snapshot
            assert latest_test_results(db, spec38_participant.id)["results"][0]["question_body"] == v5_current_attempt.question_body_snapshot
            assert latest_test_results(db, spec39_participant.id)["results"][0]["question_body"] == v5_spec39_attempt.question_body_snapshot
            for participant, attempt in zip(
                (spec40_fixed_settings_participant, spec40_shared_prompt_participant),
                v5_spec40_legacy_attempts,
            ):
                assert latest_test_results(db, participant.id)["results"][0]["question_body"] == attempt.question_body_snapshot

            saved_body_v4 = v4_attempt.question_body_snapshot
            saved_options_v4 = deepcopy(v4_attempt.option_order_snapshot)
            saved_body_v5 = v5_current_attempt.question_body_snapshot
            saved_options_v5 = deepcopy(v5_current_attempt.option_order_snapshot)
            active.body = "live bank changed after the response"
            active_m1.body = "live option changed after the response"
            db.flush()
            confirmation = split_learning_spec(db, spec34_participant, term)
            assert confirmation["questions"][0]["body"] == saved_body_v4
            assert confirmation["questions"][0]["options"] == saved_options_v4
            confirmation_v5 = split_learning_spec(db, spec38_participant, term)
            assert len(confirmation_v5["questions"][0]["options"]) == 6
            assert confirmation_v5["questions"][0]["body"] == saved_body_v5
            assert confirmation_v5["questions"][0]["options"] == saved_options_v5
            confirmation_v5_spec39 = split_learning_spec(db, spec39_participant, term)
            assert confirmation_v5_spec39["questions"][0]["body"] == saved_body_v5
            assert confirmation_v5_spec39["questions"][0]["options"] == v5_spec39_attempt.option_order_snapshot

            seed_database(db)
            db.refresh(v2_question)
            db.refresh(v3_question)
            db.refresh(v4_question)
            db.refresh(v2_attempt)
            db.refresh(v3_attempt)
            db.refresh(v4_attempt)
            db.refresh(v5_attempt)
            for attempt in v5_legacy_attempts:
                db.refresh(attempt)
            for attempt in v5_spec40_legacy_attempts:
                db.refresh(attempt)
            db.refresh(v5_current_attempt)
            db.refresh(v5_spec39_attempt)
            db.refresh(active)
            db.refresh(active_m1)
            db.refresh(active_added_m1)
            assert not v2_question.is_active
            assert not v3_question.is_active
            assert not v4_question.is_active
            restored_options = db.query(QuestionOption).filter_by(question_id=v2_question.id).order_by(QuestionOption.option_label).all()
            assert (v2_question.body, [(o.option_label, o.body) for o in restored_options]) == v2_snapshot
            restored_v3_options = db.query(QuestionOption).filter_by(question_id=v3_question.id).order_by(QuestionOption.option_label).all()
            assert (v3_question.body, [(o.option_label, o.body) for o in restored_v3_options]) == v3_snapshot
            assert v2_attempt.question_body_snapshot == v2_snapshot[0]
            assert v3_attempt.question_body_snapshot == v3_snapshot[0]
            assert v3_attempt.option_order_snapshot == v3_attempt_options
            assert v4_attempt.question_body_snapshot == saved_body_v4
            assert v4_attempt.option_order_snapshot == saved_options_v4
            assert v5_attempt.question_body_snapshot == saved_body_v5
            assert v5_attempt.option_order_snapshot == saved_options_v5
            assert v5_current_attempt.question_body_snapshot == saved_body_v5
            assert v5_current_attempt.option_order_snapshot == saved_options_v5
            assert v5_spec39_attempt.question_body_snapshot == saved_body_v5
            assert v5_spec39_attempt.option_order_snapshot == v5_current_attempt.option_order_snapshot
            for attempt in v5_spec40_legacy_attempts:
                assert attempt.question_body_snapshot == saved_body_v5
                assert attempt.option_order_snapshot == v5_current_attempt.option_order_snapshot
            assert active.is_active and active.body == saved_body_v5
            assert v4_question.body == v4_snapshot[0]
            assert active_m1.body == V5_POST_PR264_WORDING["choice_overrides"]["pretest_v1"]["memory_process"][1]["B"]
            assert [(o.option_label, o.body) for o in v4_options] == v4_snapshot[1]
            assert active_added_m1.body == V5_ADDITIONS["added_choices"]["pretest_v1"]["memory_process"][0]["M1"]
            assert latest_test_results(db, spec32_participant.id)["results"][0]["question_body"] == v2_snapshot[0]
            assert latest_test_results(db, spec33_participant.id)["results"][0]["question_body"] == v3_snapshot[0]
            assert split_learning_spec(db, spec34_participant, term)["questions"][0]["body"] == saved_body_v4
            assert latest_test_results(db, spec35_participant.id)["results"][0]["question_body"] == v5_attempt.question_body_snapshot
            for participant in (spec36_rag_participant, spec36_presurvey_participant, spec37_participant):
                assert latest_test_results(db, participant.id)["results"][0]["question_body"] == v5_attempt.question_body_snapshot
            assert split_learning_spec(db, spec38_participant, term)["questions"][0]["body"] == v5_current_attempt.question_body_snapshot
            assert split_learning_spec(db, spec39_participant, term)["questions"][0]["body"] == v5_spec39_attempt.question_body_snapshot
    finally:
        engine.dispose()
