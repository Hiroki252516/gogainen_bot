# 18. Implementation Blueprint

## Build Order

1. Docs and YAML content
2. Content validation/import
3. DB compatibility columns and new tables
4. AIBackend material contracts
5. Choice-based learning state machine
6. Frontend replacement
7. Metrics, CSV, admin
8. Automated and browser verification

## Content Layout

```text
experiment_content/
  manifest.yaml
  pretest/pretest_v2.yaml
  retest/retest_v2.yaml
  terms/
    transformer.yaml
    attention.yaml
    llm_training_process.yaml
    pretraining.yaml
    post_training.yaml
```

The term files contain prerequisite names and deterministic question templates. Import expands them into 255 immutable DB questions.

## State Machine

```text
prerequisite
  -> concept_phase1
  -> concept_phase2
  -> completed

AI/RAG/content failure -> technical_blocked -> retry-material -> previous stage
```

## Compatibility

Existing free-text sessions continue to be readable. New sessions are identified by a non-null content version and use only choice-based APIs and logs.
