# Backend API Spec

## Question Payload

新規seedの対象は `llm_knowledge`、`multi_agent`、`memory_process` の3用語である。pretest、retest、final_test、l0_checkの固定問題はYAMLから読み込む。

```json
{
  "question_id": "uuid",
  "term_slug": "llm_knowledge",
  "term_label": "LLMに知識を与える方法",
  "variant_key": "pretest_v1",
  "question_type": "multi_select",
  "selection_mode": "multiple",
  "min_selections": 3,
  "max_selections": 3,
  "requires_reason": false,
  "options": []
}
```

`selected_option_ids: string[]` を正本とし、既存互換の `selected_option_id` も残す。A〜Iから3件ちょうど、またはJのみ1件を必須とする。JとA〜Iの混在は不可とする。

## Variant policy

- pretest: 用語ごとに `pretest_v1`
- retest: `retest_v1`〜`retest_v4`。5回目以降はv4を再利用
- learning: stage・用語ごとにv1〜v5。6回目以降はv5を再利用
- final_test: 用語ごとに `final_v1`

`variant_key` は既存DBの `questions.variant_key` と互換に保存する。

## Scoring

A/B/Cの3つだけを選択した場合だけ正解。不正解分類はM3を最優先し、次にM1、J単独または判定材料なしはunknownとする。採点・遷移はbackendが決定し、AI出力で上書きしない。

## Learning API

`learning_stage` は既存の内部値 `enrichment`、`conceptual_change`、`final_feedback` を使う。教材生成時は用語・段階・固定確認問題・共通RAG本文を両群へ渡す。proposedだけがログ・taxonomy・足場掛け情報を追加で受け取る。
