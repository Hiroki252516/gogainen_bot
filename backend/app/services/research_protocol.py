"""Versioned baseline/posttest questionnaires and material-display events."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy.orm import Session
from sqlalchemy import update

from app.core.experiment_spec import assert_current_experiment
from app.models import AuditEvent, Participant, TutorSession, TutorTurn, now

PRESURVEY_VERSION = "presurvey-baseline-v5"
FOUR_TOPIC_PRESURVEY_VERSION_V5 = "presurvey-four-topic-baseline-v5"
FOUR_TOPIC_PRESURVEY_VERSION_V6 = "presurvey-four-topic-baseline-v6"
FOUR_TOPIC_PRESURVEY_VERSION = "presurvey-four-topic-baseline-v7"
SURVEY_VERSION = "posttest-5point-v4"
SUPPORTED_SURVEY_VERSIONS = (
    "posttest-10point-v1", "posttest-10point-v2", "posttest-10point-v3",
    "posttest-5point-v1", "posttest-5point-v2", "posttest-5point-v3", SURVEY_VERSION,
)
PosttestRating = Annotated[int, Field(strict=True, ge=1, le=5)] | Literal["not_applicable"]
ProficiencyRating = Annotated[int, Field(strict=True, ge=1, le=5)] | Literal["not_applicable"]
Comment = Annotated[str, StringConstraints(strip_whitespace=True)]
EXPOSURE_VALUES = ("experienced", "not_experienced", "cannot_recall")
UNDERSTANDING_VALUES = ("not_at_all", "hardly", "slightly", "moderately", "well")
AI_FREQUENCY_VALUES = ("0_days", "1_3_days", "4_8_days", "9_20_days", "21_30_days")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PriorTermExposure(StrictModel):
    pretraining: Literal["experienced", "not_experienced", "cannot_recall"]
    fine_tuning: Literal["experienced", "not_experienced", "cannot_recall"]
    rag: Literal["experienced", "not_experienced", "cannot_recall"]
    prompt_engineering: Literal["experienced", "not_experienced", "cannot_recall"]
    multi_agent: Literal["experienced", "not_experienced", "cannot_recall"]
    memory_process: Literal["experienced", "not_experienced", "cannot_recall"]


class PriorTermUnderstanding(StrictModel):
    pretraining: Literal["not_at_all", "slightly", "moderately", "well"] | None
    fine_tuning: Literal["not_at_all", "slightly", "moderately", "well"] | None
    rag: Literal["not_at_all", "slightly", "moderately", "well"] | None
    prompt_engineering: Literal["not_at_all", "slightly", "moderately", "well"] | None
    multi_agent: Literal["not_at_all", "slightly", "moderately", "well"] | None
    memory_process: Literal["not_at_all", "slightly", "moderately", "well"] | None


class FourTopicPriorTermExposure(StrictModel):
    transformer: Literal["experienced", "not_experienced", "cannot_recall"]
    pretraining: Literal["experienced", "not_experienced", "cannot_recall"]
    instruction_tuning: Literal["experienced", "not_experienced", "cannot_recall"]
    human_feedback_post_training: Literal["experienced", "not_experienced", "cannot_recall"]
    multi_agent: Literal["experienced", "not_experienced", "cannot_recall"]
    memory_process: Literal["experienced", "not_experienced", "cannot_recall"]


class FourTopicPriorTermUnderstanding(StrictModel):
    transformer: Literal["not_at_all", "slightly", "moderately", "well"] | None
    pretraining: Literal["not_at_all", "slightly", "moderately", "well"] | None
    instruction_tuning: Literal["not_at_all", "slightly", "moderately", "well"] | None
    human_feedback_post_training: Literal["not_at_all", "slightly", "moderately", "well"] | None
    multi_agent: Literal["not_at_all", "slightly", "moderately", "well"] | None
    memory_process: Literal["not_at_all", "slightly", "moderately", "well"] | None


class FourTopicPriorTermUnderstandingV6(StrictModel):
    transformer: Literal["not_at_all", "hardly", "slightly", "moderately", "well"] | None
    pretraining: Literal["not_at_all", "hardly", "slightly", "moderately", "well"] | None
    instruction_tuning: Literal["not_at_all", "hardly", "slightly", "moderately", "well"] | None
    human_feedback_post_training: Literal["not_at_all", "hardly", "slightly", "moderately", "well"] | None
    multi_agent: Literal["not_at_all", "hardly", "slightly", "moderately", "well"] | None
    memory_process: Literal["not_at_all", "hardly", "slightly", "moderately", "well"] | None


class FourTopicPriorTermExposureV3(StrictModel):
    transformer: Literal["experienced", "not_experienced", "cannot_recall"]
    pretraining: Literal["experienced", "not_experienced", "cannot_recall"]
    fine_tuning: Literal["experienced", "not_experienced", "cannot_recall"]
    human_feedback_post_training: Literal["experienced", "not_experienced", "cannot_recall"]
    multi_agent: Literal["experienced", "not_experienced", "cannot_recall"]
    memory_process: Literal["experienced", "not_experienced", "cannot_recall"]


class FourTopicPriorTermUnderstandingV3(StrictModel):
    transformer: Literal["not_at_all", "slightly", "moderately", "well"] | None
    pretraining: Literal["not_at_all", "slightly", "moderately", "well"] | None
    fine_tuning: Literal["not_at_all", "slightly", "moderately", "well"] | None
    human_feedback_post_training: Literal["not_at_all", "slightly", "moderately", "well"] | None
    multi_agent: Literal["not_at_all", "slightly", "moderately", "well"] | None
    memory_process: Literal["not_at_all", "slightly", "moderately", "well"] | None


class FourTopicPriorTermExposureV2(StrictModel):
    transformer: Literal["experienced", "not_experienced", "cannot_recall"]
    pretraining: Literal["experienced", "not_experienced", "cannot_recall"]
    instruction_tuning: Literal["experienced", "not_experienced", "cannot_recall"]
    human_feedback_post_training: Literal["experienced", "not_experienced", "cannot_recall"]
    multi_agent: Literal["experienced", "not_experienced", "cannot_recall"]
    memory_process: Literal["experienced", "not_experienced", "cannot_recall"]


class FourTopicPriorTermUnderstandingV2(StrictModel):
    transformer: Literal["not_at_all", "slightly", "moderately", "well"] | None
    pretraining: Literal["not_at_all", "slightly", "moderately", "well"] | None
    instruction_tuning: Literal["not_at_all", "slightly", "moderately", "well"] | None
    human_feedback_post_training: Literal["not_at_all", "slightly", "moderately", "well"] | None
    multi_agent: Literal["not_at_all", "slightly", "moderately", "well"] | None
    memory_process: Literal["not_at_all", "slightly", "moderately", "well"] | None


class AIProficiencyRatings(StrictModel):
    goal_aligned_output: ProficiencyRating
    revise_instructions: ProficiencyRating
    verify_with_sources: ProficiencyRating


class BaselineRatings(StrictModel):
    ai_usage_frequency_30d: Literal["0_days", "1_3_days", "4_8_days", "9_20_days", "21_30_days"]
    ai_proficiency: AIProficiencyRatings


class PosttestRatings(StrictModel):
    system_usability: PosttestRating


class MaterialRatings(StrictModel):
    clarity: PosttestRating
    readability: PosttestRating
    japanese_clarity: PosttestRating
    difficulty_appropriateness: PosttestRating
    learning_usefulness: PosttestRating
    amount_appropriateness: PosttestRating


MATERIAL_RATING_KEYS = tuple(MaterialRatings.model_fields)
PRESURVEY_TERM_ITEMS = (
    {"key": "pretraining", "label": "事前学習"},
    {"key": "fine_tuning", "label": "ファインチューニング"},
    {"key": "rag", "label": "RAG"},
    {"key": "prompt_engineering", "label": "プロンプトエンジニアリング"},
    {"key": "multi_agent", "label": "マルチエージェント"},
    {"key": "memory_process", "label": "記憶プロセス"},
)
FOUR_TOPIC_PRESURVEY_TERM_ITEMS = (
    {"key": "transformer", "label": "Transformer"},
    {"key": "pretraining", "label": "事前学習"},
    {"key": "instruction_tuning", "label": "インストラクションチューニング"},
    {"key": "human_feedback_post_training", "label": "人の評価・好みを用いる事後学習"},
    {"key": "multi_agent", "label": "マルチエージェント"},
    {"key": "memory_process", "label": "記憶プロセス"},
)
FOUR_TOPIC_PRESURVEY_V3_TERM_ITEMS = (
    {"key": "transformer", "label": "Transformer"},
    {"key": "pretraining", "label": "事前学習"},
    {"key": "fine_tuning", "label": "ファインチューニング"},
    {"key": "human_feedback_post_training", "label": "人の評価・好みを用いる事後学習"},
    {"key": "multi_agent", "label": "マルチエージェント"},
    {"key": "memory_process", "label": "記憶プロセス"},
)
FOUR_TOPIC_PRESURVEY_V2_TERM_ITEMS = (
    {"key": "transformer", "label": "Transformer"},
    {"key": "pretraining", "label": "事前学習"},
    {"key": "instruction_tuning", "label": "指示チューニング"},
    {"key": "human_feedback_post_training", "label": "人の評価・好みを用いる事後学習"},
    {"key": "multi_agent", "label": "マルチエージェント"},
    {"key": "memory_process", "label": "記憶プロセス"},
)


class PresurveyPayload(StrictModel):
    survey_version: Literal["presurvey-baseline-v5"] = PRESURVEY_VERSION
    prior_term_exposure: PriorTermExposure
    prior_term_understanding: PriorTermUnderstanding
    general_ratings: BaselineRatings

    @model_validator(mode="after")
    def validate_understanding_branch(self):
        _validate_understanding_branch(self.prior_term_exposure, self.prior_term_understanding)
        return self


class FourTopicPresurveyPayload(StrictModel):
    survey_version: Literal["presurvey-four-topic-baseline-v5"] = FOUR_TOPIC_PRESURVEY_VERSION_V5
    prior_term_exposure: FourTopicPriorTermExposure
    prior_term_understanding: FourTopicPriorTermUnderstanding
    general_ratings: BaselineRatings

    @model_validator(mode="after")
    def validate_understanding_branch(self):
        _validate_understanding_branch(self.prior_term_exposure, self.prior_term_understanding)
        return self


class FourTopicPresurveyPayloadV6(StrictModel):
    survey_version: Literal["presurvey-four-topic-baseline-v6"] = FOUR_TOPIC_PRESURVEY_VERSION_V6
    prior_term_exposure: FourTopicPriorTermExposure
    prior_term_understanding: FourTopicPriorTermUnderstandingV6
    general_ratings: BaselineRatings

    @model_validator(mode="after")
    def validate_understanding_branch(self):
        _validate_understanding_branch(self.prior_term_exposure, self.prior_term_understanding)
        return self


class FourTopicPresurveyPayloadV7(StrictModel):
    survey_version: Literal["presurvey-four-topic-baseline-v7"] = FOUR_TOPIC_PRESURVEY_VERSION
    prior_term_exposure: FourTopicPriorTermExposure
    prior_term_understanding: FourTopicPriorTermUnderstandingV6
    general_ratings: BaselineRatings

    @model_validator(mode="after")
    def validate_understanding_branch(self):
        _validate_understanding_branch(self.prior_term_exposure, self.prior_term_understanding)
        return self


class PresurveyPayloadV4(PresurveyPayload):
    """Read-only schema for validating the prior standard presurvey version."""

    survey_version: Literal["presurvey-baseline-v4"] = "presurvey-baseline-v4"


class FourTopicPresurveyPayloadV4(FourTopicPresurveyPayload):
    """Read-only schema for validating the prior four-topic presurvey version."""

    survey_version: Literal["presurvey-four-topic-baseline-v4"] = "presurvey-four-topic-baseline-v4"


class FourTopicPresurveyPayloadV3(StrictModel):
    survey_version: Literal["presurvey-four-topic-baseline-v3"] = "presurvey-four-topic-baseline-v3"
    prior_term_exposure: FourTopicPriorTermExposureV3
    prior_term_understanding: FourTopicPriorTermUnderstandingV3
    general_ratings: BaselineRatings

    @model_validator(mode="after")
    def validate_understanding_branch(self):
        _validate_understanding_branch(self.prior_term_exposure, self.prior_term_understanding)
        return self


class FourTopicPresurveyPayloadV2(StrictModel):
    survey_version: Literal["presurvey-four-topic-baseline-v2"] = "presurvey-four-topic-baseline-v2"
    prior_term_exposure: FourTopicPriorTermExposureV2
    prior_term_understanding: FourTopicPriorTermUnderstandingV2
    general_ratings: BaselineRatings

    @model_validator(mode="after")
    def validate_understanding_branch(self):
        _validate_understanding_branch(self.prior_term_exposure, self.prior_term_understanding)
        return self


def _validate_understanding_branch(exposure: StrictModel, understanding: StrictModel) -> None:
    for key, exposure_value in exposure.model_dump().items():
        understanding_value = getattr(understanding, key)
        if exposure_value == "experienced" and understanding_value is None:
            raise ValueError(f"{key}: understanding is required when exposure is experienced")
        if exposure_value != "experienced" and understanding_value is not None:
            raise ValueError(f"{key}: understanding must be null when exposure is not experienced")


class SurveyPayload(StrictModel):
    survey_version: Literal["posttest-5point-v4"] = SURVEY_VERSION
    general_ratings: PosttestRatings
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


def presurvey_context(participant: Participant) -> dict:
    assert_current_experiment(participant)
    if participant.current_step != "presurvey":
        raise HTTPException(status_code=409, detail="この参加者は事前アンケート対象ではありません。")
    four_topic = participant.test_content_mode == "four_topic_fundamentals"
    survey_version = FOUR_TOPIC_PRESURVEY_VERSION if four_topic else PRESURVEY_VERSION
    terms = FOUR_TOPIC_PRESURVEY_TERM_ITEMS if four_topic else PRESURVEY_TERM_ITEMS
    return {"survey_version": survey_version, "term_items": list(terms)}


def validate_presurvey_payload(payload: dict, test_content_mode: str | None = None) -> dict:
    if test_content_mode == "four_topic_fundamentals":
        return FourTopicPresurveyPayloadV7.model_validate(payload).model_dump()
    return PresurveyPayload.model_validate(payload).model_dump()


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
