from __future__ import annotations

import asyncio
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models import AICallLog, EvaluationSummary, Term, TutorSession, TutorTurn
import app.services.experiment as experiment_service
from app.services.prefetch import wait_for_prefetch_tasks
from app.services.tutor_prefetch import TutorPrefetchRegistry


client = TestClient(app)


def test_prefetch_wait_propagates_caller_cancellation():
    async def scenario() -> None:
        registry = TutorPrefetchRegistry()
        started = asyncio.Event()

        async def worker(_handle) -> None:
            started.set()
            await asyncio.Event().wait()

        handle = registry.prepare("session", "participant")
        assert handle.start(worker)
        waiter = asyncio.create_task(registry.wait_for("session"))
        await asyncio.wait_for(started.wait(), timeout=1)

        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert handle._task is not None
        assert not handle._task.done()

        handle.abort()
        await asyncio.gather(handle._task, return_exceptions=True)

    asyncio.run(scenario())


def _ids_for_labels(question: dict, labels: list[str]) -> list[str]:
    by_label = {option["label"]: option["option_id"] for option in question["options"]}
    return [by_label[label] for label in labels]


def _create_participant_with_pretest() -> str:
    participant = client.post(
        "/api/participants",
        json={"assignment_code": "A", "consent_checked": True},
    )
    assert participant.status_code == 200, participant.text
    pid = participant.json()["participant_id"]
    questions = client.get(f"/api/experiment/{pid}/pretest").json()["questions"]
    for question in questions:
        response = client.post(
            "/api/attempts",
            json={
                "participant_id": pid,
                "question_id": question["question_id"],
                "phase": "pretest",
                "selected_option_ids": _ids_for_labels(question, ["D", "E", "F"]),
            },
        )
        assert response.status_code == 200, response.text
    diagnosis = client.post(f"/api/participants/{pid}/diagnose-pretest")
    assert diagnosis.status_code == 200, diagnosis.text
    return pid


def _start_first_turn(pid: str) -> tuple[dict, dict]:
    session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "llm_knowledge"})
    assert session.status_code == 200, session.text
    turn = client.post(f"/api/tutor-sessions/{session.json()['tutor_session_id']}/turns", json={})
    assert turn.status_code == 200, turn.text
    return session.json(), turn.json()


def _term_session(db, pid: str, slug: str) -> TutorSession:
    term = db.query(Term).filter_by(slug=slug).one()
    return db.query(TutorSession).filter_by(participant_id=pid, term_id=term.id).order_by(TutorSession.started_at.desc()).one()


def test_first_learning_turn_prefetches_all_later_targets():
    pid = _create_participant_with_pretest()
    session, turn = _start_first_turn(pid)
    wait_for_prefetch_tasks()
    summary_response = client.post(f"/api/participants/{pid}/evaluation-summary/recalculate")
    assert summary_response.status_code == 200, summary_response.text

    db = SessionLocal()
    try:
        assert turn["turn_index"] == 1
        for slug in ("multi_agent", "memory_process"):
            prefetched_session = _term_session(db, pid, slug)
            assert prefetched_session.prefetch_state == "ready"
            prefetched_turn = db.query(TutorTurn).filter_by(tutor_session_id=prefetched_session.id).one()
            assert prefetched_turn.learner_response is None
            assert prefetched_turn.practice_question_json["variant_key"].endswith("v1")
            assert prefetched_turn.diagnosis_json["generation_origin"] == "prefetch"
            assert prefetched_turn.diagnosis_json["prefetch"]["state"] == "ready"
            assert prefetched_session.prefetch_source_session_id == session["tutor_session_id"]
        summary = db.query(EvaluationSummary).filter_by(participant_id=pid).order_by(EvaluationSummary.created_at.desc()).first()
        assert summary.learning_burden_json["tutor_session_count"] == 1
        assert summary.learning_burden_json["tutor_turn_count"] == 1
    finally:
        db.close()


def test_wrong_current_turn_keeps_prefetch_and_current_second_turn_uses_m3():
    pid = _create_participant_with_pretest()
    session, turn = _start_first_turn(pid)
    wait_for_prefetch_tasks()
    response = client.post(
        f"/api/tutor-turns/{turn['turn_id']}/respond",
        json={"selected_option_ids": _ids_for_labels(turn["practice_question"], ["A", "D", "G"])},
    )
    assert response.status_code == 200, response.text
    second = client.post(f"/api/tutor-sessions/{session['tutor_session_id']}/turns", json={})
    assert second.status_code == 200, second.text
    assert second.json()["turn_index"] == 2

    db = SessionLocal()
    try:
        multi_agent = _term_session(db, pid, "multi_agent")
        memory_process = _term_session(db, pid, "memory_process")
        assert multi_agent.prefetch_state == "ready"
        assert memory_process.prefetch_state == "ready"
        current_logs = [
            log for log in db.query(AICallLog).filter_by(purpose="generate_tutoring_turn").all()
            if log.request_payload.get("participant_id") == pid
            and (log.request_payload.get("term") or {}).get("slug") == "llm_knowledge"
        ]
        assert any(
            (log.request_payload.get("previous_learning_misconception") or {}).get("misconception_type") == "M3"
            for log in current_logs
        )
        current_turn = db.get(TutorTurn, turn["turn_id"])
        second_turn = db.get(TutorTurn, second.json()["turn_id"])
        assert second_turn.previous_teaching_strategy == current_turn.teaching_strategy
    finally:
        db.close()


def test_next_term_reuses_prefetched_turn_without_new_material_generation():
    pid = _create_participant_with_pretest()
    _, turn = _start_first_turn(pid)
    wait_for_prefetch_tasks()
    db = SessionLocal()
    try:
        prefetched_session = _term_session(db, pid, "multi_agent")
        prefetched_turn = db.query(TutorTurn).filter_by(tutor_session_id=prefetched_session.id).one()
        prefetched_turn_id = prefetched_turn.id
        before = db.query(AICallLog).filter(
            AICallLog.purpose == "generate_tutoring_turn",
            AICallLog.request_payload["participant_id"].as_string() == pid,
            AICallLog.request_payload["term"]["slug"].as_string() == "multi_agent",
        ).count()
    finally:
        db.close()

    answer = client.post(
        f"/api/tutor-turns/{turn['turn_id']}/respond",
        json={"selected_option_ids": _ids_for_labels(turn["practice_question"], ["A", "B", "C"])},
    )
    assert answer.status_code == 200, answer.text
    next_session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "multi_agent"})
    assert next_session.status_code == 200, next_session.text
    next_turn = client.post(f"/api/tutor-sessions/{next_session.json()['tutor_session_id']}/turns", json={})
    assert next_turn.status_code == 200, next_turn.text
    assert next_turn.json()["turn_id"] == prefetched_turn_id

    db = SessionLocal()
    try:
        after = db.query(AICallLog).filter(
            AICallLog.purpose == "generate_tutoring_turn",
            AICallLog.request_payload["participant_id"].as_string() == pid,
            AICallLog.request_payload["term"]["slug"].as_string() == "multi_agent",
        ).count()
        session = db.get(TutorSession, next_session.json()["tutor_session_id"])
        assert after == before
        assert session.prefetch_state == "consumed"
        assert db.get(TutorTurn, prefetched_turn_id).diagnosis_json["prefetch"]["reused"] is True
    finally:
        db.close()


def test_prefetch_failure_falls_back_to_normal_generation(monkeypatch: pytest.MonkeyPatch):
    original = experiment_service._generate_validated_tutoring_turn

    async def fail_prefetch(db, payload, *, forbidden_strings=None):
        audit = payload.get("_generation_audit") or {}
        if audit.get("origin") == "prefetch" and (payload.get("term") or {}).get("slug") == "multi_agent":
            raise RuntimeError("test prefetch failure")
        return await original(db, payload, forbidden_strings=forbidden_strings)

    monkeypatch.setattr(experiment_service, "_generate_validated_tutoring_turn", fail_prefetch)
    pid = _create_participant_with_pretest()
    _, first_turn = _start_first_turn(pid)
    wait_for_prefetch_tasks()

    db = SessionLocal()
    try:
        assert _term_session(db, pid, "multi_agent").prefetch_state == "failed"
    finally:
        db.close()

    answer = client.post(
        f"/api/tutor-turns/{first_turn['turn_id']}/respond",
        json={"selected_option_ids": _ids_for_labels(first_turn["practice_question"], ["A", "B", "C"])},
    )
    assert answer.status_code == 200, answer.text
    next_session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "multi_agent"}).json()
    next_turn = client.post(f"/api/tutor-sessions/{next_session['tutor_session_id']}/turns", json={})
    assert next_turn.status_code == 200, next_turn.text

    db = SessionLocal()
    try:
        fallback_session = db.get(TutorSession, next_session["tutor_session_id"])
        generated = db.get(TutorTurn, next_turn.json()["turn_id"])
        assert fallback_session.prefetch_state == "failed"
        assert generated.diagnosis_json["generation_origin"] == "interactive_fallback"

        # A synchronous fallback keeps this session active.  Cleanup for a
        # new round/experiment must not mistake it for an untouched prefetch.
        experiment_service.discard_unconsumed_prefetches(db, pid, reason="test_cleanup")
        db.commit()
        db.refresh(fallback_session)
        assert fallback_session.ended_at is None

        follow_up_answer = client.post(
            f"/api/tutor-turns/{generated.id}/respond",
            json={"selected_option_ids": _ids_for_labels(generated.practice_question_json, ["A", "D", "G"])},
        )
        assert follow_up_answer.status_code == 200, follow_up_answer.text
        follow_up = client.post(f"/api/tutor-sessions/{fallback_session.id}/turns", json={})
        assert follow_up.status_code == 200, follow_up.text
        follow_up_turn = db.get(TutorTurn, follow_up.json()["turn_id"])
        assert follow_up_turn.diagnosis_json["generation_origin"] == "same_session_prefetch"
        assert follow_up_turn.diagnosis_json["prefetch"]["state"] == "not_applicable"
    finally:
        db.close()


def test_reaching_next_term_during_prefetch_discards_worker_result(monkeypatch: pytest.MonkeyPatch):
    original = experiment_service._generate_validated_tutoring_turn
    started = threading.Event()

    async def delay_prefetch(db, payload, *, forbidden_strings=None):
        audit = payload.get("_generation_audit") or {}
        if audit.get("origin") == "prefetch" and (payload.get("term") or {}).get("slug") == "multi_agent":
            started.set()
            time.sleep(0.35)
        return await original(db, payload, forbidden_strings=forbidden_strings)

    monkeypatch.setattr(experiment_service, "_generate_validated_tutoring_turn", delay_prefetch)
    pid = _create_participant_with_pretest()
    _, first_turn = _start_first_turn(pid)
    assert started.wait(timeout=3)

    answer = client.post(
        f"/api/tutor-turns/{first_turn['turn_id']}/respond",
        json={"selected_option_ids": _ids_for_labels(first_turn["practice_question"], ["A", "B", "C"])},
    )
    assert answer.status_code == 200, answer.text
    next_session = client.post("/api/tutor-sessions", json={"participant_id": pid, "term_slug": "multi_agent"}).json()
    next_turn = client.post(f"/api/tutor-sessions/{next_session['tutor_session_id']}/turns", json={})
    assert next_turn.status_code == 200, next_turn.text

    wait_for_prefetch_tasks()
    db = SessionLocal()
    try:
        session = db.get(TutorSession, next_session["tutor_session_id"])
        generated = db.get(TutorTurn, next_turn.json()["turn_id"])
        assert session.prefetch_state == "discarded"
        assert generated.diagnosis_json["generation_origin"] == "interactive_fallback"
        assert db.query(TutorTurn).filter_by(tutor_session_id=session.id).count() == 1
    finally:
        db.close()


def test_give_up_discards_unused_prefetched_sessions():
    pid = _create_participant_with_pretest()
    _, _ = _start_first_turn(pid)
    wait_for_prefetch_tasks()
    result = client.post(f"/api/participants/{pid}/give-up-learning")
    assert result.status_code == 200, result.text

    db = SessionLocal()
    try:
        prefetched = (
            db.query(TutorSession)
            .filter_by(participant_id=pid)
            .filter(TutorSession.prefetch_source_session_id.is_not(None))
            .all()
        )
        assert prefetched
        assert all(session.prefetch_state == "discarded" for session in prefetched)
        assert all(session.ended_at is not None for session in prefetched)
    finally:
        db.close()


def test_give_up_marks_failed_prefetch_as_discarded(monkeypatch: pytest.MonkeyPatch):
    original = experiment_service._generate_validated_tutoring_turn

    async def fail_prefetch(db, payload, *, forbidden_strings=None):
        audit = payload.get("_generation_audit") or {}
        if audit.get("origin") == "prefetch" and (payload.get("term") or {}).get("slug") == "multi_agent":
            raise RuntimeError("test prefetch failure")
        return await original(db, payload, forbidden_strings=forbidden_strings)

    monkeypatch.setattr(experiment_service, "_generate_validated_tutoring_turn", fail_prefetch)
    pid = _create_participant_with_pretest()
    _start_first_turn(pid)
    wait_for_prefetch_tasks()

    result = client.post(f"/api/participants/{pid}/give-up-learning")
    assert result.status_code == 200, result.text

    db = SessionLocal()
    try:
        failed_session = _term_session(db, pid, "multi_agent")
        assert failed_session.prefetch_state == "discarded"
        assert failed_session.prefetch_error_code == "participant_session_closed"
        assert failed_session.ended_at is not None
    finally:
        db.close()
