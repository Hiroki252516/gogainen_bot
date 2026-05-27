# 05. System Architecture

## 推奨アーキテクチャ

```text
Browser
  ↓
Next.js Frontend
  ↓ REST / SSE
FastAPI Backend
  ↓
Application Services
  ├─ Experiment Service
  ├─ Diagnosis Service
  ├─ Tutoring Service
  ├─ Scaffolding Service
  ├─ Evaluation Service
  └─ Export Service
  ↓
PostgreSQL
  ↓
AIBackend Interface
  ├─ CodexAppServerBackend
  └─ MockAIBackend
  ↓
Codex app-server
  ↓
ChatGPT/Codex Login
```

## コンテナ構成

### frontend

- Next.js
- TypeScript
- Tailwind CSS

### backend

- FastAPI
- SQLAlchemy
- Pydantic
- Alembic
- websockets / subprocess

### db

- PostgreSQL 16系
- volume永続化

## AIBackend抽象化

AI呼び出しは必ず抽象化する。

```python
class AIBackend(Protocol):
    async def diagnose_answer(self, payload: DiagnosisPayload) -> DiagnosisResult: ...
    async def generate_tutoring_turn(self, payload: TutoringPayload) -> TutoringResult: ...
    async def grade_response(self, payload: GradingPayload) -> GradingResult: ...
    async def generate_feedback(self, payload: FeedbackPayload) -> FeedbackResult: ...
```

実装:

- `MockAIBackend`: テスト・CI用。決定論的に返す。
- `CodexAppServerBackend`: Codex app-serverを使う。

OpenAI APIキーを直接使う実装は作らない。

## app-server起動方式

### 方式A: host codex app-server

Macホスト上でCodexをログイン・起動する。backendコンテナから `host.docker.internal` 経由で接続する。MVPではこの方式を優先する。

### 方式B: codex sidecar container

Codex CLIを含むコンテナを起動し、device code flowでChatGPTログインする。実験的。認証・ブラウザ連携・トークン保存で詰まりやすいため後回し。
