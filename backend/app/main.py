from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.codex_app_server_backend import CodexAppServerBackend
from app.core.config import get_settings
from app.db.session import get_db, init_db
from app.seed.seed_questions import seed_database
from app.services.experiment import (
    admin_summary,
    create_participant,
    create_tutor_session,
    diagnose_pretest,
    export_csv,
    generate_tutor_turn,
    learning_targets,
    question_payloads,
    recalculate_evaluation,
    respond_tutor_turn,
    save_survey,
    score_phase,
    submit_attempt,
)


settings = get_settings()


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
    group_condition: str | None = None
    assignment_method: str = "manual"
    consent_checked: bool = True


class SurveyPayload(BaseModel):
    phase: str = "pre_survey"
    ai_experience_level: int | None = None
    programming_experience_level: int | None = None
    llm_usage_level: int | None = None
    self_rated_ai_knowledge: int | None = None
    term_confidences: dict | None = None
    usability_rating: int | None = None
    helpfulness_rating: int | None = None
    perceived_hint_amount: int | None = None
    free_comment: str | None = None


class AttemptPayload(BaseModel):
    participant_id: str
    question_id: str
    phase: str | None = None
    selected_option_id: str | None = None
    free_text_answer: str | None = None
    reason_text: str | None = None
    confidence: int | None = None
    response_time_sec: float | None = None


class TutorSessionCreate(BaseModel):
    participant_id: str
    term_slug: str


class TutorTurnRespond(BaseModel):
    learner_response: str
    confidence: int | None = None


class AILoginStart(BaseModel):
    type: str = "chatgpt"


class AILoginCancel(BaseModel):
    login_id: str


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/seed")
def seed(db: Session = Depends(get_db)) -> dict:
    seed_database(db)
    return {"seeded": True}


@app.post("/api/participants")
def api_create_participant(payload: ParticipantCreate, db: Session = Depends(get_db)) -> dict:
    participant = create_participant(db, payload.group_condition, payload.assignment_method, payload.consent_checked)
    return {
        "participant_id": participant.id,
        "display_code": participant.display_code,
        "group_condition": participant.group_condition,
        "current_step": participant.current_step,
    }


@app.get("/api/participants/{participant_id}/current-step")
def current_step(participant_id: str, db: Session = Depends(get_db)) -> dict:
    from app.services.experiment import get_participant

    participant = get_participant(db, participant_id)
    mapping = {
        "pre_survey": "/survey/pre",
        "pretest": "/pretest",
        "learning_targets": "/learning-targets",
        "l0_check": "/l0-check",
        "transfer": "/transfer-test",
        "post_survey": "/survey/post",
        "finish": "/finish",
    }
    return {"step": participant.current_step, "next_url": mapping.get(participant.current_step, "/start")}


@app.post("/api/participants/{participant_id}/survey")
def api_save_survey(participant_id: str, payload: SurveyPayload, db: Session = Depends(get_db)) -> dict:
    save_survey(db, participant_id, payload.model_dump())
    return {"saved": True, "next_step": "pretest" if payload.phase == "pre_survey" else "finish"}


@app.get("/api/experiment/{participant_id}/pretest")
def get_pretest(participant_id: str, db: Session = Depends(get_db)) -> dict:
    return {"phase": "pretest", "questions": question_payloads(db, participant_id, "pretest")}


@app.get("/api/experiment/{participant_id}/retest")
def get_retest(participant_id: str, db: Session = Depends(get_db)) -> dict:
    return {"phase": "retest", "questions": question_payloads(db, participant_id, "retest")}


@app.get("/api/experiment/{participant_id}/l0-check")
def get_l0(participant_id: str, db: Session = Depends(get_db)) -> dict:
    return {"phase": "l0_check", "questions": question_payloads(db, participant_id, "l0_check")}


@app.get("/api/experiment/{participant_id}/transfer-test")
def get_transfer(participant_id: str, db: Session = Depends(get_db)) -> dict:
    return {"phase": "transfer", "questions": question_payloads(db, participant_id, "transfer")}


@app.post("/api/attempts")
def api_submit_attempt(payload: AttemptPayload, idempotency_key: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict:
    attempt = submit_attempt(db, payload.model_dump(), idempotency_key)
    return {"attempt_id": attempt.id, "saved": True, "is_complete_for_question": True}


@app.post("/api/participants/{participant_id}/diagnose-pretest")
async def api_diagnose_pretest(participant_id: str, db: Session = Depends(get_db)) -> dict:
    count = await diagnose_pretest(db, participant_id)
    return {"status": "completed", "learning_target_count": count, "next_step": "learning_targets"}


@app.get("/api/participants/{participant_id}/learning-targets")
def api_learning_targets(participant_id: str, db: Session = Depends(get_db)) -> dict:
    return {"targets": learning_targets(db, participant_id)}


@app.post("/api/tutor-sessions")
def api_create_tutor_session(payload: TutorSessionCreate, db: Session = Depends(get_db)) -> dict:
    session = create_tutor_session(db, payload.participant_id, payload.term_slug)
    return {"tutor_session_id": session.id, "session_index": session.session_index, "max_turns": settings.max_turns_per_term}


@app.post("/api/tutor-sessions/{session_id}/turns")
async def api_generate_tutor_turn(session_id: str, db: Session = Depends(get_db)) -> dict:
    turn = await generate_tutor_turn(db, session_id)
    return {
        "turn_id": turn.id,
        "tutor_message": turn.tutor_message,
        "learner_prompt": turn.learner_prompt,
        "practice_question": turn.practice_question_json,
        "requires_learner_response": True,
    }


@app.post("/api/tutor-turns/{turn_id}/respond")
async def api_respond_tutor_turn(turn_id: str, payload: TutorTurnRespond, db: Session = Depends(get_db)) -> dict:
    return await respond_tutor_turn(db, turn_id, payload.model_dump())


@app.post("/api/participants/{participant_id}/score-retest")
async def api_score_retest(participant_id: str, db: Session = Depends(get_db)) -> dict:
    return await score_phase(db, participant_id, "retest")


@app.post("/api/participants/{participant_id}/score-l0-check")
async def api_score_l0(participant_id: str, db: Session = Depends(get_db)) -> dict:
    return await score_phase(db, participant_id, "l0_check")


@app.post("/api/participants/{participant_id}/score-transfer-test")
async def api_score_transfer(participant_id: str, db: Session = Depends(get_db)) -> dict:
    return await score_phase(db, participant_id, "transfer")


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
    return {
        "participants": [
            {
                "participant_id": row.id,
                "display_code": row.display_code,
                "group_condition": row.group_condition,
                "current_step": row.current_step,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            }
            for row in rows
        ]
    }


@app.get("/api/admin/export/{name}.csv")
def api_export_csv(name: str, db: Session = Depends(get_db)):
    path = export_csv(db, name)
    return FileResponse(path, media_type="text/csv", filename=path.name)


@app.get("/api/admin/ai/status")
async def api_ai_status() -> dict:
    if settings.ai_backend == "codex_app_server":
        status = await CodexAppServerBackend().status()
        return {"ai_backend": settings.ai_backend, **status}
    return {"ai_backend": "mock", "app_server_reachable": None, "logged_in": None, "account_label": "MockAIBackend (test only)", "last_error": None}


@app.post("/api/admin/ai/login/start")
async def api_ai_login_start(payload: AILoginStart) -> dict:
    return await CodexAppServerBackend().start_login(payload.type)


@app.post("/api/admin/ai/login/cancel")
async def api_ai_login_cancel(payload: AILoginCancel) -> dict:
    return await CodexAppServerBackend().cancel_login(payload.login_id)


@app.post("/api/admin/ai/logout")
async def api_ai_logout() -> dict:
    return await CodexAppServerBackend().logout()
