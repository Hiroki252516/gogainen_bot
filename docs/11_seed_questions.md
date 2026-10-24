# 現行問題バンク

計画書の目標も問題本文・選択肢・採点基準を事前に用意し、AIに生成・採点させない。テスト系の固有問題9問と、現行学習確認バンクの9問を区別する。[計画書対応表](20_experiment_plan_alignment.md) を参照する。

テスト系は backend/app/seed/content/learning_content.yml、学習確認は learning_questions_v3.yml。旧30問バンクは learning_questions_v2_unused.yml へ保存し、通常の問題としては使用しない。

3用語ごとに事前1・再2のテスト問題をactiveなYAMLへ保持する。内部final_testは独立問題を持たず、retest_v1を使用する。retest_v4・v5と旧final_test_v1はアーカイブとして保全する。

通常版（実験仕様版7 / scenario-actions-v1）ではpretest_v1、retest_v1/v2のみをactiveにする。LLM知識は製品サポート・問い合わせ分類・議事録作成の承認済み3案を文面どおり使用する。他2用語は既存場面を基に行動選択型へ更新した。全文と分類根拠・妥当性の限界は[21](21_assessment_action_questions.md)を参照する。事前後のテストはfinal_test込み2回までで、final_test後はretest_v2を使い、未回答用語も全体回次に合わせる。

学習確認v3は3用語×3学習セッションvariant=9問である。各用語は学習セッション1でlearning_round_v1、2でlearning_round_v2、3でlearning_round_v3を使う。enrichmentとconceptual_changeは同じ問題本文・選択肢を使い、教材生成プロンプトだけが変わる。同一セッション内の誤答時は同じ問題で最大3回答し、教材だけを再生成する。問題内容は変更しないが、現行の上限では3セッション目に到達しない。

通常経路の最大はテスト9問＋学習6問＝15固有問題、採点回答イベントはテスト9＋学習18＝27回。事前満点経路では学習が最大1周となり、テスト9＋学習3＝12固有問題、採点回答イベント18回である。

問題バンクのcanonicalな内部ラベルは、A〜C正解・D〜F=M1・G〜I=M3・J=unknownのデバッグ配置で管理する。管理画面のdebug_fixedではこの並びを表示する。randomizedでも「わからない」は最後のJへ固定し、残る9択をA〜Iへ決定的に再配置する。再配置は問題ごとに固定され、全参加者・両群で共通、アプリ再起動後も変わらない。選択肢配置はlearning_questions_v3.ymlの9問にも適用する。

teaching_targetsの訂正・仕組み・対比例・M3境界を新事前選択肢へ合わせる。旧問題全12固有問と教授対象はlearning_content_pre_issue156.ymlに原文のまま保全する。新しいconstruct_keyで別Question/QuestionOptionを作り、旧DB問題は削除せず非activeにする。snapshot・旧回答・教材・評価は書き換えず、seed再実行でも新問題を重複作成しない。

## 通常版と易しい版の並行保持

通常版の2 YAMLは変更しない。易しい版のlearning_content_easy.ymlとlearning_questions_v4_easy.ymlを別バンクとして追加し、各版にテスト9固有問・学習確認9問を持つ。両版は同時にactiveで、参加者の固定版で絞る。easyの文長下限は非空、比1.8以下・差32以下とし、standardの20文字下限は維持する。個別の誤答理由・教授対象は[23](23_easy_question_bank.md)、保存・seed件数は[22](22_question_set_modes.md)を参照する。
