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
| Phase2 inactive | retained for compatibility, not used in participant flow |
| Initial test | initial_test_v1, all-five MCQ |
| Retest loop | retest_v1, all-five MCQ, wrong/unknown terms return to learning |
| Final test | final_test_v1, all-five MCQ |
| Reproducibility | content hash, session version pin, AI/RAG logs |
| M transition analysis | learning choice attempts and evaluation summary |

## Group Difference

| Behavior | Control | Proposed |
|---|---|---|
| Fixed prerequisites/questions | same | same |
| Current-answer feedback | general | misconception-aware |
| Uses initial/retest diagnosis for teaching | no | yes |
| Uses cumulative history | no | yes |
| Phase1 prerequisite review | no | yes |
| Phase2 return | inactive | inactive |
| Phase2 attempts | inactive | inactive |
