from typing import Literal

from app.models import RuntimeSetting


ANNOTATION_ONLY = "annotation_only"
INTEGRATED_MATERIAL = "integrated_material"
LearningMaterialGlossaryMode = Literal["annotation_only", "integrated_material"]
VALID_MODES = {ANNOTATION_ONLY, INTEGRATED_MATERIAL}


def normalize_mode(value: str | None) -> str:
    return value if value in VALID_MODES else ANNOTATION_ONLY


def current_setting(db) -> str:
    row = db.get(RuntimeSetting, 1)
    return normalize_mode(row.learning_material_glossary_mode if row else None)


def save_setting(db, mode: str) -> str:
    if mode not in VALID_MODES:
        raise ValueError("unsupported learning material glossary mode")
    row = db.get(RuntimeSetting, 1)
    if row is None:
        row = RuntimeSetting(id=1)
        db.add(row)
    row.learning_material_glossary_mode = mode
    db.commit()
    return mode
