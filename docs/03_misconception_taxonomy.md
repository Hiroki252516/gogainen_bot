# 分類と教授方針

実験計画書と承認された実装計画に沿うM1/M3/unknown。現行taxonomy版はm1-m3-unknown-v3、実装は[misconception_taxonomy.py](../backend/app/ai/misconception_taxonomy.py)。

| 分類 | 選択記録としての意味 | 方略 | 目標の教授内容 |
| --- | --- | --- | --- |
| M1 | 概念の働き・仕組みに関する個別の主張の誤り | belief_revision | 誤った主張と正しい説明、反例、誤りの理由・仕組み。明示的反駁を標準とする |
| M3 | 対象を本来とは異なる種類のものと捉える誤り | category_reorientation | 誤分類と正分類、区別する判断基準、対比例 |
| unknown | J単独選択など、特定の誤った主張を修正対象に置けない回答 | foundational_explanation | 特定の誤概念を仮定せず意味や仕組みを説明する |
| control | 共通履歴による通常説明。backendの診断・タイプ別指針は受け取らない | general_explanation | 共通情報から学習対象を説明し、自然な誤り訂正も許容する |

unknownの旧6項目必須指定は撤廃した。定義はmandatory_elements.definition、仕組み・適用確認は既存teaching_contractのmechanism_explanation/transfer_checkから本文内出現を検査する。unknownは誤概念の不存在や知識欠如の確定診断ではない。

## 固定判定と教授への利用

正解3つだけの完全選択ならstable_correct、誤答にM3があればM3、次にM1、J単独はunknown。同じ判定を事前・再・最終・学習確認へ適用する。理解状態はstable_correct/misconception/unknownのみで、正答記録のstable_correct_countを維持する。

M3優先はカテゴリーの取り違えを先に扱うという本研究の操作上の規則。Chiがこの10択問題の優先判定を直接検証したわけではない。[出典上の注意](99_sources_and_notes.md) を参照する。

両群でbackendが分類し、出題制御・評価に利用する。実験群だけのLLMへ診断とタイプ別指針を渡し、参加者には内部分類・群・方略を表示しない。統制群が回答本文から自然に誤りを推測・訂正することは禁止しない。

## 入力と検査用項目の区別

- pretest_targets: 実際に選択された事前誤答のうちM1/M3で訂正メタデータがあるもの。未選択の全誤答を渡すものではない。
- pretest_target: 現在タイプに合う主対象。対象がなければnull。
- diagnostic_evidence.selected_options: その用語の事前テストで選んだ選択肢。正答やJも含み得る。学習中の最新回答そのものとは別。
- 訂正・仕組み・対比例はYAMLのteaching_targetsから渡す。RAGの共通資料とも区別する。
- mandatory_elements.wrong_belief / wrong_category: 本文で誤った主張・分類を説明した文章をコピーする出力JSONキー。教授方略でも新たな分類名でもない。

選択記録を確定した信念と扱わず、記録にない個人の誤概念を創作しない。検査用のコピーは本文内出現を確かめるためであり、意味の正しさを保証しない。廃止分類を現行の定義・目標へ追加せず、旧資料はhistoryに保持する。
