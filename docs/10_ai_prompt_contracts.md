# 10. AI Prompt Contracts

## Common Rules

- JSON構造化出力
- 学習者向け文章へM1〜M4を出さない
- RAGを優先し、一般知識補足を別フィールドへ返す
- 固定問題の正答位置、correct option ID、未使用選択肢一覧を渡さない
- 統制群へ事前診断・累積ログ・戻り履歴を渡さない
- 提案群へだけ、内部用の `misconception_taxonomy` と `teaching_guidelines` を渡す
- taxonomyはM1/M2/M3/unknownの定義、診断cue、教材生成指針、避ける支援、研究根拠を含む
- 統制群payloadにはtaxonomyもteaching guidelinesも含めない
- 学習者向けの教材・解説・要点はMarkdown本文で返す。使用できる形式は `##` 見出し、`-` 箇条書き、`**太字**`、短い段落までとし、HTML、表、コードブロック、長大な連続段落は禁止する

## `generate_prerequisite_material`

入力: 対象概念、L3用語、material mode、RAG。提案群だけ診断snapshot、履歴、`misconception_taxonomy`、`teaching_guidelines` を追加。関数名と内部payload keyは互換性のため `prerequisite` 名を維持する。

出力: material、examples、comparisons、counterexamples、rag sources、general knowledge supplement。`material` はMarkdown本文として表示される。

## `generate_concept_phase1_material`

入力: 対象概念、L3用語名、cycle、material mode、RAG。提案群だけ診断、履歴、`misconception_taxonomy`、`teaching_guidelines` を追加。関数名と内部payload keyは互換性のため `concept_phase1` 名を維持する。

出力は教材のみ。問題文や正答を生成しない。`concept_material` はMarkdown本文として表示される。

## `explain_selected_distractor`

現在選択された誤答が不適切な理由と見直す観点をMarkdown本文で返す。提案群ではtaxonomyとteaching guidelinesを内部基準にして、選択肢のMタイプに対応する見直し観点を使う。1〜2回目は正答選択肢本文を返さない。

## `generate_correct_answer_summary`

正答文をそのまま繰り返さず、短いMarkdown要点を返す。

## `generate_emergency_question_variant`

問題バンク枯渇時だけ使用する。提案群ではtaxonomyに基づき、5択、correct/M1/M2/M3/unknownを1件ずつ返し、backend検証後に出題する。

## Leakage Check

AI出力は未使用正答文との完全包含、長い共通部分、正規化類似度0.88以上を検査する。最大3回再生成し、失敗時は `technical_blocked`。
