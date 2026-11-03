"""Versioned posttest questionnaire and observed material-display events."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints
from sqlalchemy.orm import Session
from sqlalchemy import update

from app.core.experiment_spec import assert_current_experiment
from app.models import AuditEvent, Participant, TutorSession, TutorTurn, now

SURVEY_VERSION = "posttest-10point-v2"
SUPPORTED_SURVEY_VERSIONS = ("posttest-10point-v1", SURVEY_VERSION)
Rating = Annotated[int, Field(strict=True, ge=1, le=10)]
Comment = Annotated[str, StringConstraints(strip_whitespace=True)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PriorTermKnowledge(StrictModel):
    pretraining: StrictBool
    fine_tuning: StrictBool
    rag: StrictBool
    prompt_engineering: StrictBool
    multi_agent: StrictBool
    memory_process: StrictBool


class GeneralRatings(StrictModel):
    ai_usage_frequency: Rating
    self_rated_ai_proficiency: Rating
    system_usability: Rating
    system_clarity: Rating


class MaterialRatings(StrictModel):
    clarity: Rating
    readability: Rating
    japanese_clarity: Rating
    difficulty_appropriateness: Rating
    learning_usefulness: Rating
    amount_appropriateness: Rating


MATERIAL_RATING_KEYS = tuple(MaterialRatings.model_fields)


class SurveyPayload(StrictModel):
    survey_version: Literal["posttest-10point-v2"] = SURVEY_VERSION
    prior_term_knowledge: PriorTermKnowledge
    general_ratings: GeneralRatings
    material_ratings: MaterialRatings | None
    free_comment: Comment | None = None


def has_viewed_material(db: Session, participant_id: str) -> bool:
    return db.query(TutorTurn.id).join(TutorSession).filter(
        TutorSession.participant_id == participant_id,
        TutorTurn.material_viewed_at.is_not(None),
    ).first() is not None


def survey_context(db: Session, participant: Participant) -> dict:
    assert_current_experiment(participant)
    viewed = has_viewed_material(db, participant.id)
    return {
        "survey_version": SURVEY_VERSION,
        "has_viewed_material": viewed,
        "material_ratings_required": viewed,
        "material_rating_status": "required" if viewed else "not_applicable_not_viewed",
    }


def validate_survey_for_participant(db: Session, participant: Participant, payload: dict) -> dict:
    parsed = SurveyPayload.model_validate(payload).model_dump()
    viewed = has_viewed_material(db, participant.id)
    if viewed != (parsed["material_ratings"] is not None):
        raise HTTPException(status_code=422, detail="教材閲覧者は教材評価6項目が必須です。未閲覧者の教材評価は対象外（null）にしてください。")
    return {**parsed, "has_viewed_material": viewed,
            "material_rating_status": "answered" if viewed else "not_applicable_not_viewed"}


def record_material_view(db: Session, turn_id: str) -> dict:
    turn = db.query(TutorTurn).filter_by(id=turn_id).with_for_update().one_or_none()
    if turn is None:
        raise HTTPException(status_code=404, detail="turn not found")
    session = db.get(TutorSession, turn.tutor_session_id)
    participant = db.get(Participant, session.participant_id) if session else None
    if participant is None:
        raise HTTPException(status_code=404, detail="participant not found")
    assert_current_experiment(participant)
    if turn.material_viewed_at is None:
        if participant.current_step not in {"learning_targets", "learning"} or session.ended_at is not None:
            raise HTTPException(status_code=409, detail="現在の学習セッションでのみ教材表示を記録できます。")
        if session.prefetch_state not in {"none", "consumed"}:
            raise HTTPException(status_code=409, detail="未利用の先行生成は教材表示として記録できません。")
        viewed_at = now()
        changed = db.execute(update(TutorTurn).where(TutorTurn.id == turn.id, TutorTurn.material_viewed_at.is_(None)).values(material_viewed_at=viewed_at))
        if changed.rowcount:
            db.add(AuditEvent(actor="participant", action="material_view", entity_type="participant", entity_id=participant.id,
                              after_json={"turn_id": turn.id, "session_id": session.id, "material_viewed_at": viewed_at.isoformat()}))
            # Invalidate evaluation caches even if no learning answer follows.
            participant.updated_at = now()
        db.commit()
        db.refresh(turn)
    return {"turn_id": turn.id, "material_viewed_at": turn.material_viewed_at.isoformat(), "recorded": True}
