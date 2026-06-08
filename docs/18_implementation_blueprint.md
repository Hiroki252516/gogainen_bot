# 18. Implementation Blueprint

この文書は、現在の実装構成と、今後拡張するときの青写真をまとめる。

## Build Order

1. backendとDBを先に作る
2. seed questionsを入れる
3. AIBackend抽象を作り、CodexAppServerBackendを通常実行にする
4. frontendを研究フロー順に接続する
5. CSV exportとadminを作る
6. MockAIBackendはテスト・切り分け用に維持する

理由:

- 研究ロジックはAI接続から分離する
- 自動テストはMockで再現性を確保できる
- app-server仕様変更の影響を隔離できる

## Backend Package Layout

```text
backend/app/
├── main.py
├── core/
│   ├── config.py
│   ├── errors.py
│   └── logging.py
├── db/
│   ├── session.py
│   └── base.py
├── models/
│   ├── participant.py
│   ├── question.py
│   ├── attempt.py
│   ├── learner_state.py
│   ├── tutor.py
│   ├── recurrence.py
│   ├── ai_call_log.py
│   └── evaluation.py
├── schemas/
│   ├── api.py
│   ├── ai.py
│   └── export.py
├── services/
│   ├── experiment_service.py
│   ├── question_service.py
│   ├── diagnosis_service.py
│   ├── learner_state_service.py
│   ├── scaffolding_service.py
│   ├── tutoring_service.py
│   ├── evaluation_service.py
│   └── export_service.py
├── ai/
│   ├── backend.py
│   ├── mock_backend.py
│   ├── codex_app_server_backend.py
│   ├── codex_client.py
│   └── prompts.py
├── api/
│   ├── participants.py
│   ├── questions.py
│   ├── attempts.py
│   ├── diagnosis.py
│   ├── tutoring.py
│   ├── scoring.py
│   ├── admin.py
│   └── ai_status.py
├── seed/
│   └── seed_questions.py
└── exports/
    └── csv_exporter.py
```

## Frontend Package Layout

```text
frontend/app/
├── start/page.tsx
├── pretest/page.tsx
├── diagnosing/page.tsx
├── learning-targets/page.tsx
├── learning/[termSlug]/page.tsx
├── retest/page.tsx
├── l0-check/page.tsx
├── finish/page.tsx
└── admin/page.tsx

frontend/components/
├── QuestionCard.tsx
├── ConfidenceScale.tsx
├── ReasonTextarea.tsx
├── ProgressHeader.tsx
├── TutorPanel.tsx
├── AdminMetricCards.tsx
└── CsvExportButtons.tsx
```

## Core Domain Types

### ScaffoldingLevel

```text
L3 > L2 > L1
```

Utility:

- `lower_level(level)`
- `raise_level(level)`
- `level_to_numeric(level)`

### TeachingStrategy

- general_explanation
- foundational_explanation
- category_reorientation
- boundary_comparison
- deep_structure_focus
- context_transfer_training
- self_explanation_check
- contrastive_example
- discrimination_practice
- counterexample_prompt
- common_structure_extraction
- guided_self_correction

## Critical Algorithms

### Learning Target Selection

Input:

- pretest attempts
- diagnosis result
- pretest does not collect reason_text or confidence
- learning session does not collect confidence
- response time

Priority:

1. M1 or M2 misconception
2. M3 misconception
3. unknown
4. unstable_correct
5. stable_correct that still needs confirmation test

Output:

- up to `MAX_LEARNING_TARGETS`
- term_assignments with `is_learning_target = true`

### Diagnosis Merge

1. Start from selected option label
2. Do not send reason_text or confidence in pretest diagnosis
3. If selected option correct but available evidence is weak, mark unstable_correct
4. If conflict is strong, mark ambiguous

### Recurrence

```text
recurrence_flag =
  previous phase has primary misconception M1-M3
  and current phase has same primary misconception
  and term_id is same
```

Unknown is not recurrence.

### Stage-Based Learning Update

Use deterministic service logic from `04_scaffolding_and_tutoring.md`. In learning turns, backend uses AI feedback `is_sufficient` as the update signal for stage progression. In `term_understanding`, sufficient answers move to the next component term, and the last component term moves to `concept_understanding`. Insufficient answers repeat the same component term. In `concept_understanding`, sufficient answers complete the session and move to `final_feedback`; insufficient answers return to the first component term. AI `next_action`, `next_scaffolding_level`, and generated `scaffolding_level` are advisory or compatibility fields and do not control navigation. Continued material includes previous practice question, learner response, and feedback. Initial material always includes a full explanation: definition, role in the target concept, common misconception contrast, and criterion/example.

## MVP API Dependency Graph

```text
POST /participants
  -> GET /pretest
  -> POST /attempts
  -> POST /diagnose-pretest
  -> GET /learning-targets
  -> POST /tutor-sessions
  -> POST /tutor-sessions/{id}/turns
  -> POST /tutor-turns/{id}/respond
  -> GET /retest
  -> POST /score-retest
  -> GET /l0-check
  -> POST /score-l0-check
  -> POST /evaluation-summary/recalculate
  -> GET /admin/export/evaluation_summary.csv
```

## Development Guardrails

- Do not implement an OpenAI API key path
- Do not leak internal labels to participant pages
- Do not let AI decide final metrics
- Do not let app-server failure block MockAIBackend testing
- Do not skip CSV export
- Do not hardcode model names
- Do not store auth tokens

## Minimum Seed Data

MVP seed must include:

- 8 terms
- pretest question per term
- retest variant per term
- option labels correct/M1/M2/M3/unknown

Learning practice questions can be smaller but must exist for at least all 8 terms.

## README to Generate During Implementation

The final implemented README should include:

- prerequisites
- docker compose start
- migration
- seed
- running with Codex app-server
- MockAIBackend is test-only
- admin URL
- CSV export location
- troubleshooting

## First Implementation PR Scope

If implementation is split, the first PR should stop at:

- Docker backend/db/frontend boots
- DB migrations
- seed
- Codex app-server status check
- pretest -> diagnosis -> learner_states

## RAG教材参照

学習ターン生成と学習回答フィードバックでは、`rag_ready_教材` のローカルTF-IDF検索結果を `rag_context` としてAIBackend payloadへ渡す。OpenAI APIキーや外部vector storeは通常実行に使わない。RAG資産が見つからない場合は空のcontextとして扱い、実験フローを停止しない。
