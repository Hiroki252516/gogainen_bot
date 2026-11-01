from copy import deepcopy

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID
from app.core.question_sets import ASSESSMENT_BANK_VERSIONS, HISTORICAL_ASSESSMENT_BANK_VERSIONS, STANDARD, assessment_construct_key
from app.models import Attempt, Base, Participant, Question, QuestionOption, Term
from app.seed.seed_questions import _upsert_question, seed_database
from app.services.experiment import _displayed_options, latest_test_results
from app.services.split_assessment import learning_spec as split_learning_spec, split_bank, split_specs
from app.core.experiment_spec import can_resume


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
MEMORY_FULL_CONVERSATION_DISTRACTOR = "利用者が「辛い料理は避けたい」と伝えた会話を利用者ごとに全文保存し、次の相談ではAIが保存された会話から必要な希望を自動的に見つけて使えると考え、過去の記録を検索してAIに渡す仕組みは設けない。"
MEMORY_NO_UPDATE_DISTRACTOR = "利用者が「辛い料理は避けたい」という希望を「少し辛い料理も食べたい」に変更した場合、新しい希望をAIに伝えて献立を作らせれば、以前に保存した希望の記録も新しい内容に書き換わると考え、記録を更新する処理は設けない。"
MEMORY_SHARED_INSTRUCTION_DISTRACTOR = "利用者が「辛い料理は避けたい」から「少し辛い料理も食べたい」に希望を変更した際、AIがすべての利用者に共通して使う指示文を「少し辛い料理も提案する」に変更し、この設定を、利用者ごとの希望を記憶する仕組みとして利用する。"


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


def test_v3_changes_only_the_requested_memory_distractors_and_preserves_v1_v2():
    v1 = split_bank("split-actions-v1")
    v2 = split_bank("split-actions-v2")
    revised = split_bank("split-actions-v3")
    expected = deepcopy(v2)
    memory = expected["pretest_v1"]["memory_process"]["questions"]
    memory[0]["choices"]["M1"]["body"] = MEMORY_FULL_CONVERSATION_DISTRACTOR
    memory[1]["choices"]["M1"]["body"] = MEMORY_NO_UPDATE_DISTRACTOR
    memory[1]["choices"]["M3"]["body"] = MEMORY_SHARED_INSTRUCTION_DISTRACTOR

    assert revised == expected
    assert split_bank("split-actions-v1") == v1
    assert split_bank("split-actions-v2") == v2
    assert revised["retest_v1"] == v2["retest_v1"]
    assert revised["retest_v2"] == v2["retest_v2"]
    for role, label in (("M1", "B"),):
        assert revised["pretest_v1"]["memory_process"]["questions"][0]["choices"][role]["label"] == label
    assert revised["pretest_v1"]["memory_process"]["questions"][1]["choices"]["M3"]["label"] == "C"


def test_spec_33_seeds_v3_and_restores_spec_32_from_v2_without_changing_snapshots(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'pretest-revision.db'}")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            seed_database(db)
            assert CURRENT_EXPERIMENT_SPEC_VERSION == 33
            assert CURRENT_PROTOCOL_ID == "experiment-plan-2026-11-01-pretest-content-revision-v2"
            assert ASSESSMENT_BANK_VERSIONS[STANDARD] == "split-actions-v3"
            assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[31][STANDARD] == "split-actions-v1"
            assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[32][STANDARD] == "split-actions-v2"

            term = db.query(Term).filter_by(slug="memory_process").one()
            active = db.query(Question).filter_by(
                term_id=term.id,
                phase="pretest",
                construct_key=assessment_construct_key(term.slug, "pretest", STANDARD),
                variant_key="pretest_v1_q1",
            ).one()
            assert active.is_active
            assert "split-actions-v3" in active.construct_key
            active_m1 = db.query(QuestionOption).filter_by(question_id=active.id, option_label="B").one()
            assert active_m1.body == MEMORY_FULL_CONVERSATION_DISTRACTOR

            v2_spec = split_specs(term.slug, "pretest_v1", bank_version="split-actions-v2")[0]
            v2_question = _upsert_question(
                db,
                term,
                phase="pretest",
                question_type="split_single",
                body=v2_spec["body"],
                expected_answer="A",
                construct_key=assessment_construct_key(term.slug, "pretest", STANDARD, bank_version="split-actions-v2"),
                variant_key=v2_spec["variant_key"],
                options=v2_spec["options"],
            )
            v2_question.is_active = False
            v2_options = db.query(QuestionOption).filter_by(question_id=v2_question.id).order_by(QuestionOption.option_label).all()
            v2_snapshot = (v2_question.body, [(o.option_label, o.body) for o in v2_options])

            spec32_participant = Participant(
                display_code="PRETEST-V32",
                group_condition="control",
                current_step="finish",
                experiment_spec_version=32,
                protocol_id="experiment-plan-2026-11-01-pretest-content-revision-v1",
                question_set_mode=STANDARD,
                learning_content_version=15,
            )
            spec33_participant = Participant(
                display_code="PRETEST-V33",
                group_condition="control",
                current_step="learning",
                experiment_spec_version=33,
                protocol_id=CURRENT_PROTOCOL_ID,
                question_set_mode=STANDARD,
                learning_content_version=15,
            )
            db.add_all([spec32_participant, spec33_participant])
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
            v3_options = db.query(QuestionOption).filter_by(question_id=active.id).order_by(QuestionOption.option_label).all()
            v3_selected = next(option for option in v3_options if option.option_label == "B")
            v3_attempt = Attempt(
                participant_id=spec33_participant.id,
                term_id=term.id,
                question_id=active.id,
                phase="pretest",
                test_round="test",
                selected_option_ids=[v3_selected.id],
                is_correct=False,
                misconception_type="M1",
                question_body_snapshot=active.body,
                option_order_snapshot=_displayed_options(db, spec33_participant, active),
            )
            db.add_all([v2_attempt, v3_attempt])
            db.commit()

            assert can_resume(spec33_participant)
            assert not can_resume(spec32_participant)
            assert assessment_construct_key(
                term.slug, "pretest", STANDARD,
                bank_version=HISTORICAL_ASSESSMENT_BANK_VERSIONS[32][STANDARD],
            ) == v2_question.construct_key
            assert assessment_construct_key(term.slug, "pretest", STANDARD) == active.construct_key
            assert latest_test_results(db, spec32_participant.id)["results"][0]["question_body"] == v2_snapshot[0]
            assert latest_test_results(db, spec33_participant.id)["results"][0]["question_body"] == v3_attempt.question_body_snapshot

            saved_body = v3_attempt.question_body_snapshot
            saved_options = deepcopy(v3_attempt.option_order_snapshot)
            active.body = "live bank changed after the response"
            active_m1.body = "live option changed after the response"
            db.flush()
            confirmation = split_learning_spec(db, spec33_participant, term)
            assert confirmation["questions"][0]["body"] == saved_body
            assert confirmation["questions"][0]["options"] == saved_options

            seed_database(db)
            db.refresh(v2_question)
            db.refresh(v2_attempt)
            db.refresh(v3_attempt)
            db.refresh(active)
            db.refresh(active_m1)
            assert not v2_question.is_active
            restored_options = db.query(QuestionOption).filter_by(question_id=v2_question.id).order_by(QuestionOption.option_label).all()
            assert (v2_question.body, [(o.option_label, o.body) for o in restored_options]) == v2_snapshot
            assert v2_attempt.question_body_snapshot == v2_snapshot[0]
            assert v3_attempt.question_body_snapshot == saved_body
            assert v3_attempt.option_order_snapshot == saved_options
            assert active.is_active and active.body == saved_body
            assert active_m1.body == MEMORY_FULL_CONVERSATION_DISTRACTOR
            assert latest_test_results(db, spec32_participant.id)["results"][0]["question_body"] == v2_snapshot[0]
            assert split_learning_spec(db, spec33_participant, term)["questions"][0]["body"] == saved_body
    finally:
        engine.dispose()
