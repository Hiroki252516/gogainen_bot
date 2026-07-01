# 99. Sources and Notes

## Authoritative Sources

- `/Users/hiroki/Downloads/5月18日(テーマ変更) (2) 2.pptx`
- `/Users/hiroki/Downloads/5月25日進捗報告.pptx`
- `revised_experiment_flow_term_concept_stages_FINAL.md`
- `revised_experiment_flow_3phase_learning_session_v2.md`
- `fixed_prerequisite_mcq_experiment_design.md`

Later documents override earlier design drafts. The current implementation source of truth is `fixed_prerequisite_mcq_experiment_design.md`.

## Current Decisions

- Research target is concept discrimination and misconception avoidance, not prose explanation ability.
- Both groups receive the same fixed prerequisites and questions.
- Proposed only uses initial-test diagnosis, cumulative learning logs, and retest-error logs for teaching adaptation.
- Proposed AI calls receive an internal misconception taxonomy and teaching guidelines so M1/M2/M3 are defined at runtime, not only in docs.
- `initial_retest_final_test_experiment_design_review.md` is the current design source for the initial-test, retest-loop, final-test flow.
- Learning answers are fixed five-choice items.
- AI generates materials and feedback, not normal questions or scores.
- Pre-survey, L0 check, and transfer test are not conducted.
- Retest covers all five concepts.
- Content is versioned in YAML and pinned per participant.
- Old content remains inactive for reproducibility.

## Validation Note

The initial content release is provisional. Before formal data collection, two or more experts should independently review correctness and M classification, followed by cognitive interviews with 5–10 representative learners.

## Misconception Taxonomy Sources

- M1 is grounded in Chi's conceptual change account, especially category-level conceptual change and category mistakes. The system operationalizes this as wrong-category assignment and teaches through category reorientation.
- M2 uses Hassani, Ghodsi, and Howell's discussion of standard deviation / standard error confusion as a concrete example of close-concept boundary confusion. Because that paper is domain-specific, the broader teaching guideline also uses comparison and contrasting-cases research as support for boundary-focused instruction.
- M3 is grounded in Chi, Feltovich, and Glaser's expert/novice problem representation findings: novices tend to use literal surface features, while experts abstract underlying principles. The system operationalizes this as keyword/surface-feature reaction and teaches through deep-structure focus.
- Runtime implementation keeps these sources internal. Learner-facing materials must not name M labels or research papers.

Reference URLs:

- Chi, M. T. H. (2008). Three types of conceptual change: Belief revision, mental model transformation, and categorical shift. https://education.asu.edu/sites/g/files/litvpz656/files/lcl/chi_concpetualchangechapter_0.pdf
- Hassani, H., Ghodsi, M., & Howell, G. (2010). A note on standard deviation and standard error. https://doi.org/10.1093/teamat/hrq003
- Chi, M. T. H., Feltovich, P. J., & Glaser, R. (1981). Categorization and representation of physics problems by experts and novices. https://education.asu.edu/lcl/publications/chi-m-t-h-feltovich-p-glaser-r-1981-categorization-and-representation-physics
- ComPADRE summary of Chi, Feltovich, and Glaser (1981). https://www.compadre.org/portal/items/detail.cfm?ID=2341
- National Academies discussion of contrasting cases. https://www.nationalacademies.org/read/9853/chapter/6
