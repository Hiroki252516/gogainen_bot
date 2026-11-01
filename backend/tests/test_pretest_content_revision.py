from copy import deepcopy

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID
from app.core.question_sets import ASSESSMENT_BANK_VERSIONS, HISTORICAL_ASSESSMENT_BANK_VERSIONS, STANDARD, assessment_construct_key
from app.models import Attempt, Base, Participant, Question, QuestionOption, Term
from app.seed.seed_questions import _upsert_question, seed_database
from app.services.experiment import latest_test_results
from app.services.split_assessment import split_bank, split_specs


LLM_FINE_TUNING_DISTRACTOR = "改訂後の取扱説明書の内容をもとにAIを追加訓練し、そのAIが学習した内容から回答する方法を、利用者から質問があるたびに説明書の該当箇所を検索して参照する方法と同じ仕組みとして扱う。"
LLM_GENERALIZATION_DISTRACTOR = "担当者が確認した質問と回答の事例を使ってAIを追加訓練し、訓練に使った質問に「結論・操作手順・注意点」の順で答えられれば、初めて受ける質問にも同じ形式で答えられると判断し、未使用の質問での評価は行わない。"
LLM_PROMPT_DATABASE_DISTRACTOR = "取扱説明書の本文をあらかじめAIへのプロンプトに含め、その中から質問に合う情報を選んで回答させる方法を、外部の文書データベースから必要な情報を検索して取り出す方法と同じ仕組みとして扱う。"
MULTI_AGENT_SCENARIO = """大学が、学生からの本の貸出に関する質問に回答するAIシステムを開発している。

例えば、学生が「統計学の入門書を借りたい。借りられる本はありますか？」と質問した場合、図書館にどのような本があるかだけでなく、その本が現在貸出中かどうかや、館外への貸出が認められているかも確認する必要がある。

開発担当者は、図書館にある本や貸出状況を調べる担当と、本の種類や図書館の貸出規則を確認する担当に仕事を分け、それぞれが調べた情報をもとに学生へ適切な案内を行うAIシステムを作りたいと考えている。"""
MULTI_AGENT_DUPLICATE_WORK_DISTRACTOR = "蔵書担当のAIが「その本があるか」を調べ、貸出条件担当のAIが「館外へ貸し出せるか」を調べると、調査内容が異なるため案内を作れないと考え、両方のAIに本の有無と貸出条件を同じように調べさせる。"
MULTI_AGENT_SINGLE_AI_DISTRACTOR = "図書館の案内AIに「本が図書館にあるかを調べる役」と「本を借りられるかを確認する役」の2つの役割を指示し、1つのAIが両方の仕事を行う構成を、2つのAIエージェントが役割分担する仕組みと同じものとして扱う。"
MULTI_AGENT_TOOL_DISTRACTOR = "蔵書担当のAIが、本の一覧や貸出状況を返す検索ツールを使い、そのツールも貸出に関する情報を調べているので、利用条件を確認する別のAIエージェントとして数える。"
MEMORY_SCENARIO = """利用者の食事に関する相談に応じて、献立を提案する健康相談AIを開発している。

ある利用者は、以前の相談で「辛い料理は避けたい」と伝えていたが、その後「最近は少し辛い料理も食べられるようになったので、これからは献立に入れてほしい」と希望を変更した。また、AIが提案した献立について「量が多かったので、次からは少なめにしてほしい」と感想を伝えた。

開発担当者は、この利用者が別の日に新しく相談した際にも、以前に伝えた希望やその後の変更、提案への感想を踏まえて献立を提案できるAIシステムを作りたいと考えている。"""
MEMORY_STALE_PREFERENCE_DISTRACTOR = "利用者が「辛い料理は避けたい」から「少し辛い料理も食べたい」に希望を変更した場合、新しい希望を別の記録として追加し、以前の希望もそのまま残す。次回の相談では、保存した記録を検索すれば、どちらが現在の希望なのかを確認しなくても、AIが新しい希望を使うと考える。"


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


def test_spec_32_seeds_new_bank_and_spec_31_results_resolve_old_bank(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'pretest-revision.db'}")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            seed_database(db)
            assert CURRENT_EXPERIMENT_SPEC_VERSION == 32
            assert CURRENT_PROTOCOL_ID == "experiment-plan-2026-11-01-pretest-content-revision-v1"
            assert ASSESSMENT_BANK_VERSIONS[STANDARD] == "split-actions-v2"
            assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[31][STANDARD] == "split-actions-v1"

            term = db.query(Term).filter_by(slug="llm_knowledge").one()
            active = db.query(Question).filter_by(
                term_id=term.id,
                phase="pretest",
                construct_key=assessment_construct_key(term.slug, "pretest", STANDARD),
                variant_key="pretest_v1_q1",
            ).one()
            assert active.is_active
            assert "split-actions-v2" in active.construct_key
            active_m3 = db.query(QuestionOption).filter_by(question_id=active.id, option_label="C").one()
            assert "改訂後の取扱説明書" in active_m3.body

            old_spec = split_specs(term.slug, "pretest_v1", bank_version="split-actions-v1")[0]
            old_question = _upsert_question(
                db,
                term,
                phase="pretest",
                question_type="split_single",
                body=old_spec["body"],
                expected_answer="A",
                construct_key=assessment_construct_key(term.slug, "pretest", STANDARD, bank_version="split-actions-v1"),
                variant_key=old_spec["variant_key"],
                options=old_spec["options"],
            )
            old_question.is_active = False
            old_options = db.query(QuestionOption).filter_by(question_id=old_question.id).order_by(QuestionOption.option_label).all()
            old_snapshot = (old_question.body, [(o.option_label, o.body) for o in old_options])
            old_m3_body = next(option.body for option in old_options if option.option_label == "C")

            old_participant = Participant(
                display_code="PRETEST-V31",
                group_condition="control",
                current_step="finish",
                experiment_spec_version=31,
                protocol_id="experiment-plan-2026-10-31-glossary-definition-paraphrase-v1",
                question_set_mode=STANDARD,
                learning_content_version=15,
            )
            current_participant = Participant(
                display_code="PRETEST-V32",
                group_condition="control",
                current_step="finish",
                experiment_spec_version=32,
                protocol_id=CURRENT_PROTOCOL_ID,
                question_set_mode=STANDARD,
                learning_content_version=15,
            )
            db.add_all([old_participant, current_participant])
            db.flush()
            attempt = Attempt(
                participant_id=old_participant.id,
                term_id=term.id,
                question_id=old_question.id,
                phase="pretest",
                test_round="test",
                selected_option_ids=[old_options[0].id],
                is_correct=False,
                misconception_type="M1",
                question_body_snapshot=old_question.body,
                option_order_snapshot=[{"option_id": old_options[0].id, "label": "A", "body": old_options[0].body}],
            )
            db.add(attempt)
            db.commit()

            old_results = latest_test_results(db, old_participant.id)
            assert old_results["results"][0]["question_body"] == old_question.body
            assert old_results["results"][0]["question_id"] == old_question.id
            assert active.id != old_question.id
            assert active_m3.body != old_m3_body

            seed_database(db)
            db.refresh(old_question)
            db.refresh(attempt)
            assert not old_question.is_active
            restored_options = db.query(QuestionOption).filter_by(question_id=old_question.id).order_by(QuestionOption.option_label).all()
            assert (old_question.body, [(o.option_label, o.body) for o in restored_options]) == old_snapshot
            assert attempt.question_body_snapshot == old_snapshot[0]
            assert attempt.option_order_snapshot == [{"option_id": old_options[0].id, "label": "A", "body": old_snapshot[1][0][1]}]
            assert latest_test_results(db, old_participant.id)["results"][0]["question_body"] == old_snapshot[0]
    finally:
        engine.dispose()
