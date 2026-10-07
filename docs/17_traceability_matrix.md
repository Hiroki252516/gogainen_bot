# 現行要件と実装

| 要件 | backend/appからの実装パス |
| --- | --- |
| 版・閲覧専用 | core/experiment_spec.py、main.py、services/idempotency.py |
| 現行分類と方略 | ai/misconception_taxonomy.py、ai/backend.py |
| 必須教授・適用確認 | ai/mandatory_elements.py、ai/teaching_contract.py |
| 共通履歴と診断除外 | services/interaction_history.py、ai/interaction_history.py |
| 両群共通の診断連動出題 | services/experiment.py |
| 実AI監査・非フォールバック | ai/codex_app_server_backend.py、services/experiment.py |
| 21テスト・30確認問題 | seed/content_loader.py、seed/content/*.yml |
| 採点・ループ・先行生成 | services/experiment.py、services/prefetch.py、services/tutor_prefetch.py |
| 履歴互換 | models/__init__.py、services/legacy_logs.py、db/session.py |
| 仮説1 | score_timeline_jsonのtest/retest_1 |
| 仮説2 | learning_burden_json |
| 仮説3 | recurrence_events、misconception_timeline_json |

旧対応表はhistory資料として残し、現行実行範囲へ混ぜない。
