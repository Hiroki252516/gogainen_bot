import csv
import io

import pytest
from fastapi.testclient import TestClient

from admin_client import AuthenticatedTestClient
from app.main import app
from app.db.session import SessionLocal
from app.models import Participant
from split_api_support import acknowledge_all_question_reviews, complete_presurvey, ok, select_roles

ENDPOINT = "/api/admin/pretest-result-display"


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("perfect", [False, True])
@pytest.mark.parametrize("mode", ["standard"])
@pytest.mark.parametrize("group,layout", [("A", "debug_fixed"), ("B", "randomized")])
def test_display_snapshot_and_navigation(enabled, perfect, mode, group, layout):
    client = AuthenticatedTestClient(app)
    previous = ok(client.get(ENDPOINT))["enabled"]
    settings = {name: ok(client.get(f"/api/admin/{name}"))["mode"] for name in ("question-set", "option-order")}
    pid = None
    try:
        ok(client.put(ENDPOINT, json={"enabled": enabled}))
        ok(client.put("/api/admin/option-order", json={"mode": layout}))
        pid = ok(client.post("/api/registrations", json={"assignment_code": group, "consent_checked": True, "student_number": "DISPLAY-SYNTHETIC"}))["participant_id"]
        complete_presurvey(client, pid)
        ok(client.put(ENDPOINT, json={"enabled": not enabled}))
        with SessionLocal() as db:
            assert db.get(Participant, pid).show_pretest_results is enabled
            assert db.get(Participant, pid).show_retest_results is enabled
        questions = ok(client.get(f"/api/experiment/{pid}/pretest"))["questions"]
        for index, question in enumerate(questions):
            roles = [None]
            if index == 0 and not perfect:
                roles = ["unknown"]
            ok(client.post("/api/attempts", json={"participant_id": pid, "phase": "pretest", "question_id": question["question_id"], "selected_option_ids": select_roles(question, roles)}))
        acknowledge_all_question_reviews(client, pid, "pretest")
        url = f"/api/participants/{pid}/diagnose-pretest"
        response = ok(client.post(url, json={}, headers={"Idempotency-Key": "display-score"}))
        assert ok(client.post(url, json={}, headers={"Idempotency-Key": "display-score"})) == response
        assert response["review_required"] is enabled
        action = "/final-test" if perfect else "/learning/llm_knowledge"
        assert response["next_url"] == ("/learning-targets" if enabled else action)
        review = ok(client.get(f"/api/participants/{pid}/learning-targets"))
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
            final_questions = ok(client.get(f"/api/experiment/{pid}/final-test"))["questions"]
            for question in final_questions:
                roles = [None]
                ok(client.post("/api/attempts", json={"participant_id": pid, "phase": "final_test", "question_id": question["question_id"], "selected_option_ids": select_roles(question, roles)}))
            acknowledge_all_question_reviews(client, pid, "final_test")
            final_score = ok(client.post(
                f"/api/participants/{pid}/score-final-test",
                json={},
                headers={"Idempotency-Key": "final-score-display"},
            ))
            assert ok(client.post(
                f"/api/participants/{pid}/score-final-test",
                json={},
                headers={"Idempotency-Key": "final-score-display"},
            )) == final_score
            assert final_score["review_required"] is enabled
            assert final_score["next_url"] == ("/learning-targets" if enabled else "/survey")
            reviewed = ok(client.get(f"/api/participants/{pid}/learning-targets"))
            assert reviewed["review_required"] is enabled
            assert bool(reviewed["test_results"]["results"]) is enabled
            assert reviewed["current_step"] == "survey"
    finally:
        if pid:
            ok(client.delete(f"/api/admin/participants/{pid}"))
        ok(client.put(ENDPOINT, json={"enabled": previous}))
        ok(client.put("/api/admin/option-order", json={"mode": settings["option-order"]}))


def test_admin_auth_strict_boolean_and_no_cache():
    assert TestClient(app).get(ENDPOINT).status_code == 401
    client = AuthenticatedTestClient(app)
    assert client.get(ENDPOINT).headers["cache-control"] == "no-store"
    for value in (None, 0, 1, "false", "true", [], {}):
        assert client.put(ENDPOINT, json={"enabled": value}).status_code == 422
    assert client.put(ENDPOINT, json={"enabled": True, "extra": 1}).status_code == 422


def test_nullable_migration_is_repeatable_and_preserves_existing_rows(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from app.db import session as database
    from app.models import Base, RuntimeSetting
    from app.services.pretest_display import current_setting, enabled, save_setting

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
        assert current_setting(db)
        save_setting(db, False)
    database.init_db()
    with Session(engine) as db:
        assert not current_setting(db)
        assert db.get(Participant, pid).show_pretest_results is None
        assert db.get(Participant, pid).show_retest_results is None
    engine.dispose()


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("round_two", [False, True])
@pytest.mark.parametrize("group,layout", [("A", "debug_fixed"), ("B", "randomized")])
def test_retest_result_display_is_snapshotted_and_controls_review(enabled, round_two, group, layout):
    from split_api_support import answer_test, create_trial

    client = AuthenticatedTestClient(app)
    previous = ok(client.get(ENDPOINT))["enabled"]
    previous_layout = ok(client.get("/api/admin/option-order"))["mode"]
    try:
        ok(client.put(ENDPOINT, json={"enabled": enabled}))
        ok(client.put("/api/admin/option-order", json={"mode": layout}))
        with create_trial(group, layout) as (_, pid):
            # Registration snapshots the switch. Changing it afterward must not
            # affect this participant's upcoming retest review.
            ok(client.put(ENDPOINT, json={"enabled": not enabled}))
            with SessionLocal() as db:
                participant = db.get(Participant, pid)
                assert participant.show_pretest_results is enabled
                assert participant.show_retest_results is enabled

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
    finally:
        ok(client.put(ENDPOINT, json={"enabled": previous}))
        ok(client.put("/api/admin/option-order", json={"mode": previous_layout}))


def test_existing_null_retest_snapshot_keeps_retest_results_visible():
    from split_api_support import answer_test, create_trial

    client = AuthenticatedTestClient(app)
    previous = ok(client.get(ENDPOINT))["enabled"]
    try:
        ok(client.put(ENDPOINT, json={"enabled": False}))
        with create_trial("A", "debug_fixed") as (_, pid):
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
    finally:
        ok(client.put(ENDPOINT, json={"enabled": previous}))


@pytest.mark.parametrize("group", ["A", "B"])
@pytest.mark.parametrize("layout", ["debug_fixed", "randomized"])
def test_hidden_review_three_terms_progress_to_retest(group, layout):
    from split_api_support import create_trial, confirm
    client = AuthenticatedTestClient(app)
    previous = ok(client.get(ENDPOINT))["enabled"]
    try:
        ok(client.put(ENDPOINT, json={"enabled": False}))
        with create_trial(group, layout) as (client, pid):
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
    finally:
        ok(client.put(ENDPOINT, json={"enabled": previous}))
