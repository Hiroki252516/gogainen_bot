from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    ContentVersion,
    LearningQuestion,
    LearningQuestionOption,
    LearningQuestionSlot,
    PrerequisiteDefinition,
    Question,
    QuestionOption,
    Term,
)


class TestQuestionSpec(BaseModel):
    target_term: str
    body: str
    correct: str
    m1: str
    m2: str
    m3: str


class TestFileSpec(BaseModel):
    schema_version: int = 1
    version: str
    questions: list[TestQuestionSpec]


class MisconceptionSpec(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    m1: str = Field(alias="M1")
    m2: str = Field(alias="M2")
    m3: str = Field(alias="M3")


class PrerequisiteSpec(BaseModel):
    key: str
    label: str
    definition: str
    misconceptions: MisconceptionSpec


class PrerequisiteSetSpec(BaseModel):
    version: str
    items: list[PrerequisiteSpec]

    @model_validator(mode="after")
    def unique_keys(self) -> "PrerequisiteSetSpec":
        keys = [item.key for item in self.items]
        if len(keys) != len(set(keys)):
            raise ValueError("prerequisite keys must be unique")
        if not self.items:
            raise ValueError("at least one prerequisite is required")
        return self


class TermContentSpec(BaseModel):
    schema_version: int = 1
    content_version: str
    target_term: str
    target_label: str
    target_definition: str
    target_misconceptions: MisconceptionSpec
    phase_links: dict[str, list[str]]
    prerequisite_set: PrerequisiteSetSpec

    @model_validator(mode="after")
    def valid_links(self) -> "TermContentSpec":
        keys = {item.key for item in self.prerequisite_set.items}
        for misconception in ("M1", "M2", "M3"):
            links = self.phase_links.get(misconception) or []
            if not links or any(link not in keys for link in links):
                raise ValueError(f"{self.target_term}: invalid phase_links for {misconception}")
        return self


class ManifestSpec(BaseModel):
    schema_version: int = 1
    release_version: str
    validation_status: str
    is_active: bool = True
    pretest_file: str
    retest_file: str
    term_files: list[str]


class ContentBundle(BaseModel):
    manifest: ManifestSpec
    pretest: TestFileSpec
    retest: TestFileSpec
    terms: list[TermContentSpec]
    file_hash: str
    root: str

    @model_validator(mode="after")
    def validate_bundle(self) -> "ContentBundle":
        term_slugs = [term.target_term for term in self.terms]
        if len(term_slugs) != 5 or len(set(term_slugs)) != 5:
            raise ValueError("exactly five unique target terms are required")
        expected = set(term_slugs)
        if {item.target_term for item in self.pretest.questions} != expected:
            raise ValueError("pretest must cover all target terms")
        if {item.target_term for item in self.retest.questions} != expected:
            raise ValueError("retest must cover all target terms")
        return self


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        value = yaml.safe_load(file)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a mapping")
    return value


def load_content_bundle(root: str | Path | None = None) -> ContentBundle:
    content_root = Path(root or get_settings().experiment_content_dir).resolve()
    manifest_path = content_root / "manifest.yaml"
    manifest = ManifestSpec.model_validate(_read_yaml(manifest_path))
    files = [manifest_path, content_root / manifest.pretest_file, content_root / manifest.retest_file]
    files.extend(content_root / relative for relative in manifest.term_files)
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(content_root).as_posix().encode())
        digest.update(path.read_bytes())
    return ContentBundle(
        manifest=manifest,
        pretest=TestFileSpec.model_validate(_read_yaml(content_root / manifest.pretest_file)),
        retest=TestFileSpec.model_validate(_read_yaml(content_root / manifest.retest_file)),
        terms=[TermContentSpec.model_validate(_read_yaml(content_root / path)) for path in manifest.term_files],
        file_hash=digest.hexdigest(),
        root=str(content_root),
    )


def _upsert_option(
    db: Session,
    question_id: str,
    default_order: int,
    *,
    body: str,
    is_correct: bool,
    misconception_type: str | None,
    rationale: str,
) -> None:
    option = (
        db.query(QuestionOption)
        .filter_by(question_id=question_id, default_order=default_order)
        .one_or_none()
    )
    if not option:
        option = QuestionOption(
            question_id=question_id,
            option_label=chr(65 + default_order),
            default_order=default_order,
            body=body,
            is_correct=is_correct,
        )
        db.add(option)
    option.body = body
    option.is_correct = is_correct
    option.misconception_type = misconception_type
    option.rationale = rationale


def _sync_test_file(
    db: Session,
    release: ContentVersion,
    terms: dict[str, Term],
    spec: TestFileSpec,
    phase: str,
) -> None:
    db.query(Question).filter(Question.phase == phase, Question.variant_key != spec.version).update(
        {"is_active": False}, synchronize_session=False
    )
    for item in spec.questions:
        term = terms[item.target_term]
        question = (
            db.query(Question)
            .filter_by(term_id=term.id, phase=phase, variant_key=spec.version)
            .one_or_none()
        )
        if not question:
            question = Question(
                term_id=term.id,
                phase=phase,
                question_type="definition" if phase == "pretest" else "retest_same_construct",
                body=item.body,
                construct_key=f"{item.target_term}_{phase}",
                variant_key=spec.version,
            )
            db.add(question)
            db.flush()
        question.body = item.body
        question.content_version_id = release.id
        question.expected_answer = item.correct
        question.expected_keywords = []
        question.is_active = True
        configured = [
            (item.correct, True, None, "correct"),
            (item.m1, False, "M1", "category misconception"),
            (item.m2, False, "M2", "boundary misconception"),
            (item.m3, False, "M3", "surface-feature misconception"),
            ("わからない。", False, "unknown", "knowledge gap"),
        ]
        for index, (body, correct, misconception, rationale) in enumerate(configured):
            _upsert_option(
                db,
                question.id,
                index,
                body=body,
                is_correct=correct,
                misconception_type=misconception,
                rationale=rationale,
            )


def _variant_text(text: str, attempt_index: int, slot_index: int, cycle_index: int = 1) -> str:
    prefixes = [
        "",
        "対象概念との関係を考えると、",
        "別の場面でも成り立つ説明として、",
    ]
    suffixes = [
        "",
        "という点が重要である。",
        "と整理できる。",
    ]
    prefix = prefixes[(attempt_index + slot_index + cycle_index) % len(prefixes)]
    suffix = suffixes[(attempt_index * slot_index + cycle_index) % len(suffixes)]
    return f"{prefix}{text}{suffix}"


def _upsert_learning_option(
    db: Session,
    question: LearningQuestion,
    order: int,
    body: str,
    correct: bool,
    misconception: str | None,
    linked_keys: list[str],
    remediation_focus: str,
) -> None:
    option = (
        db.query(LearningQuestionOption)
        .filter_by(learning_question_id=question.id, default_order=order)
        .one_or_none()
    )
    if not option:
        option = LearningQuestionOption(
            learning_question_id=question.id,
            default_order=order,
            body=body,
            is_correct=correct,
        )
        db.add(option)
    option.body = body
    option.is_correct = correct
    option.misconception_type = misconception
    option.diagnostic_rationale = (
        "correct concept" if correct else ("knowledge gap" if misconception == "unknown" else f"{misconception} misconception")
    )
    option.linked_prerequisite_keys = linked_keys
    option.remediation_focus = remediation_focus


def _upsert_learning_question(
    db: Session,
    slot: LearningQuestionSlot,
    variant_key: str,
    attempt_index: int,
    body: str,
    correct: str,
    misconceptions: MisconceptionSpec,
    linked: dict[str, list[str]],
    remediation_focus: str,
    validation_status: str,
) -> None:
    question = db.query(LearningQuestion).filter_by(slot_id=slot.id, variant_key=variant_key).one_or_none()
    if not question:
        question = LearningQuestion(
            slot_id=slot.id,
            variant_key=variant_key,
            attempt_index=attempt_index,
            body=body,
        )
        db.add(question)
        db.flush()
    question.body = body
    question.attempt_index = attempt_index
    question.source_type = "predefined_codex"
    question.validation_status = validation_status
    question.is_active = True
    values = [
        (correct, True, None),
        (misconceptions.m1, False, "M1"),
        (misconceptions.m2, False, "M2"),
        (misconceptions.m3, False, "M3"),
        ("わからない。", False, "unknown"),
    ]
    for order, (text, is_correct, misconception) in enumerate(values):
        _upsert_learning_option(
            db,
            question,
            order,
            text,
            is_correct,
            misconception,
            [] if is_correct or misconception == "unknown" else linked.get(misconception, []),
            remediation_focus,
        )


def _get_or_create_slot(
    db: Session,
    release: ContentVersion,
    term: Term,
    slot_key: str,
    stage: str,
    required_order: int,
    prerequisite_id: str | None = None,
    cycle_index: int | None = None,
) -> LearningQuestionSlot:
    slot = (
        db.query(LearningQuestionSlot)
        .filter_by(content_version_id=release.id, target_term_id=term.id, slot_key=slot_key)
        .one_or_none()
    )
    if not slot:
        slot = LearningQuestionSlot(
            content_version_id=release.id,
            target_term_id=term.id,
            slot_key=slot_key,
            stage=stage,
            required_order=required_order,
        )
        db.add(slot)
        db.flush()
    slot.stage = stage
    slot.required_order = required_order
    slot.prerequisite_definition_id = prerequisite_id
    slot.cycle_index = cycle_index
    return slot


def _sync_term_learning_content(
    db: Session,
    release: ContentVersion,
    term: Term,
    spec: TermContentSpec,
    validation_status: str,
) -> None:
    definitions: dict[str, PrerequisiteDefinition] = {}
    for order, item in enumerate(spec.prerequisite_set.items, start=1):
        definition = (
            db.query(PrerequisiteDefinition)
            .filter_by(
                target_term_id=term.id,
                set_version=spec.prerequisite_set.version,
                prerequisite_key=item.key,
            )
            .one_or_none()
        )
        if not definition:
            definition = PrerequisiteDefinition(
                content_version_id=release.id,
                target_term_id=term.id,
                prerequisite_key=item.key,
                label=item.label,
                display_order=order,
                set_version=spec.prerequisite_set.version,
            )
            db.add(definition)
            db.flush()
        definition.content_version_id = release.id
        definition.label = item.label
        definition.display_order = order
        definition.is_active = True
        definitions[item.key] = definition
        for slot_index in (1, 2):
            slot_key = f"prerequisite:{item.key}:slot{slot_index}"
            slot = _get_or_create_slot(
                db,
                release,
                term,
                slot_key,
                "prerequisite",
                slot_index,
                prerequisite_id=definition.id,
            )
            for attempt_index in (1, 2, 3):
                body = f"「{item.label}」について、観点{slot_index}の説明として最も適切なものはどれか。"
                _upsert_learning_question(
                    db,
                    slot,
                    f"{item.key}_slot{slot_index}_attempt{attempt_index}_v1",
                    attempt_index,
                    body,
                    _variant_text(item.definition, attempt_index, slot_index),
                    MisconceptionSpec(
                        M1=_variant_text(item.misconceptions.m1, attempt_index, slot_index),
                        M2=_variant_text(item.misconceptions.m2, attempt_index, slot_index),
                        M3=_variant_text(item.misconceptions.m3, attempt_index, slot_index),
                    ),
                    {"M1": [item.key], "M2": [item.key], "M3": [item.key]},
                    item.definition,
                    validation_status,
                )

    for cycle_index in (1, 2, 3):
        for slot_index in (1, 2):
            slot_key = f"phase1:cycle{cycle_index}:slot{slot_index}"
            slot = _get_or_create_slot(
                db,
                release,
                term,
                slot_key,
                "concept_phase1",
                slot_index,
                cycle_index=cycle_index,
            )
            for attempt_index in (1, 2, 3):
                body = (
                    f"{spec.target_label}について、教材で扱った観点を踏まえた説明として"
                    f"最も適切なものはどれか。（確認{slot_index}）"
                )
                _upsert_learning_question(
                    db,
                    slot,
                    f"{spec.target_term}_phase1_c{cycle_index}_s{slot_index}_a{attempt_index}_v1",
                    attempt_index,
                    body,
                    _variant_text(spec.target_definition, attempt_index, slot_index, cycle_index),
                    MisconceptionSpec(
                        M1=_variant_text(spec.target_misconceptions.m1, attempt_index, slot_index, cycle_index),
                        M2=_variant_text(spec.target_misconceptions.m2, attempt_index, slot_index, cycle_index),
                        M3=_variant_text(spec.target_misconceptions.m3, attempt_index, slot_index, cycle_index),
                    ),
                    spec.phase_links,
                    spec.target_definition,
                    validation_status,
                )

    phase2_slot = _get_or_create_slot(db, release, term, "phase2", "concept_phase2", 1)
    for attempt_index in (1, 2, 3):
        body = f"教材を見ずに、{spec.target_label}の説明として最も適切なものを選んでください。"
        _upsert_learning_question(
            db,
            phase2_slot,
            f"{spec.target_term}_phase2_attempt{attempt_index}_v1",
            attempt_index,
            body,
            _variant_text(spec.target_definition, attempt_index, 1),
            MisconceptionSpec(
                M1=_variant_text(spec.target_misconceptions.m1, attempt_index, 1),
                M2=_variant_text(spec.target_misconceptions.m2, attempt_index, 1),
                M3=_variant_text(spec.target_misconceptions.m3, attempt_index, 1),
            ),
            spec.phase_links,
            spec.target_definition,
            validation_status,
        )


def sync_content_bundle(db: Session, bundle: ContentBundle | None = None) -> ContentVersion:
    bundle = bundle or load_content_bundle()
    manifest = bundle.manifest
    release = (
        db.query(ContentVersion)
        .filter_by(content_type="experiment_release", version_key=manifest.release_version)
        .one_or_none()
    )
    if not release:
        release = ContentVersion(
            content_type="experiment_release",
            version_key=manifest.release_version,
            source_file=str(Path(bundle.root) / "manifest.yaml"),
            file_hash=bundle.file_hash,
            validation_status=manifest.validation_status,
            is_active=manifest.is_active,
        )
        db.add(release)
        db.flush()
    release.source_file = str(Path(bundle.root) / "manifest.yaml")
    release.file_hash = bundle.file_hash
    release.validation_status = manifest.validation_status
    if manifest.is_active:
        db.query(ContentVersion).filter(
            ContentVersion.content_type == "experiment_release",
            ContentVersion.id != release.id,
        ).update({"is_active": False}, synchronize_session=False)
    release.is_active = manifest.is_active

    existing_terms = {term.slug: term for term in db.query(Term).all()}
    active_slugs = {spec.target_term for spec in bundle.terms}
    for index, spec in enumerate(bundle.terms, start=1):
        term = existing_terms.get(spec.target_term)
        if not term:
            term = Term(slug=spec.target_term, label=spec.target_label, display_order=index)
            db.add(term)
            db.flush()
        term.label = spec.target_label
        term.description = spec.target_definition
        term.display_order = index
        term.is_active = True
        existing_terms[term.slug] = term
    for slug, term in existing_terms.items():
        if slug not in active_slugs:
            term.is_active = False

    _sync_test_file(db, release, existing_terms, bundle.pretest, "pretest")
    _sync_test_file(db, release, existing_terms, bundle.retest, "retest")
    db.query(Question).filter(Question.phase.in_(("l0_check", "transfer"))).update(
        {"is_active": False}, synchronize_session=False
    )
    for spec in bundle.terms:
        _sync_term_learning_content(
            db,
            release,
            existing_terms[spec.target_term],
            spec,
            manifest.validation_status,
        )
    db.commit()
    return release
