# 現行の教材教授

文書名はリンク互換のため維持するが、段階的な支援量の計算・更新は行わない。

M1は「誤った考え → 正しい考え → 反例 → 誤りの理由」。M3は「誤カテゴリー → 正カテゴリー → 境界基準 → 近いカテゴリーとの比較」。unknownは「定義 → 構成要素 → 役割 → 判断基準 → 正例 → 非例」で説明する。

proposed教材は上記の `mandatory_elements` と `teaching_contract` を必須にする。教材内の別事例への適用確認 `transfer_check` は必須であり、独立したテストやAI採点タスクではない。

全群の教材はMarkdown記号を含む600〜800文字、700文字前後。controlは要点・具体例・注意点を中心とした一般説明であり、共通のinteraction_historyを利用し、回答から自然に誤りを訂正してよい。明示的な診断・タイプ別教授方針はproposedだけに追加する。

教授方略は `strategy_for` でbackendが固定し、出力Schemaのenumは当該方略1つのみ。別方略、欠落・不一致、安全性・文字数違反は初回＋最大2回の再生成で検証する。失敗は503にし、Mockへ切り替えない。

`learning_stage` はunknownの `enrichment` とM1/M3の `conceptual_change`、回答後の `final_feedback` を示す。出題制御は両群共通の `shared-diagnosis-route-v1`。controlのモデルへ段階を送らず、proposedの診断介入だけが段階を利用する。

直前の確認問題の解説・振り返りは次の教材へコピーしない。過去の問題・回答の自動prefix追記も行わない。履歴に観察記録を渡すことと、フィードバックを再表示することを分離する。
