from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from datetime import datetime

from app.models import LearnerState, Term, TutorSession, TutorTurn

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
    latest_learning_misconception,
    learning_targets,
    latest_test_results,
    participant_logs,
    participant_give_up_counts,
    pretest_results,
    question_payloads,
    recalculate_evaluation,
    respond_tutor_turn,
    score_phase,
    session_misconception_history,
    submit_attempt,
    submit_survey,
)
from app.services.idempotency import run_idempotent


settings = get_settings()


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
    yield


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


@app.get("/api/health")
def health() -> dict:
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
        participant = create_participant(db, payload.assignment_code, payload.consent_checked)
        return {
            "participant_id": participant.id,
            "display_code": participant.display_code,
            "current_step": participant.current_step,
        }

    return await run_idempotent(
        db,
        scope="participant:create",
        key=idempotency_key,
        participant_id=None,
        request_data=payload.model_dump(mode="json"),
        operation=operation,
    )


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
    session = db.get(TutorSession, session_id)
    participant_id = session.participant_id if session else None

    async def operation() -> dict:
        turn = await generate_tutor_turn(db, session_id)
        current_session = db.get(TutorSession, session_id)
        term = db.get(Term, current_session.term_id) if current_session else None
        state = db.query(LearnerState).filter_by(participant_id=current_session.participant_id, term_id=current_session.term_id).one() if current_session else None
        stage_meta = (turn.practice_question_json or {}).get("stage_meta") or {}
        history = session_misconception_history(db, session_id)
        latest_learning = latest_learning_misconception(db, session_id)
        return {
            "turn_id": turn.id,
            "term_slug": term.slug if term else None,
            "term_label": term.label if term else None,
            "tutor_message": turn.tutor_message,
            "learner_prompt": turn.learner_prompt,
            "practice_question": turn.practice_question_json,
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
            "initial_misconception_type": state.primary_misconception if state else None,
            "misconception_type": state.primary_misconception if state else None,
            "latest_learning_misconception_type": latest_learning.get("misconception_type") if latest_learning else None,
            "latest_learning_misconception_reason": latest_learning.get("reason") if latest_learning else None,
            "session_misconception_history": history,
            "teaching_strategy": turn.teaching_strategy,
        }

    return await run_idempotent(
        db,
        scope=f"tutor_turn_generate:{session_id}",
        key=idempotency_key,
        participant_id=participant_id,
        request_data={"session_id": session_id},
        operation=operation,
    )


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
    return await run_idempotent(
        db,
        scope=f"tutor_turn_respond:{turn_id}",
        key=idempotency_key,
        participant_id=participant_id,
        request_data=payload.model_dump(mode="json"),
        operation=lambda: respond_tutor_turn(db, turn_id, payload.model_dump()),
    )


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
