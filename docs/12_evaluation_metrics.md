# 現行評価ログ

既存の評価式・統計手法は再設計しない。再計算・群集計対象は仕様版2だけ。NULL・版1・未対応版は保存済み評価を閲覧/CSV出力し、値を再計算しない。

- pretest_score: 採点済み事前回答の正答率。
- retest_score: 再テスト回答の正答率。初回比較には周回JSONを使用。
- attainment_correct_rate: final_testがあればその正答率、なければ最新の再テスト全問正解バッチの正答率。is_correctを使用。
- same_misconception_recurrence_rateとM1/M3別再発率: 既存の事前誤答・再発に基づく算式を維持。
- score_timeline_json: test/retest_1/retest_2以降と事前比差分。
- misconception_timeline_json: 用語別の解消・同種再発・別タイプ化等。
- learning_burden_json: セッション、回答ターン、再テスト周回、時間。未利用の先行生成を負担に数えない。
- condition_check_json: 群別方略の使用、最終到達の測定元。

仮説1は初回の伸び、仮説2はループ、仮説3は同種誤答再発。初期正答、途中中断、測定経路・試行機会は区別する。到達率を全員共通の同一時点事後評価とみなさない。

attainment_correct_rateの物理保存先は旧l0_correct_rate列。廃止評価・支援量・方略変更量を算出しない。旧値はlegacy_fieldsへ隔離し再計算しない。統合ログCSVの固定ヘッダと生AIログは保持する。
