# 通常版テスト選択肢の文構造整形（仕様版34）

仕様版34 / `experiment-plan-2026-11-01-split-choice-wording-v1`から、新規参加者に通常版テストバンク`split-actions-v4`を適用する。仕様版33の`split-actions-v3`は変更せず、版27〜31はv1、版32はv2、版33はv3、版34はv4で既存記録を復元する。版33以下の参加者は閲覧専用で、保存済みの問題・回答・snapshotを更新しない。

## 適用範囲

添付された比較表`split_assessment_v3_change_comparison.md`の「整形後」に従い、PRETEST・RETEST1・RETEST2の3用語、各設問1〜3にある正解/M1/M3の選択肢本文、合計81項目を更新する。「わからない」の本文は変更しない。選択肢の正誤分類、役割、表示ラベル・順序、問題場面、設問文、4択形式は維持する。

設問3の本文は各回のバンクに保持するが、現行ルールどおり出題・採点・満点判定・学習対象には使わない。通常の6設問と採点、回答後の設問ペア確認、学習対象の決定、教材・AI入力は変更しない。誤答PRETEST設問を学習確認で再提示する場合は、その回答時に保存した問題snapshotを再利用する。

## 履歴と検証データ

v4はv3から作成し、activeバンクは`backend/app/seed/content/standard/split_assessment_v4.yml`に置く。添付比較表の期待文面は`backend/tests/fixtures/split_assessment_v4_expected.yml`に固定し、全81本文の一致、既存バンク構造と正誤分類、v1〜v3の不変性をテストする。問題ID・construct keyを版ごとに分け、再seedしても旧問題・回答・snapshotを上書きしない。

この文書の機械検証は文面一致・バンク構造・復元保全を確認するものであり、選択肢の教育的妥当性、難易度同等性、学習効果を実証しない。受入条件と実行記録は[14](14_testing_acceptance.md)、版管理・実験条件の判断は[20](20_experiment_plan_alignment.md)を参照。
