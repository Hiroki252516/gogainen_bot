# 00. Project Summary

## 現行設計

本システムは、AI・情報系専門用語について「正しい概念を誤概念から弁別できるか」を支援・測定する研究用AIチューターである。設計根拠はリポジトリ直下の `fixed_prerequisite_mcq_experiment_design.md` とする。

比較条件は次の二群である。

- 統制群: 固定前提用語と固定問題を使い、RAGと一般知識から通常教材を生成する。
- 提案群: 同じ固定前提用語と固定問題を使い、事前テスト診断と累積選択履歴へ適応して教材・戻り処理を生成する。

## 対象概念

1. Transformer
2. Attention
3. LLMの学習段階
4. 事前学習
5. 事後学習

## 学習セッション

各学習対象は次の3段階で学ぶ。

1. 固定前提用語: 概念ごとに5件、各用語は必須2スロット、各スロット最大3試行
2. 概念フェーズ1: AI教材あり、必須2スロット、各スロット最大3試行
3. 概念フェーズ2: 教材なしの固定5択。提案群は最大3回、統制群は1回

全問題はcorrect/M1/M2/M3/unknownの5択で、正誤と誤概念タイプは選択肢メタデータから確定する。AIは教材、誤答説明、正答要点を生成するが、通常時の問題作成と採点は行わない。

## 主評価

- `pretest_score_all_terms`
- `retest_score_all_terms`
- `learning_target_retest_score`
- `non_target_retest_retention_rate`
- `same_misconception_recurrence_rate`
- `no_material_concept_discrimination_accuracy`

事前アンケート、L0確認、転移テストは実施しない。再テストは学習対象に関係なく全5概念を出題する。
