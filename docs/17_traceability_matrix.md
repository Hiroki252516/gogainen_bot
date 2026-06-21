# 17. Traceability Matrix

| Research Requirement | Implementation |
|---|---|
| Same content in both groups | content version, prerequisite definitions, fixed question bank |
| Proposed group uses learning logs | proposed material payload and adaptive review |
| Control group excludes logs | control payload sanitizer and tests |
| Fixed prerequisites | YAML definitions and session expansion |
| Fixed MCQ learning | learning questions/options/display orders |
| Immediate feedback | distractor explanation and correct summary AI calls |
| No answer before third failure | forced resolution state machine |
| Phase2 without material | participant session response omits material |
| All-five retest | retest_v2 query without target filter |
| Reproducibility | content hash, session version pin, AI/RAG logs |
| M transition analysis | learning choice attempts and evaluation summary |

## Group Difference

| Behavior | Control | Proposed |
|---|---|---|
| Fixed prerequisites/questions | same | same |
| Current-answer feedback | general | misconception-aware |
| Uses pretest diagnosis | no | yes |
| Uses cumulative history | no | yes |
| Phase1 prerequisite review | no | yes |
| Phase2 return | no | yes |
| Phase2 attempts | 1 | max 3 |
