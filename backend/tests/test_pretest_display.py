import csv
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models import Participant
from split_api_support import acknowledge_all_question_reviews, create_trial, ok, select_roles


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("perfect", [False, True])
@pytest.mark.parametrize("test_content_mode", ["application", "basic_understanding", "four_topic_fundamentals"])
@pytest.mark.parametrize("group,layout", [("A", "debug_fixed"), ("B", "randomized")])
def test_display_snapshot_and_navigation(enabled, perfect, test_content_mode, group, layout):
    with create_trial(
        group, layout, first_question_only=False,
        show_pretest_results=enabled, show_retest_results=enabled,
        test_content_mode=test_content_mode,
    ) as (client, pid):
        questions = ok(client.get(f"/api/experiment/{pid}/pretest"))["questions"]
        for index, question in enumerate(questions):
            roles = [None, None, None] if question.get("selection_mode") == "multiple" else [None]
            if index == 0 and not perfect:
                roles = [None, None, "M1"] if question.get("selection_mode") == "multiple" else ["unknown"]
            ok(client.post("/api/attempts", json={"participant_id": pid, "phase": "pretest", "question_id": question["question_id"], "selected_option_ids": select_roles(question, roles)}))
        acknowledge_all_question_reviews(client, pid, "pretest")
        url = f"/api/participants/{pid}/diagnose-pretest"
        response = ok(client.post(url, json={}, headers={"Idempotency-Key": "display-score"}))
        assert ok(client.post(url, json={}, headers={"Idempotency-Key": "display-score"})) == response
        assert response["review_required"] is enabled
        first_target = "transformer" if test_content_mode == "four_topic_fundamentals" else "llm_knowledge"
        action = "/survey" if perfect else f"/learning/{first_target}"
        assert response["next_url"] == ("/learning-targets" if enabled else action)
        review = ok(client.get(f"/api/participants/{pid}/learning-targets"))
        assert review["current_step"] == ("survey" if perfect else "learning_targets")
        assert review["next_url"] == ("/learning-targets" if enabled and not perfect else action)
        assert review["review_required"] is enabled
        assert bool(review["pretest_results"]) is enabled
        assert bool(review["test_results"]["results"]) is enabled
        assert bool(review["targets"]) is not perfect
        current = ok(client.get(f"/api/participants/{pid}/current-step"))
        assert current["next_url"] == (action if not enabled or perfect else "/learning-targets")
        logs = ok(client.get(f"/api/admin/participants/{pid}/logs"))
        assert logs["participant"]["show_pretest_results"] is enabled
        assert logs["participant"]["show_retest_results"] is enabled
        participant_rows = csv.DictReader(io.StringIO(client.get("/api/admin/export/participants.csv").text))
        exported = next(row for row in participant_rows if row["id"] == pid)
        assert exported["show_pretest_results"] == str(enabled)
        assert exported["show_retest_results"] == str(enabled)
        if perfect:
            assert client.get(f"/api/experiment/{pid}/final-test").status_code == 409
            assert client.get(f"/api/experiment/{pid}/retest").status_code == 409
            assert client.get(f"/api/participants/{pid}/learning-targets").json()["targets"] == []
            assert current["step"] == "survey"
def test_removed_admin_setting_endpoints_return_not_found():
    client = TestClient(app)
    for endpoint in ("pretest-result-display", "question-review-display", "first-question-only"):
        assert client.get(f"/api/admin/{endpoint}").status_code == 404
        assert client.put(f"/api/admin/{endpoint}", json={"enabled": True}).status_code == 404


def test_nullable_migration_is_repeatable_and_preserves_existing_rows(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from app.db import session as database
    from app.models import Base, RuntimeSetting
    from app.services.pretest_display import enabled

    engine = create_engine(f"sqlite:///{tmp_path / 'display.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        participant = Participant(display_code="OLD-DISPLAY", group_condition="control", experiment_spec_version=26)
        db.add_all([participant, RuntimeSetting(id=1)])
        db.commit()
        pid = participant.id
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE participants DROP COLUMN show_pretest_results"))
        conn.execute(text("ALTER TABLE participants DROP COLUMN show_retest_results"))
        conn.execute(text("ALTER TABLE runtime_settings DROP COLUMN show_pretest_results"))
    monkeypatch.setattr(database, "engine", engine)
    database.init_db()
    database.init_db()
    with Session(engine) as db:
        assert db.get(Participant, pid).show_pretest_results is None
        assert db.get(Participant, pid).show_retest_results is None
        assert db.get(Participant, pid).experiment_spec_version == 26
        assert enabled(db.get(Participant, pid).show_pretest_results)
        assert enabled(db.get(Participant, pid).show_retest_results)
    database.init_db()
    with Session(engine) as db:
        assert db.get(RuntimeSetting, 1).show_pretest_results is None
        assert db.get(Participant, pid).show_pretest_results is None
        assert db.get(Participant, pid).show_retest_results is None
    engine.dispose()


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("round_two", [False, True])
@pytest.mark.parametrize("group,layout", [("A", "debug_fixed"), ("B", "randomized")])
def test_retest_result_display_is_snapshotted_and_controls_review(enabled, round_two, group, layout):
    from split_api_support import answer_test, create_trial

    with create_trial(
        group, layout, first_question_only=False,
        show_pretest_results=enabled, show_retest_results=enabled,
    ) as (client, pid):
        answer_test(client, pid, "pretest", "llm_knowledge", ("unknown", "unknown"))
        ok(client.post(f"/api/participants/{pid}/give-up-learning", json={}))

        first_rounds = 2 if round_two else 1
        final_score = None
        for round_index in range(first_rounds):
            _, final_score = answer_test(
                client, pid, "retest", "llm_knowledge", ("unknown", "unknown")
            )
            if round_index + 1 < first_rounds:
                assert final_score["review_required"] is enabled
                first_review = ok(client.get(f"/api/participants/{pid}/learning-targets"))
                assert first_review["review_required"] is enabled
                assert bool(first_review["test_results"]["results"]) is enabled
                ok(client.post(f"/api/participants/{pid}/give-up-learning", json={}))

        assert final_score is not None
        assert final_score["review_required"] is enabled
        if enabled:
            assert final_score["next_url"] == "/learning-targets"
        elif round_two:
            assert final_score["next_url"] == "/survey"
        else:
            assert final_score["next_url"] == "/learning/llm_knowledge"
        reviewed = ok(client.get(f"/api/participants/{pid}/learning-targets"))
        assert reviewed["review_required"] is enabled
        assert bool(reviewed["test_results"]["results"]) is enabled
        expected_current_url = "/survey" if round_two else (
            "/learning-targets" if enabled else final_score["next_url"]
        )
        assert ok(client.get(f"/api/participants/{pid}/current-step"))["next_url"] == expected_current_url


def test_existing_null_retest_snapshot_keeps_retest_results_visible():
    from split_api_support import answer_test, create_trial

    with create_trial(
        "A", "debug_fixed", first_question_only=False,
        show_pretest_results=False, show_retest_results=False,
    ) as (client, pid):
        with SessionLocal() as db:
            participant = db.get(Participant, pid)
            participant.show_pretest_results = False
            participant.show_retest_results = None
            db.commit()
        answer_test(client, pid, "pretest", "llm_knowledge", ("unknown", "unknown"))
        ok(client.post(f"/api/participants/{pid}/give-up-learning", json={}))
        _, scored = answer_test(client, pid, "retest", "llm_knowledge", ("unknown", "unknown"))
        assert scored["review_required"] is True
        assert scored["next_url"] == "/learning-targets"
        reviewed = ok(client.get(f"/api/participants/{pid}/learning-targets"))
        assert reviewed["review_required"] is True
        assert reviewed["test_results"]["results"]


@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
def test_hidden_review_three_terms_progress_to_retest(group, layout):
    from split_api_support import create_trial, confirm
    with create_trial(
        group, layout, first_question_only=False,
        show_pretest_results=False, show_retest_results=False,
    ) as (client, pid):
            questions = ok(client.get(f"/api/experiment/{pid}/pretest"))["questions"]
            for question in questions:
                ok(client.post("/api/attempts", json={"participant_id": pid, "phase": "pretest", "question_id": question["question_id"], "selected_option_ids": select_roles(question, ["unknown"])}))
            acknowledge_all_question_reviews(client, pid, "pretest")
            diagnosed = ok(client.post(f"/api/participants/{pid}/diagnose-pretest", json={}))
            slugs = ["llm_knowledge", "multi_agent", "memory_process"]
            assert diagnosed["learning_target_slugs"] == slugs
            for index, slug in enumerate(slugs):
                current = ok(client.get(f"/api/participants/{pid}/current-step"))
                assert current["next_url"] == f"/learning/{slug}"
                result = confirm(client, pid, slug, questions, (None, None), None, 1)
                assert result["next_url"] == (f"/learning/{slugs[index+1]}" if index < 2 else "/retest")
            assert ok(client.get(f"/api/participants/{pid}/current-step"))["next_url"] == "/retest"
            with SessionLocal() as db:
                participant = db.get(Participant, pid)
                participant.current_step = "learning_targets"
                db.commit()
            for endpoint in ("current-step", "learning-targets"):
                response = client.get(f"/api/participants/{pid}/{endpoint}")
                assert response.status_code == 503
                assert response.json()["detail"]["error_code"] == "learning_navigation_unavailable"
            with SessionLocal() as db:
                db.get(Participant, pid).current_step = "retest"
                db.commit()
