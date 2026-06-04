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
- [ ] pretest/retest variants seed
- [ ] seed command
- [ ] question_display_orders実装

## Milestone 3: Core Experiment API

- [ ] participant create
- [ ] current step API
- [ ] pretest questions fetch
- [ ] retest questions fetch
- [ ] l0 questions fetch
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
- [ ] M4 detection

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
- [ ] no-Mock-fallback failure logging

## Milestone 10: Frontend Completion

- [ ] /start
- [ ] /pretest
- [ ] /diagnosing
- [ ] /learning-targets
- [ ] /learning/[termSlug]
- [ ] /retest
- [ ] /l0-check
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

1. Codex app-serverを通常実行のAIバックエンドにする
2. ChatGPT/Codexログイン、`account/read`、`thread/start`、`turn/start` を確認する
3. MockAIBackendは自動テスト・障害切り分け用に明示指定した場合だけ使う
4. app-server接続失敗時はMockへ自動フォールバックせず、失敗ログと管理画面エラーを出す

## Do Not Implement Before Requested

このリポジトリには実装コードも含まれる。仕様整理だけを依頼された場合はMarkdownのみを編集し、実装依頼時だけfrontend/backendコードを変更する。
