from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, SecretStr, Field
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from datetime import datetime

from app.models import Participant, Term, TutorSession, TutorTurn
from app.services import pretest_display
from app.services import question_review_display, first_question_only
from app.services import learning_material_glossary_mode
from pydantic import StrictBool

from app.ai.codex_app_server_backend import CodexAppServerBackend, CodexAppServerError
from app.core.config import get_settings
from app.core.admin_auth import require_admin, login as admin_login, logout as admin_logout
from app.core.experiment_spec import MAX_LEARNING_CONFIRMATION_ATTEMPTS, MAX_POST_PRETEST_TESTS, assert_current_experiment, can_resume
from app.core.runtime_config import (
    ALLOWED_MODELS,
    ALLOWED_REASONING_EFFORTS,
    STUDY_MODEL,
    STUDY_REASONING_EFFORT,
    current_ai_runtime_settings,
    set_model,
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
    acknowledge_question_review,
    experiment_progress,
    export_overview_logs_excel_csv,
    export_overview_logs_csv,
    export_overview_logs_xlsx,
    export_hypothesis_metrics_xlsx,
    export_participant_logs_excel_csv,
    export_participant_logs_csv,
    export_participant_logs_xlsx,
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
    pending_question_review,
    post_pretest_test_progress,
    question_payloads,
    effective_test_page_mode,
    recalculate_evaluation,
    respond_tutor_turn,
    score_phase,
    submit_attempt,
    submit_test_term_page,
    submit_presurvey,
    submit_survey,
)
from app.services.idempotency import normalize_idempotency_key, registration_key_was_deleted, run_idempotent
from app.services.identity_mapping_cleanup import (
    COMPLETE as IDENTITY_MAPPING_CLEANUP_COMPLETE,
    PENDING as IDENTITY_MAPPING_CLEANUP_PENDING,
    complete_identity_mapping_cleanup,
    deletion_response,
    participant_deletion_event,
    recover_pending_identity_mapping_cleanups,
)
from app.services.option_order import current_option_order_mode, save_option_order_mode
from app.services.learning_glossary import load_learning_glossary, public_glossary
from app.services import identity_mapping
from app.services.research_protocol import PresurveyPayload, SurveyPayload, presurvey_context, survey_context, record_material_view
from app.services.tutor_prefetch import tutor_prefetch_registry
from app.services.prefetch import prefetch_coordinator, schedule_prefetch


settings = get_settings()
logger = logging.getLogger(__name__)


_PUBLIC_PRACTICE_QUESTION_FIELDS = {
    "body",
    "question_type",
    "options",
    "selection_mode",
    "min_selections",
    "max_selections",
    "variant_key",
    "learning_variant_index",
    "questions",
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
                {
                    "option_id": option.get("option_id"),
                    "label": option.get("label"),
                    "body": option.get("body"),
                    "exclusive": bool(option.get("exclusive", option.get("body") == "わからない。")),
                }
                for option in options
                if isinstance(option, dict)
            ]
        if isinstance(item.get("questions"), list):
            result["questions"] = [public_item(group, {"question_id", "body", "options"}) for group in item["questions"]]
        return result

    return public_item(question, _PUBLIC_PRACTICE_QUESTION_FIELDS)


def _reasoning_effort_status() -> dict:
    model, effort = current_ai_runtime_settings()
    study_settings_match = effort == STUDY_REASONING_EFFORT and model == STUDY_MODEL
    return {
        "model": model,
        "allowed_models": list(ALLOWED_MODELS),
        "can_change_model": settings.ai_backend == "codex_app_server",
        "model_applies": settings.ai_backend == "codex_app_server",
        "reasoning_effort": effort,
        "allowed_reasoning_efforts": list(ALLOWED_REASONING_EFFORTS),
        "can_change_reasoning_effort": True,
        "reasoning_effort_change_block_reason": None,
        "reasoning_effort_applies": settings.ai_backend == "codex_app_server",
        "study_settings_match": study_settings_match,
        "study_settings_reference": {
            "model": STUDY_MODEL,
            "reasoning_effort": STUDY_REASONING_EFFORT,
        },
        "study_settings_warning": None if study_settings_match else "アプリ標準条件（gpt-6-luna / low）と一致していません。計画書原本のモデル記載とは区別してください。",
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_learning_glossary()
    init_db()
    db = next(get_db())
    try:
        seed_database(db)
        pending_cleanups = recover_pending_identity_mapping_cleanups(db)
        if pending_cleanups:
            logger.warning("%s participant identity mapping cleanup(s) remain pending", pending_cleanups)
    finally:
        db.close()
    try:
        yield
    finally:
        prefetch_coordinator.shutdown()


async def guard_current_mutation(request: Request, db: Session = Depends(get_db)) -> None:
    """Reject historical writes before body validation, replay, or prefetch."""
    if request.method != "POST":
        return
    path = request.url.path
    if path.startswith("/api/admin/") or path in {"/api/participants", "/api/seed"}:
        return
    participant_id = request.path_params.get("participant_id")
    if path in {"/api/attempts", "/api/tutor-sessions"}:
        try:
            body = await request.json()
        except ValueError:
            return
        participant_id = body.get("participant_id") if isinstance(body, dict) else None
    elif request.path_params.get("session_id"):
        session = db.get(TutorSession, request.path_params["session_id"])
        participant_id = session.participant_id if session else None
    elif request.path_params.get("turn_id"):
        turn = db.get(TutorTurn, request.path_params["turn_id"])
        session = db.get(TutorSession, turn.tutor_session_id) if turn else None
        participant_id = session.participant_id if session else None
    if participant_id:
        assert_current_experiment(get_participant(db, participant_id))


app = FastAPI(title="Learning Log AI Tutor", lifespan=lifespan, dependencies=[Depends(require_admin), Depends(guard_current_mutation)])
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def prevent_identifier_caching(request: Request, call_next):
    response = await call_next(request)
    if request.url.path in {"/api/participants", "/api/registrations", "/api/seed"} or request.url.path.startswith("/api/admin/"):
        response.headers["Cache-Control"] = "no-store"
    return response


class AdminLoginPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: SecretStr = Field(min_length=1, max_length=256)


@app.post("/api/admin/auth/login")
def api_admin_login(payload: AdminLoginPayload, request: Request, response: Response) -> dict:
    admin_login(payload.password.get_secret_value(), request, response)
    return {"authenticated": True}


@app.post("/api/admin/auth/logout")
def api_admin_logout(request: Request, response: Response) -> dict:
    admin_logout(request, response)
    return {"authenticated": False}


class ParticipantCreate(BaseModel):
    assignment_code: str | None = None
    consent_checked: bool = False
    student_number: str = ""


class AttemptPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    participant_id: str
    question_id: str
    phase: Literal["pretest", "retest", "final_test"] | None = None
    selected_option_ids: list[str]
    response_time_sec: float | None = None
    question_shown_at: datetime | None = None
    answered_at: datetime | None = None


class TermPageAnswerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str
    selected_option_ids: list[str]


class TermPageAttemptPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    participant_id: str
    phase: Literal["pretest", "retest", "final_test"]
    term_slug: str
    test_round: str
    page_id: UUID
    answers: list[TermPageAnswerPayload] = Field(min_length=1, max_length=2)
    question_shown_at: datetime
    answered_at: datetime
    elapsed_time_sec: float = Field(gt=0)


class TutorSessionCreate(BaseModel):
    participant_id: str
    term_slug: str


class TutorTurnRespond(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selected_option_ids: list[str]
    response_time_sec: float | None = None
    question_shown_at: datetime | None = None
    answered_at: datetime | None = None


class AILoginStart(BaseModel):
    type: str = "chatgpt"


class AILoginCancel(BaseModel):
    login_id: str


class ReasoningEffortPayload(BaseModel):
    reasoning_effort: Literal["low", "medium", "high"]


class AIModelPayload(BaseModel):
    model: Literal["gpt-6.1-sol", "gpt-6-luna"]


class OptionOrderPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["debug_fixed", "randomized"]


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


@app.exception_handler(RequestValidationError)
async def private_registration_validation(request: Request, exc: RequestValidationError):
    # FastAPI's default validation body echoes rejected input, including identifiers.
    if request.url.path in {"/api/participants", "/api/registrations"}:
        return JSONResponse(status_code=422, content={"detail": "参加登録の入力形式を確認してください。"}, headers={"Cache-Control": "no-store"})
    if request.url.path.rstrip("/") == "/api/admin/auth/login":
        return JSONResponse(status_code=422, content={"detail": "パスワードの入力形式を確認してください。"}, headers={"Cache-Control": "no-store"})
    from fastapi.exception_handlers import request_validation_exception_handler
    return await request_validation_exception_handler(request, exc)


@app.post("/api/registrations")
@app.post("/api/participants")
async def api_create_participant(
    payload: ParticipantCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    if not payload.consent_checked:
        raise HTTPException(400, "同意書への同意が必要です。")
    student_number = identity_mapping.validate_student_number(payload.student_number)
    normalized_key = normalize_idempotency_key(idempotency_key)
    registration_key = normalized_key or str(uuid4())
    if normalized_key and registration_key_was_deleted(db, normalized_key):
        raise HTTPException(409, "この参加登録は削除されています。再送による再登録はできません。")
    staged_id: str | None = None

    def operation() -> dict:
        nonlocal staged_id
        try:
            participant = create_participant(db, payload.assignment_code, payload.consent_checked)
            staged_id = participant.id
            identity_mapping.save_mapping(participant.id, participant.display_code, student_number,
                                          participant.consented_at.isoformat(), registration_key)
        except OperationalError as exc:
            _raise_database_unavailable(db, exc)
        return {
            "participant_id": participant.id,
            "display_code": participant.display_code,
            "current_step": participant.current_step,
        }

    try:
        # Always reserve a transaction, even for clients without a supplied key.
        return await run_idempotent(
            db,
            scope="participant:create",
            key=registration_key,
            participant_id=None,
            request_data={"assignment_code": payload.assignment_code, "consent_checked": payload.consent_checked,
                          "consent_document_version": identity_mapping.CONSENT_DOCUMENT_VERSION},
            operation=operation,
        )
    except Exception as exc:
        # Do not remove a mapping if the research commit succeeded but the response failed.
        db.rollback()
        if staged_id and db.query(Participant.id).filter_by(id=staged_id).first() is None:
            identity_mapping.delete_mapping(staged_id)
        if isinstance(exc, OperationalError):
            _raise_database_unavailable(db, exc)
        raise


@app.get("/api/participants/{participant_id}/current-step")
def current_step(participant_id: str, db: Session = Depends(get_db)) -> dict:
    participant = get_participant(db, participant_id)
    if not can_resume(participant):
        return {"step": "legacy_read_only", "next_url": "/start", "can_resume": False, "progress": None}
    return {
        "step": participant.current_step,
        "next_url": pretest_display.next_url(db, participant),
        "can_resume": True,
        "progress": experiment_progress(db, participant),
    }


@app.get("/api/experiment/{participant_id}/pretest")
def get_pretest(participant_id: str, db: Session = Depends(get_db)) -> dict:
    participant = get_participant(db, participant_id)
    questions = question_payloads(db, participant_id, "pretest")
    return {
        "phase": "pretest",
        "test_page_mode": effective_test_page_mode(participant),
        "questions": questions,
        "pending_question_review": pending_question_review(db, participant_id, "pretest", questions),
    }


@app.get("/api/experiment/{participant_id}/retest")
def get_retest(participant_id: str, db: Session = Depends(get_db)) -> dict:
    participant = get_participant(db, participant_id)
    questions = question_payloads(db, participant_id, "retest")
    return {
        "phase": "retest",
        "test_page_mode": effective_test_page_mode(participant),
        "questions": questions,
        "pending_question_review": pending_question_review(db, participant_id, "retest", questions),
    }




@app.get("/api/experiment/{participant_id}/final-test")
def get_final_test(participant_id: str, db: Session = Depends(get_db)) -> dict:
    participant = get_participant(db, participant_id)
    questions = question_payloads(db, participant_id, "final_test")
    return {
        "phase": "final_test",
        "test_page_mode": effective_test_page_mode(participant),
        "questions": questions,
        "pending_question_review": pending_question_review(db, participant_id, "final_test", questions),
    }


class QuestionReviewAcknowledgementPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phase: Literal["pretest", "retest", "final_test"]
    term_slug: str


@app.post("/api/participants/{participant_id}/question-review-acknowledgements")
def api_acknowledge_question_review(
    participant_id: str,
    payload: QuestionReviewAcknowledgementPayload,
    db: Session = Depends(get_db),
) -> dict:
    return acknowledge_question_review(db, participant_id, payload.phase, payload.term_slug)


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


@app.post("/api/attempts/term-page")
async def api_submit_term_page_attempt(
    payload: TermPageAttemptPayload,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    normalized_key = normalize_idempotency_key(idempotency_key)
    if normalized_key is None:
        raise HTTPException(status_code=400, detail="ページ回答の保存にはIdempotency-Keyが必要です。")

    def operation() -> dict:
        attempts = submit_test_term_page(db, payload.model_dump())
        return {"saved": True, "saved_question_count": len(attempts), "page_id": str(payload.page_id)}

    return await run_idempotent(
        db,
        scope=f"test-page:{payload.participant_id}:{payload.phase}:{payload.term_slug}:{payload.test_round}",
        key=normalized_key,
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
        participant = get_participant(db, participant_id)
        review = pretest_display.enabled(participant.show_pretest_results)
        return {"status": "completed", "learning_target_count": count, "learning_target_slugs": [row["term_slug"] for row in learning_targets(db, participant_id)], "next_step": next_step, "review_required": review, "next_url": "/learning-targets" if review else pretest_display.next_url(db, participant)}

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
    assert_current_experiment(participant)
    targets = learning_targets(db, participant_id)
    progress = post_pretest_test_progress(db, participant)
    review_skipped = pretest_display.skip_review(db, participant)
    return {
        "current_step": participant.current_step,
        "targets": targets,
        "review_required": not review_skipped,
        "next_url": pretest_display.next_url(db, participant),
        "pretest_results": pretest_results(db, participant_id) if not review_skipped and pretest_display.enabled(participant.show_pretest_results) else [],
        "test_results": latest_test_results(db, participant_id) if not review_skipped else {"test_round": "test", "test_round_label": "テスト", "results": []},
        "retest_cycles_completed": participant.retest_cycles_completed,
        **progress,
        "retest_cycle_limit_reached": (
            can_resume(participant)
            and participant.current_step in {"survey", "finish"}
            and (progress["post_pretest_tests_completed"] or 0) >= MAX_POST_PRETEST_TESTS
            and bool(targets)
        ),
    }


@app.post("/api/participants/{participant_id}/give-up-learning")
async def api_give_up_learning(
    participant_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    assert_current_experiment(get_participant(db, participant_id))
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
    assert_current_experiment(get_participant(db, participant_id))
    await tutor_prefetch_registry.cancel_for_participant(participant_id)
    return await run_idempotent(
        db,
        scope=f"give_up_experiment:{participant_id}",
        key=idempotency_key,
        participant_id=participant_id,
        request_data={"participant_id": participant_id},
        operation=lambda: give_up_experiment(db, participant_id),
    )


@app.get("/api/participants/{participant_id}/survey")
def api_survey_context(participant_id: str, db: Session = Depends(get_db)) -> dict:
    participant = get_participant(db, participant_id)
    assert_current_experiment(participant)
    return survey_context(db, participant)


@app.get("/api/participants/{participant_id}/presurvey")
def api_presurvey_context(participant_id: str, db: Session = Depends(get_db)) -> dict:
    participant = get_participant(db, participant_id)
    return presurvey_context(participant)


@app.post("/api/participants/{participant_id}/presurvey")
async def api_submit_presurvey(
    participant_id: str,
    payload: PresurveyPayload,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    return await run_idempotent(
        db,
        scope=f"presurvey:{participant_id}",
        key=idempotency_key,
        participant_id=participant_id,
        request_data=payload.model_dump(mode="json"),
        operation=lambda: submit_presurvey(db, participant_id, payload.model_dump()),
    )


@app.post("/api/tutor-turns/{turn_id}/material-view")
def api_material_view(turn_id: str, db: Session = Depends(get_db)) -> dict:
    return record_material_view(db, turn_id)


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
        return {"tutor_session_id": session.id, "session_index": session.session_index, "max_turns": MAX_LEARNING_CONFIRMATION_ATTEMPTS}

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
    if session is not None:
        assert_current_experiment(get_participant(db, session.participant_id))
    # Wait before touching the request-scoped SQLAlchemy session. The worker
    # may be waiting on an external AI call for several seconds.
    await tutor_prefetch_registry.wait_for(session_id)
    session = db.get(TutorSession, session_id)
    participant_id = session.participant_id if session else None

    async def operation() -> dict:
        turn = await generate_tutor_turn(db, session_id)
        current_session = db.get(TutorSession, session_id)
        term = db.get(Term, current_session.term_id) if current_session else None
        current_participant = get_participant(db, current_session.participant_id) if current_session else None
        stage_meta = (turn.practice_question_json or {}).get("stage_meta") or {}
        return {
            "turn_id": turn.id,
            "term_slug": term.slug if term else None,
            "term_label": term.label if term else None,
            "tutor_message": turn.tutor_message,
            "glossary": public_glossary((turn.diagnosis_json or {}).get("material_glossary")),
            "show_material_glossary": learning_material_glossary_mode.normalize_mode(
                current_participant.learning_material_glossary_mode if current_participant else None
            ) != learning_material_glossary_mode.INTEGRATED_MATERIAL,
            "learner_prompt": turn.learner_prompt,
            "practice_question": _public_practice_question(turn.practice_question_json),
            "requires_learner_response": True,
            "turn_index": turn.turn_index,
            "max_turns": MAX_LEARNING_CONFIRMATION_ATTEMPTS,
            "learning_stage": stage_meta.get("learning_stage"),
            "learning_stage_label": stage_meta.get("learning_stage_label"),
            "stage_completed": False,
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
    if participant_id is not None:
        assert_current_experiment(get_participant(db, participant_id))
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
    async def operation() -> dict:
        result = await score_phase(db, participant_id, "retest")
        participant = get_participant(db, participant_id)
        result["review_required"] = not pretest_display.skip_review(db, participant)
        if result["review_required"]:
            result["next_url"] = "/learning-targets"
        return result

    return await run_idempotent(
        db,
        scope=f"score:{participant_id}:retest",
        key=idempotency_key,
        participant_id=participant_id,
        request_data={"participant_id": participant_id, "phase": "retest"},
        operation=operation,
    )




@app.post("/api/participants/{participant_id}/score-final-test")
async def api_score_final_test(
    participant_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    async def operation() -> dict:
        result = await score_phase(db, participant_id, "final_test")
        participant = get_participant(db, participant_id)
        result["review_required"] = not pretest_display.skip_review(db, participant)
        if result["review_required"]:
            result["next_url"] = "/learning-targets"
        return result

    return await run_idempotent(
        db,
        scope=f"score:{participant_id}:final_test",
        key=idempotency_key,
        participant_id=participant_id,
        request_data={"participant_id": participant_id, "phase": "final_test"},
        operation=operation,
    )


@app.post("/api/participants/{participant_id}/evaluation-summary/recalculate")
def api_recalculate(participant_id: str, db: Session = Depends(get_db)) -> dict:
    summary = recalculate_evaluation(db, participant_id)
    return {"status": "completed", "evaluation_summary_id": summary.id}


@app.get("/api/admin/evaluation-summary")
def api_admin_summary(request: Request, db: Session = Depends(get_db)) -> dict:
    _reject_question_set_filter(request)
    return admin_summary(db)


def _reject_question_set_filter(request: Request) -> None:
    if "question_set_mode" in request.query_params:
        raise HTTPException(status_code=422, detail="問題版フィルターは廃止されました。")


class PretestDisplayPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool


class QuestionReviewDisplayPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool


@app.get("/api/admin/pretest-result-display")
def api_pretest_display(db: Session = Depends(get_db)):
    return JSONResponse({"enabled": pretest_display.current_setting(db), "applies_to": "new_participants_only"}, headers={"Cache-Control": "no-store"})


@app.put("/api/admin/pretest-result-display")
def api_save_pretest_display(payload: PretestDisplayPayload, db: Session = Depends(get_db)):
    return {"enabled": pretest_display.save_setting(db, payload.enabled), "applies_to": "new_participants_only"}


@app.get("/api/admin/question-review-display")
def api_question_review_display(db: Session = Depends(get_db)):
    return JSONResponse({"enabled": question_review_display.current_setting(db), "applies_to": "new_standard_participants_only"}, headers={"Cache-Control": "no-store"})


@app.put("/api/admin/question-review-display")
def api_save_question_review_display(payload: QuestionReviewDisplayPayload, db: Session = Depends(get_db)):
    return {"enabled": question_review_display.save_setting(db, payload.enabled), "applies_to": "new_standard_participants_only"}


@app.get("/api/admin/first-question-only")
def api_first_question_only(db: Session = Depends(get_db)):
    return JSONResponse({"enabled": first_question_only.current_setting(db), "applies_to": "new_standard_participants_only"}, headers={"Cache-Control": "no-store"})


@app.put("/api/admin/first-question-only")
def api_save_first_question_only(payload: QuestionReviewDisplayPayload, db: Session = Depends(get_db)):
    return {"enabled": first_question_only.save_setting(db, payload.enabled), "applies_to": "new_standard_participants_only"}


@app.get("/api/admin/option-order")
def api_admin_option_order(db: Session = Depends(get_db)) -> dict:
    return {"mode": current_option_order_mode(db), "applies_to": "new_participants_only"}


@app.put("/api/admin/option-order")
def api_set_admin_option_order(payload: OptionOrderPayload, db: Session = Depends(get_db)) -> dict:
    mode = save_option_order_mode(db, payload.mode)
    return {"mode": mode, "applies_to": "new_participants_only"}


@app.get("/api/admin/participants")
def api_admin_participants(db: Session = Depends(get_db)) -> dict:
    from app.models import Participant

    rows = db.query(Participant).order_by(Participant.created_at.desc()).all()
    give_up_counts = participant_give_up_counts(db, [row.id for row in rows])
    return {
        "participants": [
            {
                "participant_id": row.id,
                "show_pretest_results": pretest_display.enabled(row.show_pretest_results),
                "show_retest_results": pretest_display.enabled(row.show_retest_results),
                "show_question_reviews": row.show_question_reviews,
                "first_question_only": row.first_question_only,
                "learning_material_glossary_mode": row.learning_material_glossary_mode,
                "display_code": row.display_code,
                "group_condition": row.group_condition,
                "option_order_mode": row.option_order_mode or "debug_fixed",
                "experiment_spec_version": row.experiment_spec_version,
                "protocol_id": row.protocol_id,
                "can_resume": can_resume(row),
                "current_step": row.current_step,
                "retest_cycles_completed": row.retest_cycles_completed,
                **post_pretest_test_progress(db, row),
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "completion_reason": row.completion_reason,
                "give_up_learning_count": give_up_counts.get((row.id, "give_up_learning"), 0),
                "give_up_experiment_count": give_up_counts.get((row.id, "give_up_experiment"), 0),
            }
            for row in rows
        ]
    }


@app.delete("/api/admin/participants/{participant_id}")
async def api_delete_admin_participant(participant_id: str, db: Session = Depends(get_db)) -> dict:
    previous_deletion = participant_deletion_event(db, participant_id)
    if previous_deletion is not None:
        cleanup_state = (previous_deletion.after_json or {}).get("identity_mapping_cleanup")
        if cleanup_state == IDENTITY_MAPPING_CLEANUP_PENDING:
            if not complete_identity_mapping_cleanup(db, previous_deletion):
                raise HTTPException(
                    status_code=503,
                    detail="参加者データの削除は完了しましたが、対応表の削除が未完了です。時間をおいて再試行してください。",
                )
            return deletion_response(previous_deletion)
        if cleanup_state == IDENTITY_MAPPING_CLEANUP_COMPLETE:
            raise HTTPException(status_code=404, detail="被験者が見つかりません。")
        raise HTTPException(status_code=409, detail="参加者削除の状態を確認できません。")

    assert_current_experiment(get_participant(db, participant_id))
    await tutor_prefetch_registry.cancel_for_participant(participant_id)
    previous_defer_commit = db.info.get("defer_commits", False)
    db.info["defer_commits"] = True
    try:
        result = delete_participant(db, participant_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.info["defer_commits"] = previous_defer_commit

    deletion_event = participant_deletion_event(db, participant_id)
    if deletion_event is None or not complete_identity_mapping_cleanup(db, deletion_event):
        raise HTTPException(
            status_code=503,
            detail="参加者データの削除は完了しましたが、対応表の削除が未完了です。時間をおいて再試行してください。",
        )
    return result


def _visible_identity_mappings(db: Session) -> list[dict]:
    # Hide orphaned staged registrations after a crash; never expose them as participants.
    current_ids = {row[0] for row in db.query(Participant.id).all()}
    return [row for row in identity_mapping.list_mappings() if row["participant_id"] in current_ids]


@app.get("/api/admin/identity-mappings")
def api_identity_mappings(db: Session = Depends(get_db)):
    return JSONResponse({"mappings": _visible_identity_mappings(db)}, headers={"Cache-Control": "no-store"})


@app.get("/api/admin/identity-mappings.csv")
def api_identity_mapping_csv(db: Session = Depends(get_db)):
    return Response(identity_mapping.mapping_csv(_visible_identity_mappings(db)), media_type="text/csv; charset=utf-8",
                    headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="identity-mappings.csv"'})


@app.delete("/api/admin/identity-mappings")
def api_delete_all_identity_mappings():
    return JSONResponse({"deleted_count": identity_mapping.delete_mapping()}, headers={"Cache-Control": "no-store"})


@app.delete("/api/admin/identity-mappings/{participant_id}")
def api_delete_identity_mapping(participant_id: str):
    return JSONResponse({"deleted_count": identity_mapping.delete_mapping(participant_id)}, headers={"Cache-Control": "no-store"})


@app.get("/api/admin/logs/overview")
def api_admin_logs_overview(request: Request, db: Session = Depends(get_db)) -> dict:
    _reject_question_set_filter(request)
    return admin_logs_overview(db)


@app.get("/api/admin/logs/overview.csv")
def api_admin_logs_overview_csv(request: Request, db: Session = Depends(get_db)):
    _reject_question_set_filter(request)
    path = export_overview_logs_csv(db)
    return FileResponse(path, media_type="text/csv", filename=path.name)


@app.get("/api/admin/logs/overview_excel.csv")
def api_admin_logs_overview_excel_csv(request: Request, db: Session = Depends(get_db)):
    _reject_question_set_filter(request)
    path = export_overview_logs_excel_csv(db)
    return FileResponse(path, media_type="text/csv", filename=path.name)


@app.get("/api/admin/logs/overview.xlsx")
def api_admin_logs_overview_xlsx(request: Request, db: Session = Depends(get_db)):
    _reject_question_set_filter(request)
    path = export_overview_logs_xlsx(db)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )


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


@app.get("/api/admin/participants/{participant_id}/logs.xlsx")
def api_admin_participant_logs_xlsx(participant_id: str, db: Session = Depends(get_db)):
    path = export_participant_logs_xlsx(db, participant_id)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )


@app.get("/api/admin/export/{name}.csv")
def api_export_csv(name: str, request: Request, db: Session = Depends(get_db)):
    _reject_question_set_filter(request)
    path = export_csv(db, name)
    return FileResponse(path, media_type="text/csv", filename=path.name)


@app.get("/api/admin/export/{name}.xlsx")
def api_export_xlsx(name: str, request: Request, db: Session = Depends(get_db)):
    _reject_question_set_filter(request)
    path = export_hypothesis_metrics_xlsx(db, name)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )


@app.get("/api/admin/ai/status")
async def api_ai_status() -> dict:
    reasoning_status = _reasoning_effort_status()
    if settings.ai_backend == "codex_app_server":
        status = await CodexAppServerBackend().status()
        return {
            "ai_backend": settings.ai_backend,
            **status,
            **reasoning_status,
        }
    return {
        "ai_backend": "mock",
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
        **_reasoning_effort_status(),
    }


@app.post("/api/admin/ai/model")
def api_set_ai_model(payload: AIModelPayload) -> dict:
    if settings.ai_backend != "codex_app_server":
        raise HTTPException(status_code=409, detail="AI_BACKEND=mockではモデル設定を適用できません。")
    set_model(payload.model)
    return {
        "ai_backend": "codex_app_server" if settings.ai_backend == "codex_app_server" else "mock",
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
