# 11. Experiment Content

固定コンテンツはPython定数ではなく `experiment_content/` のYAMLで管理する。

## Release

- schema: 1
- release: `experiment_content_v1`
- validation: `provisional`
- initial_test: `initial_test_v1`
- retest: `retest_v1`
- final_test: `final_test_v1`

## Learning Bank

各概念:

- 前提用語5件
- 各前提用語: 必須2スロット×3バリアント
- フェーズ1: 必須2スロット×3バリアント×3サイクル
- フェーズ2: 3バリアント
- 合計51問

全5概念で255問。全問correct/M1/M2/M3/unknownの5択で、誤答選択肢には診断理由、改善観点、主要な戻り先前提用語を持たせる。

## Retest v2

初期テスト、再テスト、最終テストは同じ5構成概念を別文面で測る。再テストは学習対象だけに限定せず全5概念を出し、全問正解まで学習ループ判定に使う。旧pretest/retest版は非activeで保持する。

## Validation

- active releaseは一意
- keyとvariant keyは一意
- 各問題は5択、正答1件
- M1/M2/M3/unknownが各1件
- linked prerequisite keyが同一概念内に存在
- 必要スロット・バリアント数を満たす
- participant UIへ内部ラベルを出さない

本実験前に専門家2名以上の独立確認と、対象者に近い5〜10名による認知インタビューを行う。
