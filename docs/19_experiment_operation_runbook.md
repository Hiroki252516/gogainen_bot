# 19. Experiment Operation Runbook

## Before Experiment

1. Start `codex app-server --listen ws://127.0.0.1:4500`.
2. Start the application with Docker Compose.
3. Confirm `/api/admin/ai/status`.
4. Run content validation/import and confirm active `experiment_content_v1`.
5. Confirm `pretest_v2`, 255 learning questions, and `retest_v2`.
6. Do not use MockAIBackend for experiment data.

## Participant Flow

1. Start and consent
2. Pretest
3. Diagnosis
4. Learning targets
5. Fixed prerequisite / phase1 / phase2 learning sessions
6. All-five retest
7. Post survey
8. Finish

## Technical Failure

- Do not show the question without its required material.
- Do not create a duplicate answer attempt.
- Show a retry action.
- Check `ai_call_logs`, app-server login, RAG files, and content validation.
- Never automatically switch to Mock.

## After Experiment

- Recalculate evaluation summary.
- Export all content, attempt, material, AI, transition, and summary CSVs.
- Verify participant content versions and source types.
- Keep provisional/approved status available for analysis.
