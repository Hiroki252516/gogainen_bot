from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.ai.prompt_config import PROMPT_TEXT


_TAXONOMY_CONFIG = PROMPT_TEXT["research_config"]["misconception_taxonomy"]
TAXONOMY_VERSION = _TAXONOMY_CONFIG["version"]
MISCONCEPTION_TAXONOMY: dict[str, Any] = _TAXONOMY_CONFIG["types"]


def taxonomy_for_prompt() -> dict[str, Any]:
    return deepcopy(MISCONCEPTION_TAXONOMY)
