from copy import deepcopy
import hashlib
import json

import pytest
import yaml
from admin_client import AuthenticatedTestClient as TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from split_api_support import assert_retest_flow, complete_presurvey

from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID
from app.core.question_sets import ASSESSMENT_BANK_VERSIONS, HISTORICAL_ASSESSMENT_BANK_VERSIONS, LEARNING_CONTENT_VERSIONS, assessment_construct_key
from app.db import session as database
from app.db.session import SessionLocal
from app.main import app
from app.models import Attempt, Base, EvaluationSummary, Participant, Question, QuestionOption, Term
from app.seed import content_loader
from app.seed.content_loader import assessment_question_spec, learning_question_spec, load_content
from app.seed.seed_questions import _upsert_question, seed_database
from app.services import experiment
from app.services.interaction_history import _test_record, build_interaction_history
from app.services.prefetch import wait_for_prefetch_tasks


EXPECTED = {
    "multi_agent": [
        {
            "variant_key": "retest_v1",
            "scenario": "旅行会社が、公共交通を利用する日帰り観光プランを提案するAIシステムを開発している。\n\n例えば、利用者が「午前に美術館、午後に水族館を訪れ、17時までに出発駅へ戻りたい」と希望した場合、観光候補の情報、訪問する順番や滞在時間、電車やバスの移動条件などを考慮して、実行可能な旅行計画を案内する必要がある。\n\n開発担当者は、複数のAIエージェントに仕事を分担させ、協力して旅行計画を作成する仕組みを検討している。",
            "task": "このような旅行計画AIを実現するための開発担当者の対応として、適切なものを3つ選びなさい。",
            "choices": {
                "correct": [
                    "観光候補を調べるAI、訪問順や滞在時間を決めるAI、電車やバスの移動条件を確認するAIを設け、それぞれが何を調べ、何を判断するかを設定する。",
                    "観光候補担当が見つけた施設や営業時間を日程担当へ渡し、日程担当が作成した訪問順と予定時刻を移動確認担当に引き継ぐ仕組みを設ける。",
                    "移動確認担当が、予定された出発時刻では17時までに駅へ戻れないと判断したら、その結果を日程担当へ返し、訪問順や滞在時間を見直せるようにする。"
                ],
                "M1": [
                    "観光調査・日程作成・移動確認のAIに役割を設定して個別に質問すれば、他の担当が出した結果も共有されると考え、調査内容を次の担当へ渡す仕組みは設けない。",
                    "観光候補担当が人気順に並べた施設は、その順番も日程担当が引き継ぐべきだと考え、移動時間に合わせて訪問順を変更する必要があっても、元の並びを優先する。",
                    "移動確認担当が前日に調べた電車の運行情報は、旅行当日もそのまま使えると考え、計画を案内する直前に運休や時刻変更がないかを確認する仕組みは設けない。"
                ],
                "M3": [
                    "1つのAIに「観光候補」「日程」「移動」の3つの見出しで回答させれば、各見出しが別のAIの担当に当たると考え、複数のエージェントが協力する構成として扱う。",
                    "電車の発着時刻だけを返す乗換検索ツールも、日程担当へ交通情報を渡す役割があるので、移動条件を判断するAIエージェントの一つとして数える。",
                    "1つのAIが移動距離に応じて徒歩と電車の案内を切り替える場合、切り替え先の処理をそれぞれ独立したAIエージェントとして数え、複数のAIが連携する構成とみなす。"
                ]
            }
        },
        {
            "variant_key": "retest_v2",
            "scenario": "博物館が、来館者に短い見学コースを提案するAIシステムを開発している。ある来館者は「恐竜の展示を優先したい。化石も見られるとうれしい。見学時間は40分以内にしたい」と希望している。博物館には、展示ごとの内容、展示室の場所、見学時間の目安をまとめた資料がある。開発担当者は、複数のAIエージェントを協力させ、来館者の希望と時間の制限に合う見学案を作りたいと考えている。",
            "task": "このAIシステムで複数のAIエージェントを協力させる設計として、適切な記述を3つ選びなさい。",
            "choices": {
                "correct": [
                    "来館者の希望を整理するAIと、展示の内容・場所・見学時間を調べるAIを別々に設け、それぞれの担当が何をまとめ、どの情報を次の担当へ渡すかをあらかじめ設計する。",
                    "希望整理担当が「恐竜を優先し、40分以内で見たい」とまとめた結果を展示調査担当へ渡し、その条件をもとに展示の内容や見学時間を調べて候補を選べるようにする。",
                    "展示調査担当が挙げた候補と希望整理担当がまとめた条件を照らし合わせ、全部見ると40分を超える場合は候補の変更や見学順の調整を依頼し、無理のない案を作れるようにする。"
                ],
                "M1": [
                    "希望整理と展示調査を別々のAIに担当させれば、各AIはほかの担当がまとめた内容も把握できると考え、希望や展示候補を受け渡すための情報共有の仕組みは用意しない。",
                    "希望整理担当が「恐竜を優先」とまとめたなら、展示調査担当も同じ内容の結論を返すことが連携の条件だと考え、展示の場所や所要時間を調べて異なる情報を示すことは避ける。",
                    "展示調査担当が候補として挙げた展示は、来館者の希望や40分の制限にも合っていると考え、希望整理担当がまとめた条件と候補の所要時間を照らし合わせず、そのまま案内へ採用する。"
                ],
                "M3": [
                    "1つのAIに「希望整理役として考え、次に展示調査役として考える」と指示し、1回の回答を二段階に分けることを、別々のAIエージェントが協力する仕組みと同じものとして扱う。",
                    "博物館の展示データから名前や場所を返す検索ツールが、調査担当のAIへ結果を渡す場合、そのツールも情報の受け渡しに参加しているので、独立したAIエージェントの一つとして数える。",
                    "来館者が恐竜を希望した場合と化石を希望した場合で案内を切り替える条件分岐を用意し、分岐先が複数あることを、別々のAIエージェントが協力する構成と同じものとして扱う。"
                ]
            }
        }
    ],
    "memory_process": [
        {
            "variant_key": "retest_v1",
            "scenario": "料理の献立を提案するAIサービスを開発している。ある利用者は以前の相談で「ピーマンは苦手なので、今後の献立には入れないでほしい」と伝えた。その後、別の日に「最近は食べられるようになったので、これからはピーマンも献立に入れてほしい」と希望を変更した。また、提案された料理について「味が濃かったので、次からは薄味にしてほしい」と感想を伝えた。開発担当者は、別の日に新しい相談が始まった場合にも、その利用者の新しい希望や過去の感想を適切に反映できる仕組みを作りたいと考えている。",
            "task": "この目的を実現するための情報の保存・利用方法として、適切な説明を3つ選びなさい。",
            "choices": {
                "correct": [
                    "利用者が「ピーマンを避けたい」と話した段階で、その希望を利用者別の記録に保存し、別の日の相談でも必要に応じて取り出し、献立の提案に利用できるようにする。",
                    "本人が「今後はピーマンも使ってほしい」と希望を変更したら、以前の「避けたい」という記録を現在の希望と区別して更新し、その後の献立には変更後の条件を反映する。",
                    "料理への「味が濃かった」という感想から「次から薄味にしてほしい」という希望を記録し、後日の提案でも必要に応じて取り出して、味付けを考える際の参考にする。"
                ],
                "M1": [
                    "過去の相談を全文保存しておけば、AIは別の日の相談でもそこに書かれた好みを自動的に把握できると考え、保存した会話から必要な情報を取り出す処理は設けない。",
                    "最初に登録した「ピーマンを避けたい」という希望は、利用者の基本的な好みを表すと考え、本人が「今後は使ってほしい」と変更しても、以前の記録を優先して献立を作る。",
                    "「味が濃かった」という感想をもとにAIが一度薄味の献立を提案できれば、その改善内容は次の相談にも引き継がれると考え、感想や新しい希望を保存する処理は設けない。"
                ],
                "M3": [
                    "利用者が伝えた「ピーマンを避けたい」という希望を追加訓練でモデルの重みに覚えさせる処理を、利用者別の好みを保存し、必要に応じて更新・検索する記憶管理と同じ仕組みとして扱う。",
                    "公開レシピから「ピーマンを使わない献立」を検索できれば、以前その利用者が「ピーマンを避けたい」と伝えたことも覚えていると考え、レシピ検索を個人の記憶機能として扱う。",
                    "新しい会話で以前の相談文をプロンプトに貼り付けて好みを参照できれば、その入力操作自体を、好みを継続的に保存し、変更に合わせて記録を更新する記憶管理の仕組みと同じものとして扱う。"
                ]
            }
        },
        {
            "variant_key": "retest_v2",
            "scenario": "企業が、利用者からの問い合わせに対応するAIを開発している。ある利用者は以前の相談で「今後の連絡は電話でしてほしい」と伝えたが、別の日に「これからはメールで連絡してほしい」と希望を変更した。\n\nさらに、案内メールを受け取った際に、「文章が長いとわかりにくいので、次からは要点を先に書いてほしい」と感想を伝えた。\n\n開発担当者は、利用者が別の日に新しい問い合わせをした場合にも、その利用者の現在の連絡方法や案内文への希望を反映できる記憶機能を設けたいと考えている。",
            "task": "この目的を実現するための情報の保存・利用方法として、適切な説明を3つ選びなさい。",
            "choices": {
                "correct": [
                    "利用者が「電話で連絡してほしい」と伝えたら、その希望を利用者ごとの記録に残し、別の日の問い合わせで連絡方法を決める際に、関連する記録を取り出して利用できるようにする。",
                    "利用者が後から「今後はメールで連絡してほしい」と伝えたら、以前の電話希望と新しい指定を照合し、現在有効な連絡方法をメールに更新して、次回の案内に反映する。",
                    "案内メールへの「次からは要点を先に書いてほしい」という感想を、今後の案内にも役立つ希望として保存し、後の問い合わせで必要に応じて取り出し、文章の作り方に利用する。"
                ],
                "M1": [
                    "これまでの問い合わせ履歴を利用者ごとに保存しておけば、次の相談ではAIがその履歴を自動的に把握すると考え、回答前に保存内容を取得する仕組みは用意しない。",
                    "最初の「電話希望」は利用者が登録した基本設定なので、後から「今後はメール」と伝えられても、変更は一時的なものだと考え、確認せずに以前の電話希望を優先して案内する。",
                    "前回の案内メールで「要点を先に書いてほしい」と言われ、その場で文章を直せたなら、AIはその改善点を次回も覚えていると考え、感想を記録する仕組みは用意しない。"
                ],
                "M3": [
                    "利用者から聞いた「今後はメール希望」という情報を追加訓練用データとしてモデルの重みに覚えさせる処理を、利用者ごとの連絡方法を保存・更新する記憶管理と同じ仕組みとして設計する。",
                    "過去の問い合わせで似た質問をした人への対応例を検索し、「メールで案内した例」が見つかったら、その検索結果を、今回の利用者が以前指定した連絡方法の記憶として扱う。",
                    "前回の会話文を新しい問い合わせの入力欄に貼り付ければ、その入力欄が連絡方法を継続して保存・更新する記憶の仕組みにもなると考え、利用者別の記録は管理しない。"
                ]
            }
        }
    ]
}


def test_assessment_v6_only_changes_four_retests_and_preserves_banks():
    assert CURRENT_EXPERIMENT_SPEC_VERSION not in HISTORICAL_ASSESSMENT_BANK_VERSIONS
    assert HISTORICAL_ASSESSMENT_BANK_VERSIONS[19]["standard"] == "scenario-actions-v5"
    assert hashlib.sha256(content_loader.SCENARIO_ACTIONS_V5_CONTENT_PATH.read_bytes()).hexdigest() == "e9022f40a5b4f6f8b56a8468e6feb9169a9889155702363701497c3cd11ee8d6"
    assert hashlib.sha256(content_loader.LEARNING_V12_CONTENT_PATH.read_bytes()).hexdigest() == "87dc5c40081f113350b9b7ffabef5f46fe6fe0fd0e68949eb68755c68de6eb4b"
    expected = yaml.safe_load(content_loader.SCENARIO_ACTIONS_V5_CONTENT_PATH.read_text(encoding="utf-8"))
    expected["assessment_bank_version"] = "scenario-actions-v6"
    for term in expected["terms"]:
        if term["slug"] in EXPECTED:
            term["questions"]["retest"] = EXPECTED[term["slug"]]
    adopted = yaml.safe_load(content_loader.SCENARIO_ACTIONS_V6_CONTENT_PATH.read_text(encoding="utf-8"))
    assert adopted == expected


@pytest.mark.parametrize("slug", list(EXPECTED))
@pytest.mark.parametrize("index", [1, 2])
def test_exact_retest_text_roles_and_paragraphs(slug, index):
    source = EXPECTED[slug][index - 1]
    adopted = yaml.safe_load(content_loader.SCENARIO_ACTIONS_V6_CONTENT_PATH.read_text(encoding="utf-8"))
    variant = next(term for term in adopted["terms"] if term["slug"] == slug)["questions"]["retest"][index - 1]
    spec = {"body": variant["scenario"] + "\n\n" + variant["task"], "options": content_loader._assessment_options(variant)}
    assert spec["body"] == source["scenario"] + "\n\n" + source["task"]
    paragraphs = 4 if (slug, index) in {("multi_agent", 1), ("memory_process", 2)} else 2
    assert len(spec["body"].split("\n\n")) == paragraphs
    assert all("\n" not in paragraph for paragraph in spec["body"].split("\n\n"))
    assert "**" not in spec["body"] and "問題：" not in spec["body"]
    for role, labels in (("correct", "ABC"), ("M1", "DEF"), ("M3", "GHI")):
        options = [option for option in spec["options"] if option["label"] in labels]
        assert [option["body"] for option in options] == source["choices"][role]
        assert all(option["is_correct"] == (role == "correct") for option in options)
        assert all(option["misconception_type"] == (None if role == "correct" else role) for option in options)
    assert spec["options"][-1] == content_loader.UNKNOWN_OPTION
    final = assessment_question_spec(slug, "final_test")
    first = assessment_question_spec(slug, "retest", 1)
    assert final["body"] == first["body"] and final["options"] == first["options"]


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def _selected(question, source, labels):
    bodies = {option["body"] for option in source["options"] if option["label"] in labels}
    return [option["option_id"] for option in question["options"] if option["body"] in bodies]


def _create(client, group, layout):
    created = _ok(client.post("/api/participants", json={"assignment_code": group, "consent_checked": True, "student_number": "MULTI-MEMORY-RETEST-SYNTHETIC"}))
    complete_presurvey(client, created["participant_id"])
    with SessionLocal() as db:
        participant = db.get(Participant, created["participant_id"])
        assert participant.experiment_spec_version == CURRENT_EXPERIMENT_SPEC_VERSION and participant.learning_content_version == LEARNING_CONTENT_VERSIONS["standard"]
        participant.option_order_mode = layout
        db.commit()
    return created["participant_id"]


def _answer_test(client, pid, slug, phase, labels, index=1):
    route = "final-test" if phase == "final_test" else phase
    questions = _ok(client.get(f"/api/experiment/{pid}/{route}"))["questions"]
    target_question = next(question for question in questions if question["term_slug"] == slug)
    if phase != "pretest":
        source = assessment_question_spec(slug, phase, index)
        assert target_question["body"] == source["body"]
    for question in questions:
        assert all(set(option) == {"option_id", "label", "body", "exclusive"} for option in question["options"])
        source = assessment_question_spec(question["term_slug"], phase, index)
        chosen = labels if question["term_slug"] == slug else "ABC"
        payload = {"participant_id": pid, "question_id": question["question_id"], "selected_option_ids": _selected(question, source, chosen)}
        headers = {"Idempotency-Key": f"{phase}-{index}-{question['term_slug']}"}
        result = _ok(client.post("/api/attempts", json=payload, headers=headers))
        assert _ok(client.post("/api/attempts", json=payload, headers=headers)) == result
        with SessionLocal() as db:
            saved = db.query(Attempt).filter_by(participant_id=pid, question_id=question["question_id"]).all()
            assert len(saved) == 1
            assert saved[0].is_correct is None and saved[0].misconception_type is None
            assert saved[0].question_body_snapshot == question["body"]
            assert _test_record(db, saved[0])["selected_options"] == [
                {"label": option["label"], "body": option["body"]} for option in question["options"] if option["option_id"] in payload["selected_option_ids"]]
    return target_question


def _assert_grades(pid, slug, phase, labels, index):
    with SessionLocal() as db:
        attempts = db.query(Attempt).filter_by(participant_id=pid, phase=phase, test_round=f"retest_{index}").all()
        assert len(attempts) == 3
        for attempt in attempts:
            chosen = labels if db.get(Term, attempt.term_id).slug == slug else "ABC"
            expected_type = "M3" if any(label in chosen for label in "GHI") else "M1" if any(label in chosen for label in "DEF") else "unknown" if chosen == "J" else None
            assert attempt.is_correct == (chosen == "ABC") and attempt.misconception_type == expected_type


def _learn(client, pid, slug):
    session = _ok(client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": slug}))
    turn = _ok(client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={}))
    source = learning_question_spec(slug, turn["learning_stage"], turn["practice_question"]["learning_variant_index"])
    result = _ok(client.post(f"/api/tutor-turns/{turn['turn_id']}/respond",
                            json={"selected_option_ids": _selected(turn["practice_question"], source, "ABC")}))
    assert result["is_sufficient"] and result["feedback"]
    wait_for_prefetch_tasks()


@pytest.mark.parametrize("slug", list(EXPECTED))
@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
@pytest.mark.parametrize("labels", ["ABC", "DEF", "GHI", "ADH", "J"])
def test_natural_two_rounds_scoring_replay_review_and_history(slug, group, layout, labels):
    assert_retest_flow(slug, group, layout, "retest", labels, None if labels == "ABC" else ("unknown" if labels == "J" else ("M1" if labels == "DEF" else "M3")), round_two=True)


@pytest.mark.parametrize("slug", list(EXPECTED))
@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
@pytest.mark.parametrize("phase", ["retest", "final_test"])
@pytest.mark.parametrize("perfect", [False, True])
def test_first_posttest_shared_v1_and_early_mastery(slug, group, layout, phase, perfect):
    assert_retest_flow(slug, group, layout, phase, "ABC" if perfect else "GHI", None if perfect else "M3", stop_after_first=True)


@pytest.mark.parametrize("slug", list(EXPECTED))
@pytest.mark.parametrize("index", [1, 2])
@pytest.mark.parametrize("snapshot", [False, True])
def test_spec19_history_seed_and_repair_preserve_v5(tmp_path, monkeypatch, slug, index, snapshot):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    monkeypatch.setattr(database, "engine", engine)
    Base.metadata.create_all(engine)
    old = yaml.safe_load(content_loader.SCENARIO_ACTIONS_V5_CONTENT_PATH.read_text(encoding="utf-8"))
    try:
        with Session(engine) as db:
            for order, data in enumerate(old["terms"], start=1):
                term = Term(slug=data["slug"], label=data["label"], description=data["description"], display_order=order)
                db.add(term)
                db.flush()
                for phase in ("pretest", "retest", "final_test"):
                    variants = data["questions"]["retest"][:1] if phase == "final_test" else data["questions"][phase]
                    for variant in variants:
                        _upsert_question(db, term, phase=phase, question_type="multi_select",
                                         body=variant["scenario"] + "\n\n" + variant["task"], expected_answer="A、B、Cをすべて選択し、それ以外を選ばない。",
                                         construct_key=assessment_construct_key(term.slug, phase, bank_version="scenario-actions-v5"),
                                         variant_key=variant["variant_key"],
                                         options=[(option["label"], option["body"], option["is_correct"], option["misconception_type"]) for option in content_loader._assessment_options(variant)])
            term = db.query(Term).filter_by(slug=slug).one()
            question = db.query(Question).filter_by(term_id=term.id, phase="retest", variant_key=f"retest_v{index}").one()
            option = db.query(QuestionOption).filter_by(question_id=question.id, option_label="H").one()
            participant = Participant(display_code="V5-HISTORY", group_condition="control", current_step="learning_targets",
                                      learning_content_version=12, experiment_spec_version=19,
                                      protocol_id="experiment-plan-2026-10-26-llm-confirmation-retest-v1", retest_cycles_completed=index)
            db.add(participant)
            db.flush()
            attempt = Attempt(participant_id=participant.id, term_id=term.id, question_id=question.id, phase="retest",
                              test_round=f"retest_{index}", is_correct=False, misconception_type="M3", selected_option_ids=[option.id],
                              question_body_snapshot="保存時の問題" if snapshot else None,
                              option_order_snapshot=[{"option_id": option.id, "label": "B", "body": "保存時の選択肢"}] if snapshot else None)
            db.add_all([attempt, EvaluationSummary(participant_id=participant.id, group_condition="control", pretest_score=0.125)])
            db.commit()
            protected = {model: deepcopy(db.execute(select(model.__table__)).mappings().all()) for model in (Participant, Attempt, EvaluationSummary)}
            questions_before = {row.id: (row.body, row.construct_key, row.variant_key) for row in db.query(Question)}
            options_before = {row.id: (row.body, row.is_correct, row.misconception_type) for row in db.query(QuestionOption)}
            seed_database(db)
            seed_database(db)
            database.init_db()
            database.init_db()
            for model, rows in protected.items():
                assert db.execute(select(model.__table__)).mappings().all() == rows
            for qid, fields in questions_before.items():
                saved = db.get(Question, qid)
                assert (saved.body, saved.construct_key, saved.variant_key) == fields and not saved.is_active
            for oid, fields in options_before.items():
                saved = db.get(QuestionOption, oid)
                assert (saved.body, saved.is_correct, saved.misconception_type) == fields
            current = db.query(Question).filter_by(term_id=term.id, phase="retest", is_active=True).filter(Question.variant_key == f"retest_v{index}_q1").all()
            assert len(current) == 1
            assert all(row.id != question.id for row in current)
            before_json = json.dumps([attempt.question_body_snapshot, attempt.option_order_snapshot], sort_keys=True)
            record = _test_record(db, attempt)
            assert record["question_body"] == ("保存時の問題" if snapshot else question.body)
            assert record["selected_options"] == [{"label": "B" if snapshot else "H", "body": "保存時の選択肢" if snapshot else option.body}]
            restored = experiment._test_result_question(db, participant, term, f"retest_{index}", "retest")
            assert restored.id == question.id
            review = experiment.latest_test_results(db, participant.id)
            row = next(row for row in review["results"] if row["term_slug"] == slug)
            assert row["question_body"] == record["question_body"]
            assert json.dumps([attempt.question_body_snapshot, attempt.option_order_snapshot], sort_keys=True) == before_json
    finally:
        engine.dispose()
