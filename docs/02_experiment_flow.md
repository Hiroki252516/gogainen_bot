# 実験フロー

設計根拠はリポジトリ直下の `initial_retest_final_test_experiment_design_review.md` とする。

```text
/start
  -> /initial-test
  -> /diagnosing
  -> /learning-targets
  -> /learning/[termSlug] ... 学習対象概念を全件実施
  -> /retest
     -> 全5問正解: /final-test
     -> 1問以上不正解/unknown: 不正解概念だけ /learning-targets へ戻す
  -> /final-test
  -> /finish
```

## 初期テスト

- phase: `initial_test`
- active版: `initial_test_v1`
- 全5概念・5択・理由欄なし・自信度なし
- 正答概念は学習対象外
- M1/M2/M3/unknownはすべて学習対象

## 学習セッション

- 前提用語フェーズと概念フェーズ1だけを参加者フローで使う。
- 概念フェーズ2はYAML/DB互換のため残すが、画面・遷移・新分析では使わない。
- 統制群と提案群は同じ固定問題を解く。
- 提案群だけが初期テスト診断、学習履歴、再テスト誤答を教材生成に使う。
- 統制群は同じログを保存するが、教材生成には使わない。

## 再テスト

- phase: `retest`
- active版: `retest_v1`
- 毎回全5概念を出す。
- 1問でも不正解またはunknownなら、不正解概念だけを再学習対象にして新しい `LearningSession` を作る。
- その回の全5問が正解なら最終テストへ進む。
- 正誤や得点は参加者へ表示しない。

## 最終テスト

- phase: `final_test`
- active版: `final_test_v1`
- 全5概念・5択・理由欄なし・自信度なし
- 不正解があっても実験は終了する。
- 得点は参加者へ表示しない。
