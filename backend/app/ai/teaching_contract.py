from __future__ import annotations

from typing import Any

from app.ai.material_structure import evidence_sections, validate_material_structure


MATERIAL_TARGET_CHARACTERS = 700
MATERIAL_MIN_CHARACTERS = 600
MATERIAL_MAX_CHARACTERS = 800
INTEGRATED_MATERIAL_TARGET_CHARACTERS = 1000
INTEGRATED_MATERIAL_MAX_CHARACTERS = 1200


PROMPT_CONTRACT_VERSION = "tutoring-prompt-contract-v9-mode-specific-length"
TEACHING_CONTRACT_TYPES = ("M1", "M3", "unknown")
REFUTATION_MODES = ("explicit", "implicit", "category_comparison", "none")


def teaching_contract_schema() -> dict[str, Any]:
    """Return the strict app-server schema for research-only teaching evidence."""
    properties: dict[str, Any] = {
        "target_claim_id": {"type": ["string", "null"]},
        "addressed_claim_ids": {"type": "array", "items": {"type": "string"}},
        "refutation_mode": {"type": "string", "enum": list(REFUTATION_MODES)},
        "corrected_claim": {"type": ["string", "null"]},
        "mechanism_explanation": {"type": "string"},
        "contrast_example": {"type": ["string", "null"]},
        "transfer_check": {"type": "string"},
        "target_addressed": {"type": "boolean"},
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def target_claim_ids(payload: dict[str, Any], expected_type: str | None = None) -> list[str]:
    targets = payload.get("pretest_targets") or []
    if expected_type not in {"M1", "M3"}:
        return []
    return [
        str(target["claim_id"])
        for target in targets
        if isinstance(target, dict)
        and (payload.get("learning_scope") or target.get("misconception_type") in {None, expected_type})
        and target.get("claim_id")
    ]


def validate_teaching_contract(
    result: dict[str, Any],
    expected_type: str | None,
    payload: dict[str, Any],
    term_label: str | None = None,
) -> dict[str, Any]:
    """Validate the structured teaching plan and evidence in visible material."""
    if expected_type not in TEACHING_CONTRACT_TYPES:
        return {
            "required": False,
            "valid": True,
            "expected_type": expected_type,
            "missing": [],
        }

    missing: list[str] = []
    contract = result.get("teaching_contract")
    if not isinstance(contract, dict):
        contract = {}
        missing.append("teaching_contract:missing")

    expected_ids = target_claim_ids(payload, expected_type)
    target_claim_id = contract.get("target_claim_id")
    addressed_ids = contract.get("addressed_claim_ids")
    if not isinstance(addressed_ids, list) or any(not isinstance(value, str) for value in addressed_ids):
        missing.append("addressed_claim_ids:invalid")
        addressed_ids = []
    if expected_type in {"M1", "M3"}:
        if expected_ids:
            if target_claim_id not in expected_ids:
                missing.append(f"target_claim_id:expected_one_of_{','.join(expected_ids)}")
            for claim_id in expected_ids:
                if claim_id not in addressed_ids:
                    missing.append(f"addressed_claim_ids:missing:{claim_id}")
        else:
            # A later learning response may reveal M1/M3 without a
            # researcher-verified pretest claim. Do not let the model invent one.
            if target_claim_id is not None:
                missing.append("target_claim_id:no_observed_target_must_be_null")
            if addressed_ids:
                missing.append("addressed_claim_ids:no_observed_target_must_be_empty")
    else:
        if target_claim_id is not None:
            missing.append("target_claim_id:unknown_must_be_null")
        if addressed_ids:
            missing.append("addressed_claim_ids:unknown_must_be_empty")

    mode = contract.get("refutation_mode")
    allowed_modes = {"explicit", "implicit"} if expected_type == "M1" else {"category_comparison"} if expected_type == "M3" else {"none"}
    if mode not in allowed_modes:
        missing.append(f"refutation_mode:invalid_for_{expected_type}")
    if contract.get("target_addressed") is not True:
        missing.append("target_addressed:not_true")

    corrected_claim = contract.get("corrected_claim")
    mechanism = contract.get("mechanism_explanation")
    contrast = contract.get("contrast_example")
    transfer_check = contract.get("transfer_check")
    if expected_type in {"M1", "M3"} and (not isinstance(corrected_claim, str) or not corrected_claim.strip()):
        missing.append("corrected_claim:empty")
    if expected_type == "unknown" and corrected_claim not in (None, ""):
        missing.append("corrected_claim:unknown_must_be_empty")
    if not isinstance(mechanism, str) or not mechanism.strip():
        missing.append("mechanism_explanation:empty")
    if expected_type in {"M1", "M3"} and (not isinstance(contrast, str) or not contrast.strip()):
        missing.append("contrast_example:empty")
    if expected_type == "unknown" and contrast not in (None, ""):
        missing.append("contrast_example:unknown_must_be_empty")
    if not isinstance(transfer_check, str) or not transfer_check.strip():
        missing.append("transfer_check:empty")

    message = str(result.get("tutor_message") or "")
    missing.extend(validate_material_structure(result, term_label)["missing"])
    placements: dict[str, list[int]] = {}
    for field, value in (
        ("corrected_claim", corrected_claim),
        ("mechanism_explanation", mechanism),
        ("contrast_example", contrast),
        ("transfer_check", transfer_check),
    ):
        if isinstance(value, str) and value.strip():
            placements[field] = evidence_sections(message, value)
            if not placements[field]:
                missing.append(f"{field}:evidence_not_in_section")

    return {
        "required": True,
        "valid": not missing,
        "expected_type": expected_type,
        "target_claim_ids": expected_ids,
        "actual_target_claim_id": target_claim_id,
        "evidence_placements": placements,
        "required_fields": [
            "target_claim_id",
            "addressed_claim_ids",
            "refutation_mode",
            "corrected_claim",
            "mechanism_explanation",
            "contrast_example",
            "transfer_check",
            "target_addressed",
        ],
        "missing": missing,
    }


def validate_tutoring_material_safety(
    result: dict[str, Any],
    forbidden_strings: list[str] | None = None,
) -> dict[str, Any]:
    """Reject fixed-question text or server-side answer strings in generated material."""
    missing: list[str] = []
    message = str(result.get("tutor_message") or "")
    for index, value in enumerate(forbidden_strings or []):
        if isinstance(value, str) and value.strip() and value in message:
            missing.append(f"tutor_message:forbidden_fixed_text:{index}")
    return {"valid": not missing, "missing": missing}


def material_length_contract(*, integrated_material: bool = False) -> dict[str, int]:
    return {
        "target_character_count": INTEGRATED_MATERIAL_TARGET_CHARACTERS if integrated_material else MATERIAL_TARGET_CHARACTERS,
        "min_character_count": MATERIAL_MIN_CHARACTERS,
        "max_character_count": INTEGRATED_MATERIAL_MAX_CHARACTERS if integrated_material else MATERIAL_MAX_CHARACTERS,
    }


def validate_tutoring_material_length(
    result: dict[str, Any],
    *,
    integrated_material: bool = False,
) -> dict[str, Any]:
    """Validate the mode-specific size contract for generated material."""
    material = str(result.get("tutor_message") or "")
    character_count = len(material)
    length_contract = material_length_contract(integrated_material=integrated_material)
    missing: list[str] = []
    if character_count < length_contract["min_character_count"]:
        missing.append(
            f"tutor_message:character_count_below_minimum:{character_count}<{length_contract['min_character_count']}"
        )
    elif character_count > length_contract["max_character_count"]:
        missing.append(
            f"tutor_message:character_count_above_maximum:{character_count}>{length_contract['max_character_count']}"
        )
    return {
        "valid": not missing,
        "character_count": character_count,
        **length_contract,
        "missing": missing,
    }


def mock_teaching_contract(
    expected_type: str,
    target: dict[str, Any] | None,
    *,
    corrected_claim: str | None = None,
    mechanism_explanation: str,
    contrast_example: str | None,
    transfer_check: str,
) -> dict[str, Any]:
    claim_id = target.get("claim_id") if expected_type in {"M1", "M3"} and target else None
    return {
        "target_claim_id": claim_id,
        "addressed_claim_ids": [claim_id] if claim_id else [],
        "refutation_mode": "explicit" if expected_type == "M1" else "category_comparison" if expected_type == "M3" else "none",
        "corrected_claim": ((target or {}).get("corrected_claim") or corrected_claim) if expected_type in {"M1", "M3"} else None,
        "mechanism_explanation": mechanism_explanation,
        "contrast_example": contrast_example if expected_type in {"M1", "M3"} else None,
        "transfer_check": transfer_check,
        "target_addressed": True,
    }
