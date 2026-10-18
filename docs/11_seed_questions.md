# 現行問題バンク

計画書の目標も問題本文・選択肢・採点基準を事前に用意し、AIに生成・採点させない。以下の21問/30問・variant数は現行バンクの内訳であり今回変更しない。問題と教材の役割、再テスト回次と評価上の比較回次を区別する。[計画書対応表](20_experiment_plan_alignment.md) を参照する。

テスト系は `backend/app/seed/content/learning_content.yml`、学習確認は `learning_questions_v2.yml`。

3用語ごとに事前1・再5・最終1の計21問。新規seedはこの21問だけを作る。廃止フェーズ・旧variantは非activeにするだけで削除しない。旧追加選択肢も参照保全のため残し、現行出題はA〜Jに限定する。seed再実行で参加者記録を削除しない。

学習確認は現行v2の3用語×2意味的stage×5問=30問。適用・予測・比較・境界判断・事例診断を扱う。DB質問テーブルへseedせず提示時にTutorTurn.practice_question_jsonへ保存する。旧v1の出題/採点はない。

両群とも同じ診断連動規則でstageを選ぶ。unknownはenrichment、M1/M3はconceptual_change、variantは同じturn_indexに従う。旧統制群の固定conceptual_change系列を使わない。問題本文・選択肢・採点データは変更しない。

全問A〜C正解・D〜F=M1・G〜I=M3・J=unknownのデバッグ配置を維持する。正解3つの完全選択とM3優先を維持し、判定はメタデータを使う。問題文・選択肢内容は変更しない。

teaching_targetsに研究者確認済み訂正・仕組み・対比・M3境界を保存する。observed_claimは選択肢本文から取得する。Jには対象主張を作らない。

長さ、同文コピー、役割数、場面形式を検証する。旧固定教材文や位置回転設定は実行YAMLに残さない。研究データ収集前に別作業で正解位置の分散を戻す。
