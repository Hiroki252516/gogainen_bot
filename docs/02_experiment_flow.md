# Experiment Flow

今回のMVPはTransformer単独で実施する。比較対象は通常AIチューターとログ適応型AIチューターであり、提案群だけが誤概念タイプ、過去ログ、足場掛け履歴を教授方略に使う。

1. 事前テストでTransformerのA〜Iの9択から3つ選択、またはJ「わからない」単独選択問題を出す。
2. A/B/C完全一致なら正解とし、最終テストへ進める。
3. 不正解がM1/M3なら学習セッションの `conceptual_change` に進める。
4. Jのみのunknownなら `enrichment` に進める。
5. 学習内確認で正解すれば `final_feedback`、不正解ならM1/M3は `conceptual_change`、unknownは `enrichment` に遷移する。
6. 再テスト・最終テストも事前テストと同じ問題文・選択肢セットを使う。

M2/M4、RNN逐次処理系、スライド37の古い判定ルールは今回のMVPから外す。
