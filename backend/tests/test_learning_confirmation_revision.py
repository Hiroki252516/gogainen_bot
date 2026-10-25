from copy import deepcopy
import hashlib
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID
from app.db import session as database
from app.models import Base, Participant, Term, TutorSession, TutorTurn
from app.seed import content_loader
from app.seed.content_loader import learning_question_spec, load_learning_content, load_learning_v3_content
from app.seed.seed_questions import seed_database
from app.services.interaction_history import _learning_record


EXPECTED = {
    "variant_key": "learning_round_v1",
    "scenario_type": "application",
    "scenario": "大学の履修案内AIに、更新された履修規程を使わせたい。回答は「必要な手続き・提出期限・注意点」の順にそろえ、担当者が確認した質問と回答の例も改善に利用したい。",
    "task": "担当者の対応として、適切なものを3つ選びなさい。",
    "choices": {
        "correct": [
            "利用者の質問に応じて履修規程の該当箇所を検索し、質問と一緒にAIへ渡して回答を作らせる。",
            "「必要な手続き・提出期限・注意点」の順に説明するよう、AIへ渡すプロンプトに指示を加える。",
            "担当者が確認した質問と回答の例を学習用データにして、AIを追加訓練する。",
        ],
        "M1": [
            "履修規程を一度AIへ渡せば、その内容がモデルの重みに保存され、以後は検索しなくてもよい。",
            "回答例を毎回の質問に加えれば、学習用データによる訓練をしなくてもモデルの重みを調整できる。",
            "回答の順番を指示する文章をプロンプトに加えることで、モデルの重みを更新する。",
        ],
        "M3": [
            "回答例をRAGの検索対象に登録すれば、回答方法の追加訓練が完了する。",
            "履修規程の該当箇所を探すには、文書検索ではなくファインチューニングを使う。",
            "履修規程の本文をプロンプトに含めれば、プロンプト自体を文書の保存・検索先として使える。",
        ],
    },
}


def test_only_llm_first_learning_variant_changes_and_v3_is_preserved():
    assert hashlib.sha256(content_loader.LEARNING_V3_CONTENT_PATH.read_bytes()).hexdigest() == "2ae5b8483016db955d5fda4cc7aacca5e58c8f5bb070d51eb08fc6cd6022f156"
    expected = deepcopy(load_learning_v3_content())
    expected["version"] = 5
    expected["terms"]["llm_knowledge"]["variants"][0] = EXPECTED
    assert load_learning_content() == expected
    for stage in ("enrichment", "conceptual_change"):
        spec = learning_question_spec("llm_knowledge", stage)
        assert spec["_content_version"] == 5
        assert spec["body"] == EXPECTED["scenario"] + "\n\n" + EXPECTED["task"]
        for role, labels in (("correct", "ABC"), ("M1", "DEF"), ("M3", "GHI")):
            options = [o for o in spec["options"] if o["label"] in labels]
            assert [o["body"] for o in options] == EXPECTED["choices"][role]
            assert all(o["is_correct"] == (role == "correct") for o in options)
            assert all(o["misconception_type"] == (None if role == "correct" else role) for o in options)
        assert spec["options"][-1]["misconception_type"] == "unknown"


@pytest.mark.parametrize("mode,version", [("standard", 4), ("easy", 3), ("easy", 5), ("standard", 99)])
def test_mismatched_or_missing_learning_version_never_falls_back(mode, version):
    with pytest.raises(ValueError, match="version"):
        learning_question_spec("llm_knowledge", "enrichment", mode=mode, content_version=version)


def test_missing_v5_file_does_not_use_v3(tmp_path, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(content_loader, "LEARNING_V5_CONTENT_PATH", tmp_path / "missing.yml")
        load_learning_content.cache_clear()
        with pytest.raises(FileNotFoundError):
            load_learning_content()
    load_learning_content.cache_clear()


@pytest.mark.parametrize("version,spec_version", [(3, 11), (5, CURRENT_EXPERIMENT_SPEC_VERSION)])
@pytest.mark.parametrize("snapshot", [False, True])
def test_history_uses_saved_snapshot_or_saved_learning_version_without_writes(tmp_path, monkeypatch, version, spec_version, snapshot):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    monkeypatch.setattr(database, "engine", engine)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        participant = Participant(display_code="HISTORY", group_condition="proposed", learning_content_version=version,
                                  experiment_spec_version=spec_version, protocol_id=CURRENT_PROTOCOL_ID if version == 5 else "experiment-plan-2026-10-25-pretest-f-wording-v1")
        term = Term(slug="llm_knowledge", label="LLM", description="description", display_order=1)
        db.add_all([participant, term])
        db.flush()
        session = TutorSession(participant_id=participant.id, term_id=term.id, group_condition="proposed", session_index=1)
        db.add(session)
        db.flush()
        spec = learning_question_spec(term.slug, "enrichment", content_version=version)
        question = {"body": "保存時の問題", "options": [{"option_id": "D", "label": "D", "body": "保存時の選択本文"}]} if snapshot else {}
        turn = TutorTurn(tutor_session_id=session.id, turn_index=1, teaching_strategy="belief_revision", tutor_message="保存済み教材", learner_response="D",
                         practice_question_json=question, diagnosis_json={"learning_content_version": version},
                         grading_json={"is_sufficient": False, "selected_option_ids": ["D"]})
        db.add(turn)
        db.commit()
        if version == 3:
            before_rows = {model: deepcopy(db.execute(select(model.__table__)).mappings().all()) for model in (Participant, TutorSession, TutorTurn)}
            seed_database(db)
            seed_database(db)
            database.init_db()
            database.init_db()
            for model, rows in before_rows.items():
                assert db.execute(select(model.__table__)).mappings().all() == rows
        before = json.dumps([turn.practice_question_json, turn.diagnosis_json, turn.grading_json, participant.learning_content_version], sort_keys=True)
        record = _learning_record(db, session, turn)
        assert record["question_body"] == ("保存時の問題" if snapshot else spec["body"])
        assert record["selected_options"] == [{"label": "D", "body": "保存時の選択本文" if snapshot else spec["options"][3]["body"]}]
        assert json.dumps([turn.practice_question_json, turn.diagnosis_json, turn.grading_json, participant.learning_content_version], sort_keys=True) == before
        assert "履修規程" in record["question_body"] if version == 5 and not snapshot else "履修規程" not in record["question_body"]
    engine.dispose()
