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
  "test_round": "test",
  "test_round_label": "テスト",
  "options": []
}
```

`selected_option_ids: string[]` を正本とし、既存互換の `selected_option_id` も残す。A〜Iから3件ちょうど、またはJのみ1件を必須とする。JとA〜Iの混在は不可とする。

## Variant policy

- pretest: 用語ごとに `pretest_v1`
- retest: `retest_v1`〜`retest_v4`。5回目以降はv4を再利用
- learning: stage・用語ごとにv1〜v5。6回目以降はv5を再利用
- final_test: 用語ごとに `final_test_v1`

`variant_key` は既存DBの `questions.variant_key` と互換に保存する。

再テストの採点対象が現行の3用語を各1問ずつ含み、すべて正解だった場合は、`score-retest` が `next_step=survey`、`next_url=/survey` を返して追加の確認を省略する。不正解または未回答がある場合は、`next_step=learning_targets`、不正解・未回答用語の優先度順を入れた `learning_target_slugs`、最初の用語への `next_url=/learning/{term_slug}` を返す。`final_test` も全問正解時だけ `survey` へ進み、不正解または未回答時は次の再テスト周回の学習セッションへ戻る。対象一覧が空の異常時も `next_url=/learning-targets` に留める。最終確認省略後、非満点再テスト後、または不正解・未回答の `final_test` 後の関連APIは `409` を返す。`final_test` の参加者向け表示名は「再テスト1」である。

`attempts.test_round` には初回 `pretest` を `test`、最初の学習後確認を `retest_1`、次周回を `retest_2` のように保存する。`attempts.phase` は `pretest`、`retest`、`final_test` の内部値として互換維持する。

現行の主なAPIルートは `/api/health`、`/api/participants`、`/api/experiment/{experiment_id}/pretest|retest|l0-check|final-test`、`/api/attempts`、`/api/participants/{participant_id}/diagnose-pretest`、`/api/tutor-sessions`、`/api/tutor-turns/{turn_id}/respond`、`/api/participants/{participant_id}/evaluation-summary/recalculate`、`/api/admin/*` である。管理画面から `DELETE /api/admin/participants/{participant_id}` を呼ぶと、対象参加者と関連する実験データを完全削除し、削除操作の監査記録だけを残す。frontendの `/api/*` はNext.jsのrewriteでbackendへ転送する。

`GET /api/participants/{participant_id}/learning-targets` は、`current_step`、既存の未達対象一覧、事前テスト後の互換用 `pretest_results`、直近のテスト結果 `test_results` を返す。`pretest_results` は3用語を表示順に含み、`term_slug`、`term_label`、`is_correct`、`result_label`、`result_summary`、`is_learning_target` を持つ。`test_results` は `test_round`、`test_round_label`、`results` を持ち、各結果に `term_slug`、`term_label`、`question_body`、`selected_options`（`label` と `body` のみ）、`is_correct`、`result_label`、`is_learning_target` を含める。`test_results` は保存済みの問題文・選択内容・正誤を参加者向けに投影したものであり、`correct_answer`、`expected_answer`、選択肢ごとの `is_correct`、M分類などの内部診断値は含めない。結果は保存済み `Attempt.is_correct` を正本とする。`targets` は優先度・用語表示順で並び、学習開始先を決める未達用語の一覧として維持する。`current_step=learning_targets` のとき、対象が空でも最終テストへの導線を返さない。

## Scoring

A/B/Cの3つだけを選択した場合だけ正解。不正解分類はM3を最優先し、次にM1、J単独または判定材料なしはunknownとする。採点・遷移はbackendが決定し、AI出力で上書きしない。

## Learning API

`learning_stage` は既存の内部値 `enrichment`、`conceptual_change`、`final_feedback` を使う。教材生成時は用語・段階・固定確認問題・共通RAG本文を両群へ渡す。proposedだけがログ・taxonomy・足場掛け情報を追加で受け取る。

学習ターン回答APIのレスポンスには `item_results` フィールドを残すが、現行の固定複数選択フローでは空配列になる。個別項目結果を返す自由回答フローは将来または互換用である。
