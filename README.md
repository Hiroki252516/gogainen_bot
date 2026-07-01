# 学習ログ駆動型AIチューター仕様

本リポジトリは、通常AIチューターとログ適応型AIチューターを比較する卒業研究用Webアプリの仕様・実装です。

## 現行フロー

1. `/start`: 参加同意と群条件の設定
2. `/initial-test`: 初期テスト。全5概念・5択・理由欄なし・自信度なし
3. `/diagnosing`: 初期テスト結果から、正答以外の概念を学習対象にする
4. `/learning-targets` と `/learning/[termSlug]`: 学習対象ごとに、L3（前提用語学習）とL2（概念理解フェーズ1）を実施
5. `/retest`: 再テスト。全5概念を出題し、1問でも不正解またはunknownなら不正解概念だけ再学習へ戻す
6. `/final-test`: 再テストで全5問正解後に実施する最終テスト
7. `/finish`: 実験終了

事前アンケート、事後アンケート、L0確認、転移テスト、概念フェーズ2は参加者フローでは実施しない。

## 主な評価

- `initial_test_score_all_terms`
- `first_retest_score_all_terms`
- `initial_to_first_retest_gain`
- `retest_loop_count`
- `retest_relearning_target_count`
- `final_test_score_all_terms`
- `initial_to_final_m_transition`
- `retest_error_m_transition`

主評価は「初期テストから初回再テストへの伸び」。再テストループ回数、Mタイプ推移、最終テスト結果は補助分析に使う。

## 実行

通常のAI応答は `AIBackend` 経由で行う。OpenAI APIキーやOpenAI SDK直呼びは使わず、通常実行ではCodex app-serverを利用する。
