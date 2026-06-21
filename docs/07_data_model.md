# 07. Data Model

## Content Tables

- `content_versions`: content type、version key、source file、file hash、validation status、active
- `prerequisite_definitions`: 対象概念、key、label、表示順、セット版
- `learning_question_slots`: stage、前提用語、slot key、cycle、順序
- `learning_questions`: slot、variant、attempt index、本文、source type、validation status
- `learning_question_options`: 本文、correct、Mタイプ、診断理由、戻り先、改善観点

## Session Tables

- `learning_sessions`: participant、term、group、固定版、現在stage/前提用語/slot/attempt/cycle、技術停止、phase2 forced completion
- `learning_session_prerequisites`: セッションへ展開した固定前提用語と進捗
- `generated_learning_materials`: 教材全文、mode、RAG、一般知識補足、漏洩検査、AI call
- `learning_choice_attempts`: 問題、選択肢、表示順、正誤、Mタイプ、遷移、forced、response time
- `learning_question_display_orders`: 参加者・学習問題ごとの固定表示順

## Status

- session: `prerequisite`, `prerequisite_review`, `concept_phase1`, `concept_phase2`, `completed`, `technical_blocked`
- slot result: `pending`, `retry`, `passed`, `forced_resolved`
- question source: `predefined_codex`, `runtime_ai_fallback`

旧 `prerequisite_terms`, `term_understanding_attempts`, `concept_understanding_attempts` は互換保持するが、新規選択式フローでは書き込まない。

## Versioning

参加者に `content_version_id` を固定する。既存参加者は次回アクセス時にactive版を遅延固定する。進行中セッションはactive版変更の影響を受けない。
