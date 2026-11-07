STANDARD = "standard"
ASSESSMENT_BANK_VERSIONS = {STANDARD: "split-actions-v5"}
LEARNING_CONTENT_VERSIONS = {STANDARD: 15}
ASSESSMENT_BANK_VERSION = ASSESSMENT_BANK_VERSIONS[STANDARD]
LEARNING_CONTENT_VERSION = LEARNING_CONTENT_VERSIONS[STANDARD]

# Historical standard banks remain available to restore saved test results.
HISTORICAL_ASSESSMENT_BANK_VERSIONS = {
    6: {STANDARD: "scenario-actions-v1"},
    7: {STANDARD: "scenario-actions-v1"},
    8: {STANDARD: "scenario-actions-v1"},
    9: {STANDARD: "scenario-actions-v2"},
    10: {STANDARD: "scenario-actions-v3"},
    11: {STANDARD: "scenario-actions-v4"},
    12: {STANDARD: "scenario-actions-v4"},
    13: {STANDARD: "scenario-actions-v4"},
    14: {STANDARD: "scenario-actions-v4"},
    15: {STANDARD: "scenario-actions-v4"},
    16: {STANDARD: "scenario-actions-v4"},
    17: {STANDARD: "scenario-actions-v4"},
    18: {STANDARD: "scenario-actions-v4"},
    19: {STANDARD: "scenario-actions-v5"},
    20: {STANDARD: "scenario-actions-v6"},
    21: {STANDARD: "scenario-actions-v6"},
    22: {STANDARD: "scenario-actions-v6"},
    23: {STANDARD: "scenario-actions-v7"},
    24: {STANDARD: "scenario-actions-v8"},
    25: {STANDARD: "scenario-actions-v9"},
    26: {STANDARD: "scenario-actions-v9"},
    27: {STANDARD: "split-actions-v1"},
    28: {STANDARD: "split-actions-v1"},
    29: {STANDARD: "split-actions-v1"},
    30: {STANDARD: "split-actions-v1"},
    31: {STANDARD: "split-actions-v1"},
    32: {STANDARD: "split-actions-v2"},
    33: {STANDARD: "split-actions-v3"},
    34: {STANDARD: "split-actions-v4"},
    35: {STANDARD: "split-actions-v5"},
    36: {STANDARD: "split-actions-v5"},
    37: {STANDARD: "split-actions-v5"},
    38: {STANDARD: "split-actions-v5"},
    39: {STANDARD: "split-actions-v5"},
    40: {STANDARD: "split-actions-v5"},
    41: {STANDARD: "split-actions-v5"},
}

# Version 41 was used by parallel protocols. Keep the v5 default for the two
# mainline protocols and restore the branch-specific v6 bank by protocol ID.
HISTORICAL_ASSESSMENT_BANK_PROTOCOL_VERSIONS = {
    (41, "experiment-plan-2026-11-07-split-actions-v6-q1-only-v1"): {
        STANDARD: "split-actions-v6",
    },
}


def historical_assessment_bank_versions_for(participant):
    key = (participant.experiment_spec_version, participant.protocol_id)
    return HISTORICAL_ASSESSMENT_BANK_PROTOCOL_VERSIONS.get(
        key,
        HISTORICAL_ASSESSMENT_BANK_VERSIONS.get(participant.experiment_spec_version),
    )


def assessment_construct_key(term_slug: str, phase: str, *, bank_version: str | None = None) -> str:
    bank = bank_version or ASSESSMENT_BANK_VERSION
    is_split_bank = bank.startswith("split-actions-")
    final_prefix = "final_test_" if phase == "final_test" and not is_split_bank else ""
    return f"{term_slug}_{final_prefix}{bank}"
