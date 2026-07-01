from __future__ import annotations

from copy import deepcopy
from typing import Any


_MISCONCEPTION_TAXONOMY: dict[str, Any] = {
    "version": "misconception_taxonomy_v1",
    "visibility": "internal_prompt_only",
    "learner_visible_label_policy": "Do not write M1/M2/M3/M4 or research paper names in learner-facing text.",
    "types": {
        "M1": {
            "name": "category_misclassification",
            "definition": "The learner assigns the target concept to the wrong kind of thing or wrong upper category.",
            "diagnostic_cues": [
                "The answer treats an abstract process, representation, metric, or method as a physical place, storage object, human feeling, personality, or social value.",
                "The answer explains what the concept is by replacing it with a different ontological category rather than by describing its role or mechanism.",
                "The selected distractor frames the concept as something it is not, even when some words sound related.",
            ],
            "teaching_goal": "Move the learner from the wrong category to the correct category before adding details.",
            "teaching_moves": [
                "State what the concept is not.",
                "State what kind of concept it is.",
                "Contrast the wrong category and the correct category.",
                "Only after that, give a concrete example in the correct category.",
            ],
            "avoid": [
                "Do not only add more facts while leaving the wrong category untouched.",
                "Do not anthropomorphize the AI or use metaphors that reinforce the wrong category.",
            ],
            "research_basis": [
                "Chi's conceptual change account treats some misconceptions as category-level mistakes that require category shifts, not just fact addition.",
            ],
        },
        "M2": {
            "name": "similar_concept_boundary_confusion",
            "definition": "The learner understands a nearby concept but cannot distinguish its boundary from the target concept.",
            "diagnostic_cues": [
                "The answer gives the definition, role, input, output, or use case of a related but different concept.",
                "The answer treats two neighboring concepts as the same or interchangeable.",
                "The error is best corrected by clarifying differences between concepts rather than by only defining the target concept in isolation.",
            ],
            "teaching_goal": "Make the boundary between the target concept and the confused concept explicit.",
            "teaching_moves": [
                "Compare roles, inputs, processes, outputs, update targets, and use cases.",
                "Use compact contrasting cases or paired examples.",
                "Ask the learner to decide which concept applies in a short case and why.",
                "Keep the contrast focused on the confused pair, not every related term.",
            ],
            "avoid": [
                "Do not present the two concepts separately without explaining the boundary.",
                "Do not imply that similar terms are interchangeable.",
            ],
            "research_basis": [
                "Hassani, Ghodsi, and Howell discuss student confusion between standard deviation and standard error as an example of boundary confusion between close statistical concepts.",
                "Contrasting-cases and comparison research supports using explicit contrasts to help learners notice relevant distinctions.",
            ],
        },
        "M3": {
            "name": "surface_feature_keyword_reaction",
            "definition": "The learner reacts to salient words, symbols, numbers, kanji, literal translation, or name similarity instead of using the underlying principle or structure.",
            "diagnostic_cues": [
                "The answer is justified mainly by a word appearing in the question or option.",
                "The answer relies on everyday meaning, literal translation, name impression, or a salient surface feature.",
                "The answer does not explain the mechanism, relationship, condition, or principle that should determine the choice.",
            ],
            "teaching_goal": "Redirect attention from surface cues to the deep structure and decision criterion.",
            "teaching_moves": [
                "Name the relevant judgment criterion in learner-friendly words.",
                "Show why the surface cue is unreliable.",
                "Use an example where the same keyword appears but the target concept does not apply.",
                "Ask the learner to identify the mechanism or relationship rather than the keyword.",
            ],
            "avoid": [
                "Do not reinforce keyword matching as the main strategy.",
                "Do not overuse literal translations or wordplay as the explanation.",
            ],
            "research_basis": [
                "Chi, Feltovich, and Glaser report that novices often represent physics problems by literal features, while experts abstract underlying principles.",
            ],
        },
        "unknown": {
            "name": "knowledge_gap",
            "definition": "The learner gives no usable concept-related explanation or chooses an explicit unknown option.",
            "diagnostic_cues": [
                "The selected option or response is equivalent to 'I do not know'.",
                "The answer is too empty to infer a specific misconception.",
            ],
            "teaching_goal": "Build the missing basic meaning before misconception-specific remediation.",
            "teaching_moves": [
                "Start from a short foundational definition.",
                "Use one simple example and one non-example.",
                "Avoid treating the learner as having a specific misconception unless later evidence appears.",
            ],
            "avoid": [
                "Do not over-diagnose M1/M2/M3 from insufficient evidence.",
            ],
            "research_basis": [
                "This is a system category for insufficient evidence or missing prerequisite knowledge, not a misconception type.",
            ],
        },
    },
}

_TEACHING_GUIDELINES: dict[str, Any] = {
    "version": "teaching_guidelines_v1",
    "group_policy": {
        "proposed": "Use diagnosis, retest context, learning history, misconception taxonomy, and teaching guidelines to choose the instructional focus.",
        "control": "Do not use diagnosis, retest context, learning history, misconception taxonomy, or misconception-specific adaptation.",
    },
    "strategy_map": {
        "M1": "category_reorientation",
        "M2": "boundary_comparison",
        "M3": "deep_structure_focus",
        "unknown": "foundational_explanation",
    },
    "learner_visible_constraints": [
        "Never show internal M labels.",
        "Never name the research paper or author as part of learner feedback.",
        "Do not reveal the correct option text during first or second wrong attempts.",
        "Use short Japanese Markdown with headings and bullet points.",
    ],
    "selection_rule": [
        "If diagnosis_context, retest_context, and learning_history disagree, prioritize the current selected option for feedback and the repeated pattern for the next material focus.",
        "If the evidence is insufficient or the selected option is unknown, use foundational_explanation instead of forcing M1/M2/M3.",
        "For material generation, make the misconception-specific support visible as explanation style and examples, not as internal labels.",
    ],
}


MISCONCEPTION_SUPPORT_PURPOSES = {
    "diagnose_answer",
    "generate_tutoring_turn",
    "generate_prerequisite_material",
    "generate_concept_phase1_material",
    "explain_selected_distractor",
    "generate_emergency_question_variant",
    "grade_prerequisite_answer",
    "grade_concept_phase1_answer",
    "grade_concept_phase2_answer",
    "generate_adaptive_support",
    "grade_response",
    "generate_feedback",
}


def misconception_taxonomy_payload() -> dict[str, Any]:
    return deepcopy(_MISCONCEPTION_TAXONOMY)


def teaching_guidelines_payload() -> dict[str, Any]:
    return deepcopy(_TEACHING_GUIDELINES)


def enrich_payload_with_misconception_support(purpose: str, payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("group_condition") != "proposed" or purpose not in MISCONCEPTION_SUPPORT_PURPOSES:
        return payload
    enriched = dict(payload)
    enriched.setdefault("misconception_taxonomy", misconception_taxonomy_payload())
    enriched.setdefault("teaching_guidelines", teaching_guidelines_payload())
    return enriched
