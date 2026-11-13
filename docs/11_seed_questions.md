# 現行問題バンクと履歴

## 現行条件（仕様版54）

新規参加者はParticipantに固定された`test_content_mode`に応じて、`split-actions-v5`（現行版）、`split-actions-basic-v1`（基礎理解版）、`split-actions-four-topic-v3`（4用語版）を使う。4用語版v3ではLLM学習段階の用語を「インストラクションチューニング」とし、問題文・選択肢・提案群の教材生成用情報も合わせる。設問数、選択肢の役割、採点、配置、確認問題での保存snapshot再利用は変更しない。v1は仕様版49以下、v2は仕様版50の対応protocolと仕様版51/52のissue338系protocol、v3は仕様版51/52のissue336系protocolの復元用に保持し、別のconstruct keyで各バンクをseedする。現行仕様版55ではv3を使う。詳細は[51](51_four_topic_foundation_mode.md)。

## 仕様版48の条件（履歴）

仕様版48当時の参加者はParticipantに固定された`test_content_mode`に応じて、`split-actions-v5`（現行版）、`split-actions-basic-v1`（基礎理解版）、`split-actions-four-topic-v1`（4用語版）を使った。application/basic_understandingは各3問、four_topic_fundamentalsは4問を出題した。事前テスト満点者は全モードで学習と再テストを省略して事後アンケートへ進んだ。4用語版の事前未達者は再テスト1後も学習し、再テスト2へ進んだ。事前アンケートの対象用語は問題モードに応じて固定していた。これは仕様版48の履歴であり、現行の出題条件は冒頭を参照する。

## 仕様版46の4用語版（履歴）

仕様版46の4用語版は`four_topic_fundamentals_v1.yml`を使った。問題本文・選択肢・分類・正答は変更せず、4用語版だけ満点後も学習を続けていた。事前・再テスト1後に誤答対象がない場合は4用語すべてを通常学習の対象にし、再テスト2の採点後は正誤にかかわらずsurveyへ進んだ。他の問題モードは満点時に早期終了できた。これは仕様版46の履歴である。

## 仕様版44・45の4用語版（導入・既定値変更の履歴）

仕様版44の新規登録ではsnapshotした`test_content_mode`に応じて問題バンクを選ぶ。未設定時は4用語版を適用し、保存済みRuntimeSetting値は変更しない。第3モード`four_topic_fundamentals`は独立バンク`split-actions-four-topic-v1`（`four_topic_fundamentals_v1.yml`）を使い、Transformer、LLMの学習段階、マルチエージェント、記憶プロセスを各1問・10択で出題した。A〜C正解、D〜F=M1、G〜I=M3、J=unknownとし、3択またはJ単独で採点した。仕様版46で事前・再テスト1/2を同一問題・選択肢とし、4用語版に内部final_testがなかった。仕様版48まで問題バンク・採点・回答後snapshotの再利用を維持し、事前満点者の進行は仕様版47で導入した早期終了に従った。仕様版50では独立バンクv2を使う。現行バンクの詳細は[4用語版仕様](51_four_topic_foundation_mode.md)を参照する。役割メタデータ・教授対象は参加者向けAPIへ含めない。

## 仕様版43の問題モード（導入時・履歴）

新規参加者は管理設定を登録時に固定し、現行`split-actions-v5`または基礎理解`split-actions-basic-v1`を使う。仕様版43の新規出題は両モードとも各用語の設問1のみ計3問で、再テスト1/2・内部final_test・学習確認も参加者の選択モードを維持する。基礎理解版YAMLには3回次×3用語の計9問を保持し、各問に正解1・M1二つ・M3二つ・unknown一つを置く。問題ID・construct keyは別にseedし、保存snapshotを優先する。問題の全文と研究上の注意は[50](50_basic_understanding_question_mode.md)。

仕様版43の新規登録・出題・採点・学習確認は登録snapshotされた問題モードに従う。`application`は`split-actions-v5`、`basic_understanding`は独立バンク`split-actions-basic-v1`を使う。管理切替は新規参加者にだけ適用し、履歴復元は当時の仕様版・protocol・保存snapshotを基準にする。

## 仕様版42の履歴バンク

新規参加者はsplit-actions-v5を使い、PRETEST・RETEST1/2・内部final_testでは各用語の設問1だけ、計3問に回答する。バンクv5には設問1〜3を保持するが、新規参加者には設問1のみを提示する。各問の回答後に本人の選択内容と正誤を同じテスト画面内で示し、テスト全体の結果確認画面は表示しない。

## 仕様版41のV6履歴バンク

`experiment-plan-2026-11-07-split-actions-v6-q1-only-v1`はsplit-actions-v6を使い、新規参加者に各用語の設問1だけを出題した。V6はPRETEST・RETEST1/2の設問1にある指定9選択肢を改訂し、研究者向け理由を保存する。理由欄は参加者向け出題JSONへ含めない。V6には設問1だけを収録し、設問2・3はV5以前の履歴バンクに保持する。このprotocolの結果はprotocol IDを用いてV6から復元する。仕様版41の他protocolと仕様版40以下は当時の条件・snapshotを保全し、変更しない。

計画書の目標も問題本文・選択肢・採点基準を事前に用意し、AIに生成・採点させない。テスト系の固有問題9問を用語別の学習確認にも共用し、学習ターンのsnapshotと採点はテスト回答とは区別して保存する。[計画書対応表](20_experiment_plan_alignment.md) を参照する。

仕様版26当時は問題本文・問題IDを変更せず版25のバンクを維持した。旧仕様版25の結果復元にもscenario-actions-v9を指定した。

通常版のテスト・学習確認は`backend/app/seed/content/standard/`を使う。旧30問バンクは`backend/app/seed/content/archive/learning_questions_v2_unused.yml`へ保存し、通常の問題としては使用しない。

3用語ごとに事前1・再2のテスト問題をactiveなYAMLへ保持する。内部final_testは独立問題を持たず、retest_v1を使用する。retest_v4・v5と旧final_test_v1はアーカイブとして保全する。

仕様版25の通常版テストは、3用語の再テストV2を改訂したscenario-actions-v9を使用した。LLMは大学・教職員版を採用していた。事前・再テストV1・内部final_testと訂正情報も当時の条件を維持した。旧v8はarchive/learning_content_scenario_actions_v8.ymlへ保全し、旧仕様版24の結果はv8から復元する。[全文と保存契約](38_round_two_revision.md)。

旧学習確認v15は履歴復元用に保持する。現行版の新規ターンはテストバンクのpretest_v1/retest_v1（確認3はretest_v2）を使うため、学習用の独立した本文・選択肢は参照しない。旧v14以前も保持する。[学習v14の採用時記録](35_multi_memory_round_one_revision.md)・[版25の採用時記録](38_round_two_revision.md)。

現行の学習確認は各用語でセッション1をpretest_v1、セッション2をretest_v1へ対応させる。enrichmentとconceptual_changeは同じ問題本文・選択肢を使い、教材生成プロンプトだけが変わる。同一セッションの各用語について確認問題への回答は1回とし、誤答後も解説を表示して次へ進む。現行の上限では3セッション目に到達しない。確認3は隔離検証・復元互換のためretest_v2へ対応させる。

通常経路の最大はテスト9問＋学習6問＝15固有問題、採点回答イベントはテスト9＋学習18＝27回。事前満点経路では学習が最大1周となり、テスト9＋学習3＝12固有問題、採点回答イベント18回である。

問題バンクのcanonicalな内部ラベルは、A〜C正解・D〜F=M1・G〜I=M3・J=unknownのデバッグ配置で管理する。管理画面のdebug_fixedではこの並びを表示する。randomizedでも「わからない」は最後のJへ固定し、残る9択をA〜Iへ決定的に再配置する。再配置は問題ごとに固定され、全参加者・両群で共通、アプリ再起動後も変わらない。学習確認にも同じテストバンクの選択肢配置規則を適用し、旧学習YAMLのsnapshotは書き換えない。

teaching_targetsの訂正・仕組み・対比例・M3境界を新事前選択肢へ合わせる。旧問題全12固有問と教授対象は`archive/learning_content_pre_issue156.yml`に原文のまま保全する。新しいconstruct_keyで別Question/QuestionOptionを作り、旧DB問題は削除せず非activeにする。snapshot・旧回答・教材・評価は書き換えず、seed再実行でも新問題を重複作成しない。

## 通常版と履歴用バンク

通常版の旧学習YAMLと履歴用v3・v5・v6・v7・v8・v9・v10・v11・v12・v13・v14は`standard/`に保持する。現行の学習確認は通常版テストバンクの同用語pretest_v1/retest_v1（確認3はretest_v2）から組み立てる。選択肢検査は非空・重複・役割数・教授対象を維持し、文長の均一性は保証しない。

旧scenario-actions-v1/v2/v3/v4/v5/v6/v7/v8の原文・教授対象をarchive/learning_content_scenario_actions_v1.yml・v2.yml・v3.yml・v4.yml・v5.yml・v6.yml・v7.yml・v8.ymlへ保全する（各ファイル名の共通接頭辞は同じ）。仕様版25当時はv9を別IDの12行としてseedし、旧通常版を非activeにした。さらに古い問題も削除しない。旧版6〜25の結果復元は当時のバンク識別子で行い、新版へ置き換えない。

同文再使用は通常版学習v15のLLM V1/V2のE・Gと、通常版テストv9のLLM再テストV1/V2のFだけに限定する。本文・用語・variant_key・内部ラベルが合う組だけを許可し、同一問題内・指定外の重複と確認問題への固定テスト文の転載は拒否する。
