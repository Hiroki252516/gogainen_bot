# 誤概念分類

M1〜M4は、誤概念を学習者の知識構造上の粒度で分類する内部taxonomyである。実行時にAIへ渡す定義は `backend/app/ai/misconception_taxonomy.py` にあり、この文書は研究上の説明と固定問題の判定規則を定める。

| ラベル | 名称 | 本質的定義 | 教材生成・支援の指針 |
| --- | --- | --- | --- |
| M1 | 誤信念型 | 単一の命題・信念が誤っている。 | 誤った信念を明示的または対比的に反証し、正しい命題へ置き換える。 |
| M2 | 欠陥メンタルモデル型 | 複数の信念がつながった説明モデル全体が不整合である。 | 中核前提を特定し、複数の信念と関係を順に修正してモデル全体を再構成する。 |
| M3 | カテゴリー誤り型 | 概念を本来とは異なる上位カテゴリーに分類している。 | まず誤カテゴリーへの気づきを促し、正しいカテゴリーの特徴と境界を示して再分類する。 |
| M4 | 欠如したスキーマ型 | 必要なカテゴリー・関係・手続きの知識構造が不足している。 | 不足している構成要素を明示し、新しいスキーマを例・関係・適用場面とともに構築する。 |
| unknown | 知識不足 | 判断に必要な基礎知識が不足している、または「わからない」を選んでいる。 | 誤概念と決めつけず、用語・構成要素・基本例を優先して説明する。 |

AIには研究名やMラベルを被験者向け本文へ出力させない。controlにはtaxonomyを渡さず、一般的な説明だけを生成させる。

## 固定問題の判定

各用語のpretest、retest、final_test、learning確認問題はYAMLで管理する。

| 選択肢 | 付与タイプ |
| --- | --- |
| A, B, C | 正解 |
| D, E, F | M1 |
| G, H, I | M3 |
| J | unknown |

正解はA/B/Cの3つだけを選択した場合に限定する。Jと他の選択肢の同時選択は不正解とする。誤答に複数タイプが含まれる場合はM3を最優先し、M3がなくM1を含む場合はM1、どちらもなければ知識不足として扱う。

M2/M4は固定問題の選択肢には含めないが、将来の診断・教材生成とDB互換のため内部taxonomyに保持する。

## 教材生成用taxonomyの版と対象主張

実行時taxonomyの版は `backend/app/ai/misconception_taxonomy.py` の `TAXONOMY_VERSION` で管理する。既存参加者へ付与済みの `Attempt.is_correct`、`diagnosed_status`、`misconception_type` は再採点せず、新規教材生成時のpayloadに版を記録する。

提案群のM1/M3教材はタイプ名だけでなく、事前テストで選択された誤答選択肢を問題バンクの `teaching_targets` から復元する。選択を確定した信念とは断定せず、次の構造で教授目標へ渡す。

```json
{
  "claim_id": "llm_knowledge:pretest:E",
  "observed_claim": "選択肢本文",
  "corrected_claim": "研究者確認済みの訂正文",
  "mechanism_explanation": "誤りが生じる仕組み",
  "contrast_example": "正しい仕組みとの対比例",
  "evidence_source": "pretest_selected_option",
  "interpretation": "observed_choice_not_confirmed_belief"
}
```

複数の誤答を選択した場合は `pretest_targets` に全対象を入れ、`pretest_target` は主対象として扱う。J「わからない」だけの回答には対象主張を作らず、unknownの基礎説明方略を使う。M1は誤った命題・訂正・仕組み・対比例・転移確認、M3は誤カテゴリー・正カテゴリー・境界・対比例・転移確認を必須とし、unknownは反駁せず定義・構成要素・役割・正例・非例を説明する。

学習中に新たなM1/M3が診断されても、事前テストに同じタイプの研究者確認済みtargetがなければ具体的なclaimを創作しない。この場合は `target_claim_id=null`、`addressed_claim_ids=[]` の一般的なM1/M3教材契約として検証し、事前テストで別タイプだったclaimを混在させない。unknownでは、残っているM1/M3の事前テストtargetをAIの教授対象から除外する。
