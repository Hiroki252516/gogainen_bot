# 18. Implementation Blueprint

この文書は、現在の実装構成と、今回の新フローを実装するときの青写真をまとめる。

## Build Order

1. docsとseed方針を揃える
2. DBモデルを追加する
3. AIBackend契約を拡張し、Mockを先に通す
4. backend APIを3段階学習セッションへ接続する
5. frontend学習画面をgroup_conditionで分岐し、両群3段階UIにする
6. 評価指標とCSVを更新する
7. Codex app-server実行を確認する

## Backend Package Layout

現行実装では単一 `experiment.py` に寄せてよいが、責務は以下に分けて考える。

- ExperimentService: 参加者、pretest、diagnosis、retest
- LearningSessionService: proposed/control 3-stage learning session
- EvaluationService: recurrence, gate metrics
- ExportService: CSV
- AIBackendService: AI call logging and backend selection

## Frontend Pages

```text
frontend/app/
├── start/page.tsx
├── pretest/page.tsx
├── diagnosing/page.tsx
├── learning-targets/page.tsx
├── learning/[termSlug]/page.tsx
├── retest/page.tsx
├── survey/post/page.tsx
├── finish/page.tsx
└── admin/page.tsx
```

`survey/pre`, `l0-check`, `transfer-test` は通常導線から外す。

## Critical Algorithms

### Learning Target Selection

Input:

- pretest attempts
- diagnosis result

Output:

- all non-stable-correct terms
- term_assignments with `is_learning_target = true`

### Proposed 3-Stage Learning

1. Create learning_session
2. Generate 3 prerequisite_terms with RAG + pretest diagnosis
3. Grade each term answer, max 2 attempts
4. If all pass, generate concept phase1 material
5. Grade phase1 answer, max 3 attempts
6. Phase1 fail returns missing prerequisite + previous related term for review or retries phase1
7. Phase1 pass generates phase2 prompt and light conditions
8. Grade phase2 answer without showing material, max 3 attempts
9. Phase2 fail 1-2 returns to phase1; phase2 fail 3 saves `failed_phase2`
10. Completed/blocked/failed_phase1/failed_phase2 session is saved

### Control Learning

1. Create learning_session
2. Generate 3 general small questions with RAG and target concept only
3. Save small-question answers; fail does not block progression
4. Generate phase1 general material and grade once
5. Generate phase2 prompt and grade once without adaptive return
6. Mark session completed regardless of phase pass/fail

### Recurrence

```text
recurrence_flag =
  pretest has primary misconception M1-M3
  and retest has same primary misconception
  and term_id is same
```

Unknown is not recurrence.

## MVP API Dependency Graph

```text
POST /participants
  -> GET /pretest
  -> POST /attempts
  -> POST /diagnose-pretest
  -> GET /learning-targets
  -> POST /learning-sessions
  -> GET /learning-sessions/{id}
  -> POST /learning-sessions/{id}/prerequisites/{pid}/attempts
  -> POST /learning-sessions/{id}/concept-phase1-attempts
  -> POST /learning-sessions/{id}/concept-phase2-attempts
  -> GET /retest
  -> POST /score-retest
  -> POST /survey post
  -> POST /evaluation-summary/recalculate
  -> GET /admin/export/evaluation_summary.csv
```

## Development Guardrails

- Do not implement an OpenAI API key path
- Do not leak internal labels to participant pages
- Do not let AI decide final metrics
- Do not let app-server failure auto-fallback to Mock in normal mode
- Do not send proposed-only diagnosis/log/return information to control group
- Do not skip CSV export
- Do not store auth tokens

## Minimum Seed Data

- 5 active terms
- `pretest_v2` question per term。旧pretest版は非activeで保持
- formal `retest_v1` per term
- option labels correct/M1/M2/M3/unknown
- pretestのM1〜M3 option rationale
- L0/transfer questions inactive or omitted in current flow
