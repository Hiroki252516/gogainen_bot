# 16. Implementation Tasks

## Milestone 1: Project Bootstrap

- [ ] Monorepo作成
- [ ] frontend/ Next.js
- [ ] backend/ FastAPI
- [ ] docker-compose.yml
- [ ] PostgreSQL接続
- [ ] Alembic設定
- [ ] Makefile
- [ ] .env.example
- [ ] README更新

## Milestone 2: Database & Seed

- [ ] SQLAlchemy models
- [ ] Alembic migration
- [ ] enum定義
- [ ] terms seed
- [ ] questions seed
- [ ] question_options seed
- [ ] pretest/retest/transfer variants seed
- [ ] seed command
- [ ] question_display_orders実装

## Milestone 3: Core Experiment API

- [ ] participant create
- [ ] current step API
- [ ] pre survey save
- [ ] post survey save
- [ ] pretest questions fetch
- [ ] retest questions fetch
- [ ] l0 questions fetch
- [ ] transfer questions fetch
- [ ] attempt submit
- [ ] idempotency handling
- [ ] admin participant list

## Milestone 4: AI Backend Abstraction

- [ ] AIBackend protocol
- [ ] payload/result schemas
- [ ] MockAIBackend
- [ ] ai_call_logs
- [ ] JSON validation/retry utility
- [ ] CodexAppServer client skeleton
- [ ] app-server health/account read
- [ ] app-server login start/cancel

## Milestone 5: Diagnosis & Learner State

- [ ] choice-based initial diagnosis
- [ ] AI reason-text diagnosis
- [ ] diagnosis merge rules
- [ ] ambiguous/manual review handling
- [ ] initial scaffolding decision
- [ ] learner_state creation
- [ ] learning target selection
- [ ] participant progress update

## Milestone 6: Tutoring Session

- [ ] tutor session create
- [ ] tutor turn generation
- [ ] learner response submit
- [ ] feedback generation
- [ ] forbidden help detection
- [ ] level update
- [ ] strategy change on recurrence
- [ ] max turns per term
- [ ] control group general_explanation behavior

## Milestone 7: Retest / L0 / Transfer

- [ ] retest flow
- [ ] recurrence calculation
- [ ] recurrence_events
- [ ] state update after retest
- [ ] second learning session trigger
- [ ] L0 check flow
- [ ] l0_success calculation
- [ ] transfer test flow
- [ ] M4 detection
- [ ] transfer_success calculation

## Milestone 8: Evaluation & Export

- [ ] evaluation summary calculation
- [ ] group-level aggregate
- [ ] CSV export endpoints
- [ ] export_jobs
- [ ] admin dashboard metrics
- [ ] simple charts
- [ ] manual recalculation API

## Milestone 9: Codex app-server Productionization

- [ ] WebSocket JSON-RPC client
- [ ] initialize
- [ ] account/read
- [ ] login browser/device flow UI
- [ ] thread/start
- [ ] turn/start
- [ ] streaming notification parser
- [ ] outputSchema validation
- [ ] timeout/retry/error handling
- [ ] capability token support
- [ ] provider fallback logging

## Milestone 10: Frontend Completion

- [ ] /start
- [ ] /survey/pre
- [ ] /pretest
- [ ] /diagnosing
- [ ] /learning-targets
- [ ] /learning/[termSlug]
- [ ] /retest
- [ ] /l0-check
- [ ] /transfer-test
- [ ] /survey/post
- [ ] /finish
- [ ] /admin
- [ ] internal label hiding
- [ ] test phase chat disabling

## Milestone 11: Tests & Documentation

- [ ] backend unit tests
- [ ] backend integration tests
- [ ] frontend unit tests
- [ ] E2E happy path
- [ ] proposed/control comparison tests
- [ ] CSV snapshot tests
- [ ] README setup instructions
- [ ] troubleshooting docs

## Implementation Order

必ず以下の順で進める。

1. MockAIBackendで全実験フローを完成させる
2. その後 CodexAppServerBackend をつなぐ
3. app-server接続に詰まっても、研究システム本体は動く状態を維持する

## Do Not Implement Before Requested

このリポジトリ整備段階では、上記タスクは仕様として記録するだけであり、実際のfrontend/backendコードは作成しない。
