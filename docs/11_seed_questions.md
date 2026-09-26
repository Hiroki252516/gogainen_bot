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

pretest、retest、final_testと学習確認の固定複数選択問題はA〜Jの10選択肢を持つ。`l0_check`の自由回答と`transfer`の互換問題は別形式である。

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
| learning confirmation | `enrichment` / `conceptual_change`の各stageで5問（v1〜v5）、6回目以降はv5再利用 |
| `final_test` | 1問（`final_test_v1`） |

学習確認問題はDBの`questions`へseedしない。`generate_tutor_turn`がYAMLのstage・用語別定義から固定の確認問題・選択肢を組み立て、AI生成教材とともに`tutor_turns.practice_question_json`へ保存する。L3/L2は問題stageではなく、内部の`scaffolding_level`互換値である。

学習確認のvariantは、学習セッション内で新しく取得した教材の順に`v1`、`v2`、`v3`を使う。誤答後に`learning_stage`が変わってもこの順序をリセットしない。現行の標準フローでは1用語あたり3回目の不正解で次の学習対象へ進むため、`v4`、`v5`は将来の上限設定や既存ログ互換のために保持する。現在の問題への回答結果表示は新しい教材取得ではないため、画面の用語進捗分子を進めない。

旧Transformerなど既存DB内の問題は削除せず非アクティブ化し、新規seed・新規参加者の導線には含めない。
