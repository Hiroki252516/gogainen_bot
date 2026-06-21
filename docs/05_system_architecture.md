# 05. System Architecture

```text
Next.js Frontend
  -> FastAPI
      -> Content Import Service
      -> Learning Session Service
      -> Evaluation / Export Service
      -> AIBackend
  -> SQLite or PostgreSQL

AIBackend
  -> CodexAppServerBackend in normal operation
  -> MockAIBackend in tests only
```

## Content Layer

`experiment_content/` のYAMLをPydanticで検証し、起動時にDBへ同期する。各リリースはfile hash、validation status、active状態を持つ。参加者は開始時点のactive版へ固定される。

## Learning Layer

固定問題の採点と状態遷移はbackendが担当する。AIは教材と説明だけを生成する。旧自由記述API・テーブルは既存データ互換のため残すが、新規学習セッションでは使用しない。

## AIBackend

```python
class AIBackend(Protocol):
    async def diagnose_answer(self, payload: dict) -> dict: ...
    async def generate_prerequisite_material(self, payload: dict) -> dict: ...
    async def generate_concept_phase1_material(self, payload: dict) -> dict: ...
    async def explain_selected_distractor(self, payload: dict) -> dict: ...
    async def generate_correct_answer_summary(self, payload: dict) -> dict: ...
    async def generate_emergency_question_variant(self, payload: dict) -> dict: ...
```

全AI呼び出しを `ai_call_logs` に記録し、Codex app-server障害時にMockへ自動フォールバックしない。
