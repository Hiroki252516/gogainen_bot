from typing import Literal

ANNOTATION_ONLY = "annotation_only"
INTEGRATED_MATERIAL = "integrated_material"
LearningMaterialGlossaryMode = Literal["annotation_only", "integrated_material"]
VALID_MODES = {ANNOTATION_ONLY, INTEGRATED_MATERIAL}


def normalize_mode(value: str | None) -> str:
    return value if value in VALID_MODES else ANNOTATION_ONLY
