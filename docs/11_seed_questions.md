# 現行問題バンク

2026-10-30以降、通常版だけを新規参加者へ出題する。易しい版YAML・問題・snapshot・旧参加者記録は履歴復元のため保持するが、通常の新規・継続フローでは使用しない。seedが過去easy問題を削除・書換えしないことは維持する。[停止後の運用](22_question_set_modes.md)。

計画書の目標も問題本文・選択肢・採点基準を事前に用意し、AIに生成・採点させない。テスト系の固有問題9問を用語別の学習確認にも共用し、学習ターンのsnapshotと採点はテスト回答とは区別して保存する。[計画書対応表](20_experiment_plan_alignment.md) を参照する。

仕様版26では問題本文・問題IDを変更せず版25のバンクを維持する。旧仕様版25の結果復元にもscenario-actions-v9を指定する。

通常版のテスト・学習確認は`backend/app/seed/content/standard/`、易しい版の履歴復元用ファイルは`backend/app/seed/content/easy/`に保持する。旧30問バンクは`backend/app/seed/content/archive/learning_questions_v2_unused.yml`へ保存し、通常の問題としては使用しない。

3用語ごとに事前1・再2のテスト問題をactiveなYAMLへ保持する。内部final_testは独立問題を持たず、retest_v1を使用する。retest_v4・v5と旧final_test_v1はアーカイブとして保全する。

通常版テストは仕様版25で3用語の再テストV2を改訂したscenario-actions-v9の内容を維持する。LLMは大学・教職員版を採用している。事前・再テストV1・内部final_testと訂正情報も維持する。旧v8はarchive/learning_content_scenario_actions_v8.ymlへ保全し、旧仕様版24の結果はv8から復元する。[全文と保存契約](38_round_two_revision.md)。

旧学習確認v15は履歴復元用に保持する。現行版の新規ターンはテストバンクのpretest_v1/retest_v1（確認3はretest_v2）を使うため、学習用の独立した本文・選択肢は参照しない。旧v14以前も保持する。[学習v14の採用時記録](35_multi_memory_round_one_revision.md)・[版25の採用時記録](38_round_two_revision.md)。

現行の学習確認は各用語でセッション1をpretest_v1、セッション2をretest_v1へ対応させる。enrichmentとconceptual_changeは同じ問題本文・選択肢を使い、教材生成プロンプトだけが変わる。同一セッションの各用語について確認問題への回答は1回とし、誤答後も解説を表示して次へ進む。現行の上限では3セッション目に到達しない。確認3は隔離検証・復元互換のためretest_v2へ対応させる。

通常経路の最大はテスト9問＋学習6問＝15固有問題、採点回答イベントはテスト9＋学習18＝27回。事前満点経路では学習が最大1周となり、テスト9＋学習3＝12固有問題、採点回答イベント18回である。

問題バンクのcanonicalな内部ラベルは、A〜C正解・D〜F=M1・G〜I=M3・J=unknownのデバッグ配置で管理する。管理画面のdebug_fixedではこの並びを表示する。randomizedでも「わからない」は最後のJへ固定し、残る9択をA〜Iへ決定的に再配置する。再配置は問題ごとに固定され、全参加者・両群で共通、アプリ再起動後も変わらない。学習確認にも同じテストバンクの選択肢配置規則を適用し、旧学習YAMLのsnapshotは書き換えない。

teaching_targetsの訂正・仕組み・対比例・M3境界を新事前選択肢へ合わせる。旧問題全12固有問と教授対象は`archive/learning_content_pre_issue156.yml`に原文のまま保全する。新しいconstruct_keyで別Question/QuestionOptionを作り、旧DB問題は削除せず非activeにする。snapshot・旧回答・教材・評価は書き換えず、seed再実行でも新問題を重複作成しない。

## 通常版と履歴用バンクの保持

通常版の旧学習YAMLと履歴用v3・v5・v6・v7・v8・v9・v10・v11・v12・v13・v14は`standard/`に保持する。易しい版の`easy/learning_content_easy.yml`と旧学習YAMLも変更せず保持するが、現行参加者にはseed選択・出題・教材生成しない。現行の学習確認は通常版テストバンクの同用語pretest_v1/retest_v1（確認3はretest_v2）から組み立てる。易しい版資産は過去の参加者記録の参照・復元用。通常版・履歴用バンクの選択肢検査は非空・重複・役割数・教授対象を維持し、文長の均一性は保証しない。個別の旧誤答理由・教授対象は[23](23_easy_question_bank.md)、保存・seed方針は[22](22_question_set_modes.md)を参照する。

旧scenario-actions-v1/v2/v3/v4/v5/v6/v7/v8の原文・教授対象をarchive/learning_content_scenario_actions_v1.yml・v2.yml・v3.yml・v4.yml・v5.yml・v6.yml・v7.yml・v8.ymlへ保全する（各ファイル名の共通接頭辞は同じ）。現行v9は別IDの12行をseedし、旧通常版は非activeにする。旧通常版1バンク＋易しい版だけを持つDBなら更新後は計36行、旧通常版が複数あれば保全済みバンクごとに12行ずつ多くなる。activeは24行、新DBも24行。さらに古い問題も削除しない。旧版6〜25の結果復元は当時のバンク識別子で行い、新版へ置き換えない。

同文再使用は通常版学習v15のLLM V1/V2のE・Gと、通常版テストv9のLLM再テストV1/V2のFだけに限定する。本文・用語・variant_key・内部ラベルが合う組だけを許可し、同一問題内・指定外の重複と確認問題への固定テスト文の転載は拒否する。旧版と易しい版の検査は緩めない。
