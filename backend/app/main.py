from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from datetime import datetime

from app.models import Term, TutorSession, TutorTurn

from app.ai.codex_app_server_backend import CodexAppServerBackend, CodexAppServerError
from app.core.config import get_settings
from app.core.runtime_config import (
    ALLOWED_REASONING_EFFORTS,
    current_reasoning_effort,
    set_reasoning_effort,
)
from app.db.session import get_db, init_db
from app.seed.seed_questions import seed_database
from app.services.experiment import (
    admin_summary,
    admin_logs_overview,
    create_participant,
    delete_participant,
    create_tutor_session,
    export_overview_logs_excel_csv,
    export_overview_logs_csv,
    export_participant_logs_excel_csv,
    export_participant_logs_csv,
    diagnose_pretest,
    export_csv,
    generate_tutor_turn,
    get_participant,
    give_up_experiment,
    give_up_learning,
    learning_targets,
    latest_test_results,
    participant_logs,
    participant_give_up_counts,
    pretest_results,
    question_payloads,
    recalculate_evaluation,
    respond_tutor_turn,
    score_phase,
    submit_attempt,
    submit_survey,
)
from app.services.idempotency import run_idempotent
from app.services.tutor_prefetch import tutor_prefetch_registry
from app.services.prefetch import prefetch_coordinator, schedule_prefetch


settings = get_settings()


_PUBLIC_PRACTICE_QUESTION_FIELDS = {
    "body",
    "question_type",
    "options",
    "items",
    "selection_mode",
    "min_selections",
    "max_selections",
    "variant_key",
    "learning_variant_index",
}
_PUBLIC_PRACTICE_ITEM_FIELDS = {
    "component_term",
    "material",
    "body",
    "question_type",
    "options",
    "selection_mode",
    "min_selections",
    "max_selections",
    "variant_key",
    "learning_variant_index",
}
_PRIVATE_TURN_RESPONSE_FIELDS = {
    "initial_misconception_type",
    "misconception_type",
    "latest_learning_misconception_type",
    "latest_learning_misconception_reason",
    "session_misconception_history",
    "teaching_strategy",
}


def _public_practice_question(question: object) -> dict | None:
    if not isinstance(question, dict):
        return None

    def public_item(item: object, allowed_fields: set[str]) -> dict:
        if not isinstance(item, dict):
            return {}
        result = {key: value for key, value in item.items() if key in allowed_fields and key != "options"}
        options = item.get("options")
        if isinstance(options, list):
            result["options"] = [
                {key: option[key] for key in ("option_id", "label", "body") if key in option}
                for option in options
                if isinstance(option, dict)
            ]
        return result

    result = public_item(question, _PUBLIC_PRACTICE_QUESTION_FIELDS)
    items = question.get("items")
    if isinstance(items, list):
        result["items"] = [public_item(item, _PUBLIC_PRACTICE_ITEM_FIELDS) for item in items]
    return result


def _reasoning_effort_status() -> dict:
    return {
        "reasoning_effort": current_reasoning_effort(),
        "allowed_reasoning_efforts": list(ALLOWED_REASONING_EFFORTS),
        "can_change_reasoning_effort": True,
        "reasoning_effort_change_block_reason": None,
        "reasoning_effort_applies": settings.ai_backend == "codex_app_server",
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    db = next(get_db())
    try:
        seed_database(db)
    finally:
        db.close()
    try:
        yield
    finally:
        prefetch_coordinator.shutdown()


app = FastAPI(title="Learning Log AI Tutor", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ParticipantCreate(BaseModel):
    assignment_code: str | None = None
    consent_checked: bool = False


class AttemptPayload(BaseModel):
    participant_id: str
    question_id: str
    phase: str | None = None
    selected_option_id: str | None = None
    selected_option_ids: list[str] | None = None
    free_text_answer: str | None = None
    reason_text: str | None = None
    response_time_sec: float | None = None
    question_shown_at: datetime | None = None
    answered_at: datetime | None = None


class TutorSessionCreate(BaseModel):
    participant_id: str
    term_slug: str


class TutorTurnRespond(BaseModel):
    learner_response: str = ""
    selected_option_id: str | None = None
    selected_option_ids: list[str] | None = None
    selected_item_option_ids: dict[str, str] | None = None
    response_time_sec: float | None = None
    question_shown_at: datetime | None = None
    answered_at: datetime | None = None


class SurveyPayload(BaseModel):
    ai_experience_level: int = Field(ge=1, le=5)
    programming_experience_level: int = Field(ge=1, le=5)
    llm_usage_level: int = Field(ge=1, le=5)
    self_rated_ai_knowledge: int = Field(ge=1, le=5)
    term_confidences: dict[str, int] | None = None
    usability_rating: int = Field(ge=1, le=5)
    helpfulness_rating: int = Field(ge=1, le=5)
    perceived_hint_amount: int = Field(ge=1, le=5)
    free_comment: str | None = None


class AILoginStart(BaseModel):
    type: str = "chatgpt"


class AILoginCancel(BaseModel):
    login_id: str


class ReasoningEffortPayload(BaseModel):
    reasoning_effort: Literal["low", "medium", "high"]


DATABASE_UNAVAILABLE_DETAIL = "データベースに接続できません。管理者に確認してください。"


def _raise_database_unavailable(db: Session, exc: OperationalError) -> None:
    db.rollback()
    raise HTTPException(status_code=503, detail=DATABASE_UNAVAILABLE_DETAIL) from exc


@app.get("/api/health")
def health(db: Session = Depends(get_db)) -> dict:
    try:
        db.execute(text("SELECT 1"))
    except OperationalError as exc:
        _raise_database_unavailable(db, exc)
    return {"status": "ok"}


@app.post("/api/seed")
def seed(db: Session = Depends(get_db)) -> dict:
    seed_database(db)
    return {"seeded": True}


@app.post("/api/participants")
async def api_create_participant(
    payload: ParticipantCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    def operation() -> dict:
        try:
            participant = create_participant(db, payload.assignment_code, payload.consent_checked)
        except OperationalError as exc:
            _raise_database_unavailable(db, exc)
        return {
            "participant_id": participant.id,
            "display_code": participant.display_code,
            "current_step": participant.current_step,
        }

    try:
        return await run_idempotent(
            db,
            scope="participant:create",
            key=idempotency_key,
            participant_id=None,
            request_data=payload.model_dump(mode="json"),
            operation=operation,
        )
    except OperationalError as exc:
        _raise_database_unavailable(db, exc)


@app.get("/api/participants/{participant_id}/current-step")
def current_step(participant_id: str, db: Session = Depends(get_db)) -> dict:
    participant = get_participant(db, participant_id)
    mapping = {
        "pretest": "/pretest",
        "learning_targets": "/learning-targets",
        "retest": "/retest",
        "final_test": "/final-test",
        "survey": "/survey",
        "l0_check": "/l0-check",
        "finish": "/finish",
    }
    return {"step": participant.current_step, "next_url": mapping.get(participant.current_step, "/start")}


@app.get("/api/experiment/{participant_id}/pretest")
def get_pretest(participant_id: str, db: Session = Depends(get_db)) -> dict:
    return {"phase": "pretest", "questions": question_payloads(db, participant_id, "pretest")}


@app.get("/api/experiment/{participant_id}/retest")
def get_retest(participant_id: str, db: Session = Depends(get_db)) -> dict:
    return {"phase": "retest", "questions": question_payloads(db, participant_id, "retest")}


@app.get("/api/experiment/{participant_id}/l0-check")
def get_l0(participant_id: str, db: Session = Depends(get_db)) -> dict:
    return {"phase": "l0_check", "questions": question_payloads(db, participant_id, "l0_check")}


@app.get("/api/experiment/{participant_id}/final-test")
def get_final_test(participant_id: str, db: Session = Depends(get_db)) -> dict:
    return {"phase": "final_test", "questions": question_payloads(db, participant_id, "final_test")}


@app.post("/api/attempts")
async def api_submit_attempt(
    payload: AttemptPayload,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    def operation() -> dict:
        attempt = submit_attempt(db, payload.model_dump(), idempotency_key)
        return {"attempt_id": attempt.id, "saved": True, "is_complete_for_question": True}

    return await run_idempotent(
        db,
        scope=f"attempt:{payload.participant_id}:{payload.question_id}:{payload.phase or 'auto'}",
        key=idempotency_key,
        participant_id=payload.participant_id,
        request_data=payload.model_dump(mode="json"),
        operation=operation,
    )


@app.post("/api/participants/{participant_id}/diagnose-pretest")
async def api_diagnose_pretest(
    participant_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    async def operation() -> dict:
        count = await diagnose_pretest(db, participant_id)
        next_step = "learning_targets" if count else "final_test"
        return {"status": "completed", "learning_target_count": count, "next_step": next_step, "next_url": "/learning-targets" if count else "/final-test"}

    return await run_idempotent(
        db,
        scope=f"diagnose_pretest:{participant_id}",
        key=idempotency_key,
        participant_id=participant_id,
        request_data={"participant_id": participant_id},
        operation=operation,
    )


@app.get("/api/participants/{participant_id}/learning-targets")
def api_learning_targets(participant_id: str, db: Session = Depends(get_db)) -> dict:
    participant = get_participant(db, participant_id)
    return {
        "current_step": participant.current_step,
        "targets": learning_targets(db, participant_id),
        "pretest_results": pretest_results(db, participant_id),
        "test_results": latest_test_results(db, participant_id),
    }


@app.post("/api/participants/{participant_id}/give-up-learning")
async def api_give_up_learning(
    participant_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    await tutor_prefetch_registry.cancel_for_participant(participant_id)
    return await run_idempotent(
        db,
        scope=f"give_up_learning:{participant_id}",
        key=idempotency_key,
        participant_id=participant_id,
        request_data={"participant_id": participant_id},
        operation=lambda: give_up_learning(db, participant_id),
    )


@app.post("/api/participants/{participant_id}/give-up")
async def api_give_up_experiment(
    participant_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    await tutor_prefetch_registry.cancel_for_participant(participant_id)
    return await run_idempotent(
        db,
        scope=f"give_up_experiment:{participant_id}",
        key=idempotency_key,
        participant_id=participant_id,
        request_data={"participant_id": participant_id},
        operation=lambda: give_up_experiment(db, participant_id),
    )


@app.post("/api/participants/{participant_id}/survey")
async def api_submit_survey(
    participant_id: str,
    payload: SurveyPayload,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    return await run_idempotent(
        db,
        scope=f"survey:{participant_id}",
        key=idempotency_key,
        participant_id=participant_id,
        request_data=payload.model_dump(mode="json"),
        operation=lambda: submit_survey(db, participant_id, payload.model_dump()),
    )


@app.post("/api/tutor-sessions")
async def api_create_tutor_session(
    payload: TutorSessionCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    def operation() -> dict:
        session = create_tutor_session(db, payload.participant_id, payload.term_slug)
        return {"tutor_session_id": session.id, "session_index": session.session_index, "max_turns": settings.max_turns_per_term}

    return await run_idempotent(
        db,
        scope=f"tutor_session:{payload.participant_id}:{payload.term_slug}",
        key=idempotency_key,
        participant_id=payload.participant_id,
        request_data=payload.model_dump(mode="json"),
        operation=operation,
    )


@app.post("/api/tutor-sessions/{session_id}/turns")
async def api_generate_tutor_turn(
    session_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    # Wait before touching the request-scoped SQLAlchemy session. The worker
    # may be waiting on an external AI call for several seconds.
    await tutor_prefetch_registry.wait_for(session_id)
    session = db.get(TutorSession, session_id)
    participant_id = session.participant_id if session else None

    async def operation() -> dict:
        turn = await generate_tutor_turn(db, session_id)
        current_session = db.get(TutorSession, session_id)
        term = db.get(Term, current_session.term_id) if current_session else None
        stage_meta = (turn.practice_question_json or {}).get("stage_meta") or {}
        return {
            "turn_id": turn.id,
            "term_slug": term.slug if term else None,
            "term_label": term.label if term else None,
            "tutor_message": turn.tutor_message,
            "learner_prompt": turn.learner_prompt,
            "practice_question": _public_practice_question(turn.practice_question_json),
            "requires_learner_response": True,
            "turn_index": turn.turn_index,
            "max_turns": settings.max_turns_per_term,
            "learning_stage": stage_meta.get("learning_stage"),
            "learning_stage_label": stage_meta.get("learning_stage_label"),
            "component_term": stage_meta.get("component_term"),
            "component_index": stage_meta.get("component_index"),
            "component_total": stage_meta.get("component_total"),
            "stage_completed": False,
            "scaffolding_level": turn.scaffolding_level,
        }

    response = await run_idempotent(
        db,
        scope=f"tutor_turn_generate:{session_id}",
        key=idempotency_key,
        participant_id=participant_id,
        request_data={"session_id": session_id},
        operation=operation,
    )
    if isinstance(response, tuple) and len(response) == 1 and isinstance(response[0], dict):
        response = response[0]
    if isinstance(response, dict):
        response = {
            key: value
            for key, value in response.items()
            if key not in _PRIVATE_TURN_RESPONSE_FIELDS
        }
        response["practice_question"] = _public_practice_question(response.get("practice_question"))
    # Schedule only after the interactive response transaction has completed.
    # A reused prefetched turn carries its origin in the private diagnosis
    # audit and must not start another prefetch batch.
    if participant_id and isinstance(response, dict) and response.get("turn_index") == 1:
        turn = db.get(TutorTurn, response.get("turn_id"))
        origin = (turn.diagnosis_json or {}).get("generation_origin") if turn else None
        if origin in {"interactive", "interactive_fallback"}:
            schedule_prefetch(participant_id, session_id)
    return response


@app.post("/api/tutor-turns/{turn_id}/respond")
async def api_respond_tutor_turn(
    turn_id: str,
    payload: TutorTurnRespond,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    turn = db.get(TutorTurn, turn_id)
    session = db.get(TutorSession, turn.tutor_session_id) if turn else None
    participant_id = session.participant_id if session else None
    prefetch_handle = (
        tutor_prefetch_registry.prepare(session.id, participant_id)
        if session is not None and participant_id is not None
        else None
    )
    try:
        result = await run_idempotent(
            db,
            scope=f"tutor_turn_respond:{turn_id}",
            key=idempotency_key,
            participant_id=participant_id,
            request_data=payload.model_dump(mode="json"),
            operation=lambda: respond_tutor_turn(
                db,
                turn_id,
                payload.model_dump(),
                prefetch_handle=prefetch_handle,
            ),
        )
    except BaseException:
        if prefetch_handle is not None:
            prefetch_handle.abort()
        raise
    else:
        if prefetch_handle is not None:
            prefetch_handle.confirm()
        return result


@app.post("/api/participants/{participant_id}/score-retest")
async def api_score_retest(
    participant_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    return await run_idempotent(
        db,
        scope=f"score:{participant_id}:retest",
        key=idempotency_key,
        participant_id=participant_id,
        request_data={"participant_id": participant_id, "phase": "retest"},
        operation=lambda: score_phase(db, participant_id, "retest"),
    )


@app.post("/api/participants/{participant_id}/score-l0-check")
async def api_score_l0(
    participant_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    return await run_idempotent(
        db,
        scope=f"score:{participant_id}:l0_check",
        key=idempotency_key,
        participant_id=participant_id,
        request_data={"participant_id": participant_id, "phase": "l0_check"},
        operation=lambda: score_phase(db, participant_id, "l0_check"),
    )


@app.post("/api/participants/{participant_id}/score-final-test")
async def api_score_final_test(
    participant_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    return await run_idempotent(
        db,
        scope=f"score:{participant_id}:final_test",
        key=idempotency_key,
        participant_id=participant_id,
        request_data={"participant_id": participant_id, "phase": "final_test"},
        operation=lambda: score_phase(db, participant_id, "final_test"),
    )


@app.post("/api/participants/{participant_id}/evaluation-summary/recalculate")
def api_recalculate(participant_id: str, db: Session = Depends(get_db)) -> dict:
    summary = recalculate_evaluation(db, participant_id)
    return {"status": "completed", "evaluation_summary_id": summary.id}


@app.get("/api/admin/evaluation-summary")
def api_admin_summary(db: Session = Depends(get_db)) -> dict:
    return admin_summary(db)


@app.get("/api/admin/participants")
def api_admin_participants(db: Session = Depends(get_db)) -> dict:
    from app.models import Participant

    rows = db.query(Participant).order_by(Participant.created_at.desc()).all()
    give_up_counts = participant_give_up_counts(db, [row.id for row in rows])
    return {
        "participants": [
            {
                "participant_id": row.id,
                "display_code": row.display_code,
                "group_condition": row.group_condition,
                "current_step": row.current_step,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "completion_reason": row.completion_reason,
                "give_up_learning_count": give_up_counts.get((row.id, "give_up_learning"), 0),
                "give_up_experiment_count": give_up_counts.get((row.id, "give_up_experiment"), 0),
            }
            for row in rows
        ]
    }


@app.delete("/api/admin/participants/{participant_id}")
def api_delete_admin_participant(participant_id: str, db: Session = Depends(get_db)) -> dict:
    return delete_participant(db, participant_id)


@app.get("/api/admin/logs/overview")
def api_admin_logs_overview(db: Session = Depends(get_db)) -> dict:
    return admin_logs_overview(db)


@app.get("/api/admin/logs/overview.csv")
def api_admin_logs_overview_csv(db: Session = Depends(get_db)):
    path = export_overview_logs_csv(db)
    return FileResponse(path, media_type="text/csv", filename=path.name)


@app.get("/api/admin/logs/overview_excel.csv")
def api_admin_logs_overview_excel_csv(db: Session = Depends(get_db)):
    path = export_overview_logs_excel_csv(db)
    return FileResponse(path, media_type="text/csv", filename=path.name)


@app.get("/api/admin/participants/{participant_id}/logs")
def api_admin_participant_logs(participant_id: str, db: Session = Depends(get_db)) -> dict:
    return participant_logs(db, participant_id)


@app.get("/api/admin/participants/{participant_id}/logs.csv")
def api_admin_participant_logs_csv(participant_id: str, db: Session = Depends(get_db)):
    path = export_participant_logs_csv(db, participant_id)
    return FileResponse(path, media_type="text/csv", filename=path.name)


@app.get("/api/admin/participants/{participant_id}/logs_excel.csv")
def api_admin_participant_logs_excel_csv(participant_id: str, db: Session = Depends(get_db)):
    path = export_participant_logs_excel_csv(db, participant_id)
    return FileResponse(path, media_type="text/csv", filename=path.name)


@app.get("/api/admin/export/{name}.csv")
def api_export_csv(name: str, db: Session = Depends(get_db)):
    path = export_csv(db, name)
    return FileResponse(path, media_type="text/csv", filename=path.name)


@app.get("/api/admin/ai/status")
async def api_ai_status() -> dict:
    reasoning_status = _reasoning_effort_status()
    if settings.ai_backend == "codex_app_server":
        status = await CodexAppServerBackend().status()
        return {
            "ai_backend": settings.ai_backend,
            "model": settings.codex_model,
            **status,
            **reasoning_status,
        }
    return {
        "ai_backend": "mock",
        "model": settings.codex_model,
        "app_server_reachable": None,
        "logged_in": None,
        "account_label": "MockAIBackend (test only)",
        "last_error": None,
        **reasoning_status,
    }


@app.post("/api/admin/ai/reasoning-effort")
def api_set_reasoning_effort(payload: ReasoningEffortPayload) -> dict:
    set_reasoning_effort(payload.reasoning_effort)
    return {
        "ai_backend": "codex_app_server" if settings.ai_backend == "codex_app_server" else "mock",
        "model": settings.codex_model,
        **_reasoning_effort_status(),
    }


@app.post("/api/admin/ai/login/start")
async def api_ai_login_start(payload: AILoginStart) -> dict:
    try:
        return await CodexAppServerBackend().start_login(payload.type)
    except CodexAppServerError as exc:
        raise HTTPException(status_code=503, detail={"error_code": exc.code, "message": exc.user_message, "detail": exc.detail}) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"error_code": "app_server_unreachable", "message": "Codex app-serverに接続できません。", "detail": str(exc)}) from exc


@app.post("/api/admin/ai/login/cancel")
async def api_ai_login_cancel(payload: AILoginCancel) -> dict:
    try:
        return await CodexAppServerBackend().cancel_login(payload.login_id)
    except CodexAppServerError as exc:
        raise HTTPException(status_code=503, detail={"error_code": exc.code, "message": exc.user_message, "detail": exc.detail}) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"error_code": "app_server_unreachable", "message": "Codex app-serverに接続できません。", "detail": str(exc)}) from exc


@app.post("/api/admin/ai/logout")
async def api_ai_logout() -> dict:
    try:
        return await CodexAppServerBackend().logout()
    except CodexAppServerError as exc:
        raise HTTPException(status_code=503, detail={"error_code": exc.code, "message": exc.user_message, "detail": exc.detail}) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"error_code": "app_server_unreachable", "message": "Codex app-serverに接続できません。", "detail": str(exc)}) from exc
