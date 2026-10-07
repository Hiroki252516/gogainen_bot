# 現行分類

taxonomy版: `m1-m3-unknown-v2`。正本は `backend/app/ai/misconception_taxonomy.py`。

| 分類 | 意味 | backend指定方略 |
| --- | --- | --- |
| M1 | 単一の誤った命題を選んだ記録 | `belief_revision` |
| M3 | 本来と異なるカテゴリーとして扱った記録 | `category_reorientation` |
| unknown | J単独選択など知識不足 | `foundational_explanation` |
| control | 共通回答履歴を使うがbackendの明示的診断・教授方針は受け取らない | `general_explanation` |

理解状態は `stable_correct`、`misconception`、`unknown` だけを新規処理で生成する。正解記録の `stable_correct_count` は維持する。

採点は選択肢メタデータに基づく。正解3つならstable_correct、誤答にM3があればM3、次にM1を優先し、J単独はunknown。同じ判定を事前・再・最終・学習確認へ適用する。

`pretest_targets` は選択された誤答全件、`pretest_target` は現在タイプに合う主対象。選択肢本文を正本にし、訂正・仕組み・対比例はYAMLの `teaching_targets` を使う。unknownに具体的な誤信念を捏造しない。

廃止分類の定義は実行時taxonomyへ含めない。歴史的分類・過去の記録は [旧文書](history/2026-10-06/03_misconception_taxonomy.md) に隔離する。
