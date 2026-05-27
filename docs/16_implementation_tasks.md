# 16. Implementation Tasks

## Milestone 1: Project Bootstrap

- [ ] Monorepo作成
- [ ] frontend/ Next.js
- [ ] backend/ FastAPI
- [ ] docker-compose.yml
- [ ] PostgreSQL接続
- [ ] Alembic設定
- [ ] README更新

## Milestone 2: Database & Seed

- [ ] SQLAlchemy models
- [ ] Alembic migration
- [ ] terms seed
- [ ] questions seed
- [ ] option labels seed
- [ ] seed command

## Milestone 3: Core Experiment API

- [ ] participant create
- [ ] pre survey save
- [ ] pretest questions fetch
- [ ] attempt submit
- [ ] current step API
- [ ] admin participant list

## Milestone 4: AI Backend Abstraction

- [ ] AIBackend protocol
- [ ] MockAIBackend
- [ ] CodexAppServer client skeleton
- [ ] app-server health/account read
- [ ] diagnosis API with mock
- [ ] ai_call_logs

## Milestone 5: Diagnosis & Learner State

- [ ] choice-based initial diagnosis
- [ ] AI reason-text diagnosis
- [ ] initial scaffolding decision
- [ ] learner_state creation
- [ ] learning target selection

## Milestone 6: Tutoring Session

- [ ] tutor session create
- [ ] tutor turn generation
- [ ] learner response submit
- [ ] feedback generation
- [ ] level update
- [ ] strategy change on recurrence

## Milestone 7: Retest / L0 / Transfer

- [ ] retest flow
- [ ] recurrence calculation
- [ ] L0 check flow
- [ ] transfer test flow
- [ ] M4 detection

## Milestone 8: Evaluation & Export

- [ ] evaluation summary calculation
- [ ] CSV export
- [ ] admin dashboard metrics
- [ ] simple charts

## Milestone 9: Codex app-server Productionization

- [ ] WebSocket JSON-RPC client
- [ ] initialize/initialized
- [ ] account/read
- [ ] login browser/device flow UI
- [ ] thread/start
- [ ] turn/start
- [ ] streaming notification parser
- [ ] outputSchema validation
- [ ] retry/error handling

## Implementation Order

必ず以下の順で進める。

1. MockAIBackendで全実験フローを完成させる
2. その後 CodexAppServerBackend をつなぐ
3. app-server接続に詰まっても、研究システム本体は動く状態を維持する
