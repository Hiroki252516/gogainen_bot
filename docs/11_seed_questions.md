# Seed Questions

問題コンテンツの正本は `backend/app/seed/content/learning_content.yml` である。

`backend/app/seed/content_loader.py` が起動・seed時に形式を検証し、`backend/app/seed/seed_questions.py` がDBへ投入する。

## Active topics

| slug | label | RAG section |
|---|---|---|
| `llm_knowledge` | LLMに知識を与える方法 | 第3章「LLMに知識を与える」 |
| `multi_agent` | マルチエージェント | 第4章「マルチエージェントとは」 |
| `memory_process` | 記憶プロセス | 第5章「記憶プロセス」 |

LangGraphを含む見出し・セクションのチャンクは検索結果から除外する。

## 固定問題の構成

各問題はA〜Jの10選択肢を持つ。

- A〜C: `is_correct: true`
- D〜F: `misconception_type: M1`
- G〜I: `misconception_type: M3`
- J: `misconception_type: unknown`

正解はA/B/Cの3つだけを選択した場合に限定し、Jは単独選択だけを有効とする。YAMLローダーは選択肢数、配分、variant数、LangGraph混入を検証する。

## Variant policy

| phase | 用語ごとの定義 |
|---|---|
| `pretest` | 1問（`pretest_v1`） |
| `retest` | 4問（`retest_v1`〜`retest_v4`）、5回目以降はv4再利用 |
| learning confirmation | 各stage 5問（v1〜v5）、6回目以降はv5再利用 |
| `final_test` | 1問（`final_test_v1`） |

旧Transformerなど既存DB内の問題は削除せず非アクティブ化し、新規seed・新規参加者の導線には含めない。
