# 実験の概要と現行仕様

## 仕様版43の現行コード（2026-11-08）

新規参加者は`experiment-plan-2026-11-08-basic-understanding-question-mode-v1`で登録する。管理画面の問題モード設定を登録時に固定し、現行版（場面応用、`split-actions-v5`）または基礎理解版（`split-actions-basic-v1`）を使用する。既定値は現行版。出題数、答え合わせ、結果表示、事前アンケート、教材・教授・採点条件は仕様版42のまま引き継ぐ。6仮説は問題モード別に集計し、モード間を合算しない。仕様版42以下と旧protocolは閲覧専用、既存記録は不変。基礎理解版の難易度低下・難易度同等性・研究上の承認は未検証・未確認。[詳細](50_basic_understanding_question_mode.md)。

## 仕様版42の履歴コード

仕様版42当時は`experiment-plan-2026-11-07-fixed-admin-settings-learning-material-target-800-control-shared-prompt-v1`を使用した。新規参加者は教材内解説、テスト結果非表示、設問ごとの答え合わせON、設問1のみ出題（計3問）に固定した。教材本文は800文字程度を目安とし、文字数の上下限による合否判定や長さを理由にした再生成は行わず、実文字数と目標だけを監査記録に残した。事前アンケートv2（必須8項目）、事後アンケートv3、RAGを含む共通辞書v4、通常版テスト`split-actions-v5`を使用した。問題モード設定はなく、教材生成では辞書を両群共通の意味参照として本文中で言い換え、統制群へ群別の自然言語方略指示を加えず、提案群だけに診断・教授方略指示を加えた。仕様版42以下の保存記録は閲覧専用として保持し、仕様版43で変更しない。詳細は[AI指示](10_ai_prompt_contracts.md)、[モード仕様](41_learning_glossary_material_mode.md)、[文字数目標](42_learning_glossary_material_length.md)、[受入記録](14_testing_acceptance.md)。

## 仕様版41の履歴記録

仕様版41には`experiment-plan-2026-11-07-fixed-admin-settings-control-shared-prompt-v1`、`experiment-plan-2026-11-07-learning-material-target-800-control-shared-prompt-v1`、`experiment-plan-2026-11-07-split-actions-v6-q1-only-v1`の別protocolがある。最初の二つは通常版バンクv5、三つ目は設問1のみのバンクv6を使った。仕様版42への統合後はいずれも履歴として保持し、回答復元ではprotocol IDに応じてバンクを選ぶ。

## 仕様版40の履歴記録

仕様版40には`experiment-plan-2026-11-07-fixed-admin-settings-v1`、`experiment-plan-2026-11-07-learning-material-target-800-v1`、`experiment-plan-2026-11-07-control-shared-prompt-v1`の別protocol記録がある。それぞれ設定固定、教材文字数目標、統制群prompt条件の変更を記録し、仕様版42の統合protocolとは区別する。

## 仕様版36の履歴記録

仕様版36には`experiment-plan-2026-11-04-rag-glossary-v1`と`experiment-plan-2026-11-04-presurvey-baseline-v1`の別protocol記録がある。両方とも閲覧専用とし、問題結果は`split-actions-v5`で復元する。RAG注釈を加えた辞書v4と保存済みsnapshotの保全条件は[49_rag_glossary.md](49_rag_glossary.md)を参照する。

## 仕様版33の履歴記録

この履歴節の「現行コード」は、各節に記録した仕様版の時点を指す。

当時の通常版PRETESTは`split-actions-v3`へ切り替え、仕様版32のv2から指定されたLLM・マルチエージェント・記憶プロセスの選択肢本文を更新した。RETEST1/2・内部final_testの問題文、6設問の採点と設問ペア答え合わせは維持し、誤答PRETEST設問の学習確認には保存済みsnapshotを使う。仕様版27〜31の`split-actions-v1`と仕様版32のv2、既存参加者記録を履歴復元用に保全した。仕様版28の設問ペア答え合わせ[40](40_question_pair_answer_review.md)、仕様版29のモード[41](41_learning_glossary_material_mode.md)、仕様版30の文字数条件[42](42_learning_glossary_material_length.md)、仕様版31の辞書と言い換え[43](43_glossary_definition_paraphrase.md)、仕様版32のPRETEST改訂[44](44_pretest_content_revision.md)、仕様版33の差分[45](45_pretest_memory_distractors.md)を参照する。

## 仕様版28の採用記録

通常版のPRETEST・RETEST・内部final_testで、設問1・2の両方を保存した後に同じテスト画面内で選択内容と正誤を示し、続行で次の用語へ進む。設定・API・保存・受入条件は[40](40_question_pair_answer_review.md)を参照する。

当時のprotocolは`experiment-plan-2026-10-30-question-review-v1`。設問ペア確認の契約は現行仕様版43でも維持するが、新規参加者は選択した問題モードの設問1のみを出題し、回答後に1問を確認する。過去に存在した設定UI/APIは廃止した。仕様版27の採用時記録[39](39_split_assessment.md)は保持し、受入検証の実行状況は[14](14_testing_acceptance.md)に記録する。

## 仕様版26で採用した共通の用語注釈辞書（現行版43でも維持）

以下は採用時点の記録を含む。現在の保存版・readonly境界は冒頭の仕様版43の記述を正とする。

仕様版26で共通固定辞書learning-glossary-v2の16語を導入した。v1〜v3は履歴用に無変更で保持し、現行v4をテスト・回答後解説・教材注釈と教材内解説モードに使う。仕様版31で導入した教材内解説では辞書を意味参照として渡し、本文では定義を逐語転載せず自然に言い換える。仕様版36ではv1のRAG定義・別表記・出典をv4へ追加した。教材snapshotや回答後・テストの保存済みsnapshotは更新しない。AI、事前学習、ファインチューニング、プロンプトエンジニアリング、データベース、マルチエージェント、タスク、記憶プロセスの8語を注釈から除外する。長い除外語の一部からプロンプト・エージェントを抽出せず、独立して登場した場合は補足する。仕様版26の当時は新規だけprotocol_id=`experiment-plan-2026-10-27-test-glossary-v2`を保存し、版25以下を閲覧専用としていた。詳細は[24](24_learning_glossary.md)、[41](41_learning_glossary_material_mode.md)、[42](42_learning_glossary_material_length.md)、[43](43_glossary_definition_paraphrase.md)、版25で採用した問題本文・分類理由は[38](38_round_two_revision.md)。

Word「卒業研究計画書_6.7挿入済み.docx」とユーザー承認済み実装計画を根拠とする。出典・確定判断・残課題は[20](20_experiment_plan_alignment.md)、指標は[12](12_evaluation_metrics.md)。

## 研究と実装

- 比較は履歴を使う通常AIチューター（control）と、明示的診断・修正対象・訂正情報・taxonomy・タイプ別教授方針を追加するAIチューター（proposed）。統制群の自然な誤り訂正を許容する。
- 対象3概念：llm_knowledge、multi_agent、memory_process。大学生40名/各群20名・原則無作為割付を目標とし、アプリは研究者のA/Bコードを使用する。
- 6仮説：初回の正答率の伸び、満点までの用語別セッション数、用語内不正解数、同種誤答再選択率、教材評価、満点到達割合。記述集計のみ。
- backendが固定採点・分類・方略決定を行う。M1/M3/unknown、M3優先。AIは教材・正答要約・誤答解説のみ。
- 共通説明とunknownは意味や仕組みを説明する。unknownは定義・仕組み・教材内適用確認を本文証拠で検査し、旧6項目を必須としない。
- 仕様版39までは本文を注釈欄のみで600〜800文字、教材内解説で600〜1200文字として検証した。仕様版42では目標800文字程度のみを指示し、上下限による合否判定を行わない。自由な章立て。実験群の本文証拠検査は意味的な正しさや理解の証明ではない。
- アプリ側既定はgpt-6-luna / low。管理画面でgpt-6.1-sol / gpt-6-luna / gpt-6-astraとlow/medium/high/xhigh/maxを一時切替できる。設定はbackendプロセス内だけに保持し、次回呼び出しから両群・進行中参加者に適用、再起動で環境値へ戻る。実験中の変更は同一参加者内のモデル混在を生み得るため、収集時は固定する。研究計画書原本にはgpt-5.6-luna / lowと記載されており、Wordは変更していない。アプリ標準条件との一致を警告・実送信監査で識別する。実AI失敗時にMockへ切り替えない。
- アンケートは仕様版36から事前・事後の2フェーズに分け、仕様版37で用語知識を4段階化した。詳細は[49_presurvey_baseline.md](49_presurvey_baseline.md)。

## 版・保存・フロー

現行コードは新規参加者に仕様版43と`experiment-plan-2026-11-08-basic-understanding-question-mode-v1`を保存する。仕様版42以下、旧protocol_id、NULL・未対応版は閲覧専用で保全する。既存行へ版・protocol・答え合わせ設定・確認時刻・教材解説モード・問題モードを補完しない。教材内解説モードと問題モードを登録時に固定し、教材生成は本文800文字程度を目安とする。統制群に群別方略指示を加えず、提案群だけに診断・教授方略指示を追加する。詳細は[問題モード仕様](50_basic_understanding_question_mode.md)。

通常版テストは登録時snapshotされた問題モードにより、`split-actions-v5`または`split-actions-basic-v1`から各用語の設問1、計3問・各6択単一選択を出す。現行版の設問2・3と基礎理解版の事前/再テスト各回の問題データは保持するが、新規経路では出題・採点しない。内部final_testは各モードのretest1を使い、学習確認には直前テストで誤答した問題の保存済みsnapshotを使う。テスト上限・採点・回次は[39](39_split_assessment.md)、旧問題本文は[44](44_pretest_content_revision.md)以降の履歴を参照する。答え合わせはPRETEST・RETEST・内部final_testに適用し、各問の保存後に選択内容と正誤を示す。

material-viewの初回表示時刻から実績を数え、未利用の先行生成を学習回数・教材表示者へ算入しない。アンケートは事前・事後のphaseと版を付けて既存の版付きJSONへ保存し、DB列を追加しない。旧5段階値・posttest v1/v2・既存評価列を変換しない。

## 開始前の残課題

A〜C正解等の配置はデバッグ用であり収集に使わない。管理者認証・アクセス対策、自動割付/人数上限は今回未実装。承認・同意/撤回・割付の運用と配布設定を別途確認する。実装完了だけで実験開始可能とはしない。

検証結果は[14](14_testing_acceptance.md)、切替・運用は[18](18_implementation_blueprint.md)・[19](19_experiment_operation_runbook.md)。過去の資料・検証・生AIログは書き換えない。

## 問題モードの廃止

仕様版43では新規参加者の`test_content_mode`に応じて`split-actions-v5`または`split-actions-basic-v1`を使う。管理設定は新規参加者だけに適用し、登録済みParticipantの問題・回答・snapshotを切り替えない。旧`question_set_mode`列・APIの削除は以前のeasy-mode整理に関する履歴であり、このモード設定・問題資産を削除対象にしない。版付きconstruct keyと保存snapshotから当時の問題を復元し、異なるバンクへフォールバックしない。研究DB内の旧条件に関するデータを削除する操作は、専用手順・明示設定を確認して扱い、起動や通常seedから削除しない。
