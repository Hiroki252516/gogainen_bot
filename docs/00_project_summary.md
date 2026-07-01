# 00. Project Summary

## 現行設計

本システムは、AI・情報系専門用語について「正しい概念を誤概念から弁別できるか」を支援・測定する研究用AIチューターである。現行フローの設計根拠はリポジトリ直下の `initial_retest_final_test_experiment_design_review.md` とする。

比較条件は次の二群である。

- 統制群: 固定前提用語と固定問題を使い、RAGと一般知識から通常教材を生成する。
- 提案群: 同じ固定前提用語と固定問題を使い、初期テスト診断、累積選択履歴、再テスト誤答へ適応して教材・戻り処理を生成する。

## 対象概念

1. Transformer
2. Attention
3. LLMの学習段階
4. 事前学習
5. 事後学習

## 学習セッション

各学習対象は次の2段階で学ぶ。被験者画面では短くL3/L2と表示する。

1. L3（前提用語学習）: 概念ごとに5件、各用語は必須1スロット、各スロット最大3試行
2. L2（概念理解フェーズ1）: AI教材あり、必須2スロット、各スロット最大3試行

全問題はcorrect/M1/M2/M3/unknownの5択で、正誤と誤概念タイプは選択肢メタデータから確定する。AIは教材、誤答説明、正答要点を生成するが、通常時の問題作成と採点は行わない。

## 主評価

- `initial_test_score_all_terms`
- `first_retest_score_all_terms`
- `initial_to_first_retest_gain`
- `retest_loop_count`
- `final_test_score_all_terms`
- `initial_to_final_m_transition`
- `retest_error_m_transition`

事前アンケート、事後アンケート、L0確認、転移テスト、概念フェーズ2は参加者フローでは実施しない。再テストは全5概念を出題し、全問正解まで学習ループを制御する。
