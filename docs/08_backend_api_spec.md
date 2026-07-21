# Backend API Spec

## Question Payload

Transformerのテスト問題は複数選択で返す。

```json
{
  "question_id": "uuid",
  "term_slug": "transformer",
  "term_label": "Transformer",
  "body": "Transformerについて、適切だと思うものをすべて選びなさい。",
  "question_type": "multi_select",
  "selection_mode": "multiple",
  "min_selections": 3,
  "max_selections": 3,
  "requires_reason": false,
  "options": []
}
```

## POST /api/attempts

`selected_option_ids: string[]` を追加する。既存互換のため `selected_option_id` も残す。複数選択問題では3件ちょうどを必須とする。

```json
{
  "participant_id": "uuid",
  "question_id": "uuid",
  "phase": "pretest",
  "selected_option_ids": ["uuid-a", "uuid-b", "uuid-c"]
}
```

採点はA/B/C完全一致のみ正解。不正解分類はM3優先、次にM1、unknownのみならunknown。

## Learning Stage

`learning_stage` は `enrichment`、`conceptual_change`、`final_feedback` を返す。統制群も同じステージ名をログに残すが、教授方略は `general_explanation` に固定する。
