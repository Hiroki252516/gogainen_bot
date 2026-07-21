# Testing Acceptance

## Backend

- pretestはTransformer 1問だけを返す。
- 問題は10択で、`selection_mode = multiple`、`min_selections = max_selections = 3` を返す。
- A/B/Cのみ選択で正解になる。
- D/E/Fを含む不正解はM1になる。
- G/H/Iを含む不正解はM3になる。
- Jのみ、またはunknown相当のみはunknownになる。
- M1/M3不正解後は `conceptual_change` に進む。
- unknown後は `enrichment` に進む。
- retest/final_testも同じ問題文・選択肢セットを使う。
- evaluation summaryはM1/M3/unknown中心で再計算できる。

## Frontend

- pretest/retest/final-testで複数選択UIが出る。
- 3つ選ばないと送信できない。
- 学習画面に旧ステージ名 `term_understanding` / `concept_understanding` を被験者向け表示しない。
- 管理画面の回答履歴に複数選択回答とM1/M3分類が表示される。

## Regression

- `AI_BACKEND=mock` で全フローが通る。
- `AI_BACKEND=codex_app_server` でMockへ自動フォールバックしない。
- 既存の単一選択API互換を壊さない。
