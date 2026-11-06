from copy import deepcopy
import hashlib

import pytest
import yaml
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.question_sets import assessment_construct_key
from app.db import session as database
from app.models import Attempt, Base, EvaluationSummary, Participant, Question, QuestionOption, Term
from app.seed.content_loader import (
    SCENARIO_ACTIONS_V1_CONTENT_PATH, SCENARIO_ACTIONS_V2_CONTENT_PATH, SCENARIO_ACTIONS_V3_CONTENT_PATH, SCENARIO_ACTIONS_V4_CONTENT_PATH, SCENARIO_ACTIONS_V5_CONTENT_PATH,
    _assessment_options, _validate_content, _validate_learning_content,
    assessment_question_spec, load_content, load_learning_content,
)
from app.seed.seed_questions import _upsert_question, seed_database
from app.services import experiment


REPLACEMENTS = {
    ("llm_knowledge", "correct", 2): "担当者が確認した質問と回答の見本を使ってAIを追加訓練し、「結論・操作手順・注意点」の順で答えるように調整する。",
    ("llm_knowledge", "M3", 2): "取扱説明書を保存・検索する仕組みとして、説明書の本文をプロンプトに登録し、プロンプトそのものを文書データベースとして利用するように設計する。",
    ("multi_agent", "M1", 0): "蔵書を調べる担当と利用条件を確認する担当にそれぞれ指示を出し、調査結果を受け渡したり統合したりする仕組みを設けずに、担当同士が自動的に連携して案内を作るように設計する。",
    ("memory_process", "correct", 0): "利用者が会話で伝えた食事の好みや避けたい食材から、次回以降の提案に必要な情報を選んで利用者ごとに保存し、次の相談時に関連する情報を検索して、AIがその情報を参考に食事を提案できる仕組みを実装する。",
    ("memory_process", "M1", 0): "利用者の食事の希望を次回も覚えておくには、必要な情報だけを保存する方法では記憶できないため、過去の会話をすべて全文のまま保存する仕組みを実装する。",
    ("memory_process", "M3", 2): "前回の会話をプロンプトに貼り付けるだけで、会話終了後も情報を保存・検索・更新する記憶機能を実現できる。",
}


def archived_content(version=1):
    path = {1: SCENARIO_ACTIONS_V1_CONTENT_PATH, 2: SCENARIO_ACTIONS_V2_CONTENT_PATH, 3: SCENARIO_ACTIONS_V3_CONTENT_PATH, 4: SCENARIO_ACTIONS_V4_CONTENT_PATH, 5: SCENARIO_ACTIONS_V5_CONTENT_PATH}[version]
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_v2_changed_only_six_standard_choices_and_four_targets():
    before = archived_content()
    expected = deepcopy(before)
    for (slug, role, index), text in REPLACEMENTS.items():
        term = next(term for term in expected["terms"] if term["slug"] == slug)
        term["questions"]["pretest"][0]["choices"][role][index] = text
        label = "ABCDEFGHI"[("correct", "M1", "M3").index(role) * 3 + index]
        option = next(o for o in assessment_question_spec(slug, "pretest")["options"] if o["label"] == label)
        assert option["body"] == text
        assert option["is_correct"] == (role == "correct")
        assert option["misconception_type"] == (None if role == "correct" else role)
    current = archived_content(2)
    assert current["assessment_bank_version"] == "scenario-actions-v2"
    current["assessment_bank_version"] = before["assessment_bank_version"]
    changed_targets = {(slug, label) for slug in before["teaching_targets"] for label in before["teaching_targets"][slug]
                       if before["teaching_targets"][slug][label] != current["teaching_targets"][slug][label]}
    assert changed_targets == {("llm_knowledge", "I"), ("multi_agent", "D"), ("memory_process", "D"), ("memory_process", "I")}
    current["teaching_targets"] = before["teaching_targets"]
    assert current == expected
    targets = load_content()["teaching_targets"]
    assert "本文をプロンプトへ含めて参照させることはできる" in targets["llm_knowledge"]["I"]["corrected_claim"]
    assert "全文保存という方法自体を誤りとするものではない" in targets["memory_process"]["D"]["mechanism_explanation"]
    assert "保存済み履歴を入力へ戻すこと自体は記憶利用の一部" in targets["memory_process"]["I"]["mechanism_explanation"]


def test_v3_changes_only_llm_pretest_a_and_b_and_keeps_both_correct():
    assert hashlib.sha256(SCENARIO_ACTIONS_V2_CONTENT_PATH.read_bytes()).hexdigest() == "57d27c53e1e1b15cfe4eb1bd1a2cb2817f95fa22cc092ceabd26e8f3dad9569b"
    expected = archived_content(2)
    assert expected["assessment_bank_version"] == "scenario-actions-v2"
    choices = expected["terms"][0]["questions"]["pretest"][0]["choices"]["correct"]
    choices[:2] = [
        "利用者の質問に応じて最新の取扱説明書を検索し、該当箇所を質問と一緒にAIへ渡して回答を作らせる仕組みを実装する。",
        "利用者からの質問に回答するとき、「結論・操作手順・注意点」の順に説明するよう、AIに指示するプロンプトを設定する。",
    ]
    expected["assessment_bank_version"] = "scenario-actions-v3"
    assert archived_content(3) == expected
    options = assessment_question_spec("llm_knowledge", "pretest")["options"]
    for label, text in zip("AB", choices[:2], strict=True):
        option = next(o for o in options if o["label"] == label)
        assert option["body"] == text
        assert option["is_correct"] is True
        assert option["misconception_type"] is None


def test_v4_changes_only_llm_pretest_f_and_keeps_m1():
    expected = archived_content(3)
    text = "回答を「結論・操作手順・注意点」の順にする指示をプロンプトに加えることで、モデルの重みも更新されると考え、質問と回答の事例を使った追加訓練は行わない。"
    expected["terms"][0]["questions"]["pretest"][0]["choices"]["M1"][2] = text
    expected["assessment_bank_version"] = "scenario-actions-v4"
    assert archived_content(4) == expected
    option = next(o for o in assessment_question_spec("llm_knowledge", "pretest")["options"] if o["label"] == "F")
    assert option["body"] == text
    assert option["is_correct"] is False
    assert option["misconception_type"] == "M1"


@pytest.mark.parametrize("bank", ["assessment", "learning"])
@pytest.mark.parametrize("change", ["lengths", "empty", "duplicate", "count", "role"])
def test_option_lengths_are_unrestricted_but_structure_is_validated(bank, change):
    assessment = deepcopy(load_content())
    if bank == "assessment":
        content = assessment
        variant = content["terms"][0]["questions"]["pretest"][0]
        validate = lambda: _validate_content(content)
    else:
        content = deepcopy(load_learning_content())
        variant = content["terms"]["llm_knowledge"]["variants"][0]
        validate = lambda: _validate_learning_content(content, assessment)
    choices = variant["choices"]
    if change == "lengths":
        choices["correct"][0] = "短"
        choices["M1"][0] = "長い選択肢の表現" * 100
    elif change == "empty":
        choices["M1"][0] = "  "
    elif change == "duplicate":
        choices["M3"][0] = choices["correct"][0]
    elif change == "count":
        choices["correct"].pop()
    else:
        choices["M2"] = choices.pop("M1")
    if change == "lengths":
        validate()
    else:
        with pytest.raises(ValueError):
            validate()


def seed_historical_banks(db, version=1):
    old = archived_content(version)
    for index, item in enumerate(old["terms"], start=1):
        term = Term(slug=item["slug"], label=item["label"], description=item["description"], display_order=index)
        db.add(term)
        db.flush()
        term_item = next(t for t in old["terms"] if t["slug"] == term.slug)
        for phase in ("pretest", "retest", "final_test"):
            variants = term_item["questions"]["retest"][:1] if phase == "final_test" else term_item["questions"][phase]
            for variant in variants:
                _upsert_question(
                    db, term, phase=phase, question_type={"pretest": "multi_select", "retest": "retest_multi_select", "final_test": "final_multi_select"}[phase],
                    body=f"{variant['scenario']}\n\n{variant['task']}", expected_answer="A、B、Cをすべて選択し、それ以外を選ばない。",
                    construct_key=assessment_construct_key(term.slug, phase, bank_version=old["assessment_bank_version"]),
                    variant_key=variant["variant_key"],
                    options=[(o["label"], o["body"], o["is_correct"], o["misconception_type"]) for o in _assessment_options(variant)],
                )
    db.commit()


@pytest.mark.parametrize("spec_version", [6, 7, 8, 9, 10, 18, 19])
def test_seed_keeps_old_ids_and_snapshotless_reviews_on_historical_bank(tmp_path, monkeypatch, spec_version):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    monkeypatch.setattr(database, "engine", engine)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        historical_version = {9: 2, 10: 3, 18: 4, 19: 5}.get(spec_version, 1)
        seed_historical_banks(db, version=historical_version)
        questions_before = {q.id: (q.body, q.expected_answer, q.construct_key, q.variant_key) for q in db.query(Question)}
        options_before = {o.id: (o.question_id, o.body, o.is_correct, o.misconception_type) for o in db.query(QuestionOption)}
        protocol = {6: "experiment-plan-2026-10-24-two-posttests-v1", 7: "experiment-plan-2026-10-24-easy-version-v1", 8: "experiment-plan-2026-10-25-glossary-v1", 9: "experiment-plan-2026-10-25-pretest-improvement-v1", 10: "experiment-plan-2026-10-25-pretest-wording-v1", 18: "experiment-plan-2026-10-26-memory-round2-v1", 19: "experiment-plan-2026-10-26-llm-confirmation-retest-v1"}[spec_version]
        participant = Participant(display_code="OLD", group_condition="proposed", current_step="learning_targets",
                                  experiment_spec_version=spec_version, protocol_id=protocol,
                                  learning_content_version=12 if spec_version == 19 else 11 if spec_version == 18 else 3, retest_cycles_completed=1)
        db.add(participant)
        db.flush()
        term = db.query(Term).filter_by(slug="llm_knowledge").one()
        bank = f"scenario-actions-v{historical_version}"
        final = db.query(Question).filter_by(term_id=term.id, phase="final_test", construct_key=assessment_construct_key(term.slug, "final_test", bank_version=bank)).one()
        db.add(Attempt(participant_id=participant.id, term_id=term.id, question_id=final.id, phase="final_test", test_round="retest_1", is_correct=False))
        pretest = db.query(Question).filter_by(term_id=term.id, phase="pretest", construct_key=assessment_construct_key(term.slug, "pretest", bank_version=bank)).one()
        selected_label = {9: "A", 10: "F"}.get(spec_version, "I")
        selected = db.query(QuestionOption).filter_by(question_id=pretest.id, option_label=selected_label).one()
        saved = Attempt(participant_id=participant.id, term_id=term.id, question_id=pretest.id, phase="pretest", test_round="test",
                        selected_option_ids=[selected.id], is_correct=False, misconception_type="M3", question_body_snapshot=None, option_order_snapshot=None)
        db.add(saved)
        db.add(EvaluationSummary(participant_id=participant.id, group_condition="proposed", pretest_score=0.125))
        db.commit()
        records_before = {model: deepcopy(db.execute(select(model.__table__)).mappings().all()) for model in (Participant, Attempt, EvaluationSummary)}
        seed_database(db)
        seed_database(db)
        database.init_db()
        database.init_db()
        for model, records in records_before.items():
            assert db.execute(select(model.__table__)).mappings().all() == records
        question_count_after_first_seed = db.query(Question).count()
        option_count_after_first_seed = db.query(QuestionOption).count()
        for qid, expected in questions_before.items():
            q = db.get(Question, qid)
            assert (q.body, q.expected_answer, q.construct_key, q.variant_key) == expected
        seed_database(db)
        assert db.query(Question).count() == question_count_after_first_seed
        assert db.query(QuestionOption).count() == option_count_after_first_seed
        assert db.query(Question).filter_by(is_active=True).count() == 18
        for oid, expected in options_before.items():
            o = db.get(QuestionOption, oid)
            assert (o.question_id, o.body, o.is_correct, o.misconception_type) == expected
        for t in db.query(Term):
            for round_name, phase, key in (("test", "pretest", "pretest_v1"), ("retest_1", "final_test", "retest_v1"), ("retest_2", "retest", "retest_v2")):
                q = experiment._test_result_question(db, participant, t, round_name, phase)
                assert q.id in questions_before
                assert q.construct_key.endswith(bank)
                assert q.variant_key == key
        assert experiment._public_selected_options(db, saved) == [{"label": selected_label, "body": selected.body}]
        if spec_version in {9, 10}:
            assert selected.body != assessment_question_spec("llm_knowledge", "pretest")["options"][ord(selected_label) - ord("A")]["body"]
        review = experiment.latest_test_results(db, participant.id)
        assert review["results"][0]["question_body"] == questions_before[final.id][0]
        for row in review["results"][1:]:
            t = db.query(Term).filter_by(slug=row["term_slug"]).one()
            q = experiment._test_result_question(db, participant, t, "retest_1", "final_test")
            assert row["question_body"] == questions_before[q.id][0]
        assert db.get(Attempt, saved.id).option_order_snapshot is None
        assert participant.experiment_spec_version == spec_version
        assert db.query(EvaluationSummary).one().pretest_score == 0.125
    engine.dispose()
