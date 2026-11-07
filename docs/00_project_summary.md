# 実験の概要と現行仕様

## 仕様版42の現行コード

現行コードは仕様版42 / `experiment-plan-2026-11-07-fixed-admin-settings-learning-material-target-800-control-shared-prompt-v1`。新規参加者は教材内解説、テスト結果非表示、設問ごとの答え合わせON、設問1のみ出題（計3問）に固定する。教材本文は800文字程度を目安とし、文字数の上下限による合否判定や長さを理由にした再生成は行わず、実文字数と目標だけを監査記録に残す。事前アンケートv2（必須8項目）、事後アンケートv3、RAGを含む共通辞書v4、通常版テスト`split-actions-v5`を維持する。管理画面に設定操作、教材モード表示、対応API、集計条件セレクターはなく、旧設定値は参加者登録時に参照しない。履歴値はDB・管理ログAPI・CSVに保持するが、参加者一覧・個別ログ画面には表示しない。教材生成では辞書を両群共通の意味参照として本文中で言い換え、統制群へ群別の自然言語方略指示を加えず、提案群だけに診断・教授方略指示を加える。仕様版41以下と旧protocolは閲覧専用で、既存条件・回答・教材・snapshot・監査記録は変更しない。詳細は[AI指示](10_ai_prompt_contracts.md)、[モード仕様](41_learning_glossary_material_mode.md)、[文字数目標](42_learning_glossary_material_length.md)、[受入記録](14_testing_acceptance.md)。

## 仕様版41の履歴記録

仕様版41には`experiment-plan-2026-11-07-fixed-admin-settings-control-shared-prompt-v1`と`experiment-plan-2026-11-07-learning-material-target-800-control-shared-prompt-v1`の別protocolがある。前者は新規参加者のテスト条件を固定し、後者は本文800文字目標を導入した。どちらも仕様版42へ統合する前の履歴として保持する。

## 仕様版40の履歴記録

仕様版40には`experiment-plan-2026-11-07-fixed-admin-settings-v1`、`experiment-plan-2026-11-07-learning-material-target-800-v1`、`experiment-plan-2026-11-07-control-shared-prompt-v1`の別protocol記録がある。それぞれ設定固定、教材文字数目標、統制群prompt条件の変更を記録し、仕様版42の統合protocolとは区別する。

## 仕様版36の履歴記録

仕様版36には`experiment-plan-2026-11-04-rag-glossary-v1`と`experiment-plan-2026-11-04-presurvey-baseline-v1`の別protocol記録がある。両方とも閲覧専用とし、問題結果は`split-actions-v5`で復元する。RAG注釈を加えた辞書v4と保存済みsnapshotの保全条件は[49_rag_glossary.md](49_rag_glossary.md)を参照する。

## 仕様版33の履歴記録

この履歴節の「現行コード」は、各節に記録した仕様版の時点を指す。

当時の通常版PRETESTは`split-actions-v3`へ切り替え、仕様版32のv2から指定されたLLM・マルチエージェント・記憶プロセスの選択肢本文を更新した。RETEST1/2・内部final_testの問題文、6設問の採点と設問ペア答え合わせは維持し、誤答PRETEST設問の学習確認には保存済みsnapshotを使う。仕様版27〜31の`split-actions-v1`と仕様版32のv2、既存参加者記録を履歴復元用に保全した。仕様版28の設問ペア答え合わせ[40](40_question_pair_answer_review.md)、仕様版29のモード[41](41_learning_glossary_material_mode.md)、仕様版30の文字数条件[42](42_learning_glossary_material_length.md)、仕様版31の辞書と言い換え[43](43_glossary_definition_paraphrase.md)、仕様版32のPRETEST改訂[44](44_pretest_content_revision.md)、仕様版33の差分[45](45_pretest_memory_distractors.md)を参照する。

## 仕様版28の採用記録

通常版のPRETEST・RETEST・内部final_testで、設問1・2の両方を保存した後に同じテスト画面内で選択内容と正誤を示し、続行で次の用語へ進む。設定・API・保存・受入条件は[40](40_question_pair_answer_review.md)を参照する。

当時のprotocolは`experiment-plan-2026-10-30-question-review-v1`。設問ペア確認の契約は現行仕様版42でも維持するが、新規参加者は設問1のみを出題し、回答後に1問を確認する。過去に存在した設定UI/APIは廃止した。仕様版27の採用時記録[39](39_split_assessment.md)は保持し、受入検証の実行状況は[14](14_testing_acceptance.md)に記録する。

## 仕様版26で採用した共通の用語注釈辞書（現行版42でも維持）

以下は採用時点の記録を含む。現在の保存版・readonly境界は冒頭の仕様版42の記述を正とする。

仕様版26で共通固定辞書learning-glossary-v2の16語を導入した。v1〜v3は履歴用に無変更で保持し、現行v4をテスト・回答後解説・教材注釈と教材内解説モードに使う。仕様版31で導入した教材内解説では辞書を意味参照として渡し、本文では定義を逐語転載せず自然に言い換える。仕様版36ではv1のRAG定義・別表記・出典をv4へ追加した。教材snapshotや回答後・テストの保存済みsnapshotは更新しない。AI、事前学習、ファインチューニング、プロンプトエンジニアリング、データベース、マルチエージェント、タスク、記憶プロセスの8語を注釈から除外する。長い除外語の一部からプロンプト・エージェントを抽出せず、独立して登場した場合は補足する。仕様版26の当時は新規だけprotocol_id=`experiment-plan-2026-10-27-test-glossary-v2`を保存し、版25以下を閲覧専用としていた。詳細は[24](24_learning_glossary.md)、[41](41_learning_glossary_material_mode.md)、[42](42_learning_glossary_material_length.md)、[43](43_glossary_definition_paraphrase.md)、版25で採用した問題本文・分類理由は[38](38_round_two_revision.md)。

Word「卒業研究計画書_6.7挿入済み.docx」とユーザー承認済み実装計画を根拠とする。出典・確定判断・残課題は[20](20_experiment_plan_alignment.md)、指標は[12](12_evaluation_metrics.md)。

## 研究と実装

- 比較は履歴を使う通常AIチューター（control）と、明示的診断・修正対象・訂正情報・taxonomy・タイプ別教授方針を追加するAIチューター（proposed）。統制群の自然な誤り訂正を許容する。
- 対象3概念：llm_knowledge、multi_agent、memory_process。大学生40名/各群20名・原則無作為割付を目標とし、アプリは研究者のA/Bコードを使用する。
- 6仮説：初回の正答率の伸び、満点までの用語別セッション数、用語内不正解数、同種誤答再選択率、教材評価、満点到達割合。記述集計のみ。
- backendが固定採点・分類・方略決定を行う。M1/M3/unknown、M3優先。AIは教材・正答要約・誤答解説のみ。
- 共通説明とunknownは意味や仕組みを説明する。unknownは定義・仕組み・教材内適用確認を本文証拠で検査し、旧6項目を必須としない。
- 仕様版39までは本文を注釈欄のみで600〜800文字、教材内解説で600〜1200文字として検証した。仕様版42では目標800文字程度のみを指示し、上下限による合否判定を行わない。自由な章立て。実験群の本文証拠検査は意味的な正しさや理解の証明ではない。
- アプリ側既定はgpt-6-luna / low。管理画面でgpt-6.1-sol / gpt-6-lunaを一時切替できる。設定はbackendプロセス内だけに保持し、次回呼び出しから両群・進行中参加者に適用、再起動で環境値へ戻る。実験中の変更は同一参加者内のモデル混在を生み得るため、収集時は固定する。研究計画書原本にはgpt-5.6-luna / lowと記載されており、Wordは変更していない。アプリ標準条件との一致を警告・実送信監査で識別する。実AI失敗時にMockへ切り替えない。
- アンケートは仕様版36から事前・事後の2フェーズに分け、仕様版37で用語知識を4段階化した。詳細は[49_presurvey_baseline.md](49_presurvey_baseline.md)。

## 版・保存・フロー

現行コードは新規参加者に仕様版42と`experiment-plan-2026-11-07-fixed-admin-settings-learning-material-target-800-control-shared-prompt-v1`を保存する。仕様版41以下、旧protocol_id、NULL・未対応版は閲覧専用で保全する。既存行へ版・protocol・答え合わせ設定・確認時刻・教材解説モードを補完しない。教材内解説モードとテスト条件を固定値として保存し、教材生成は本文800文字程度を目安とする。統制群に群別方略指示を加えず、提案群だけに診断・教授方略指示を追加する。

通常版テストは現行split-actions-v5により、3用語×設問1の計3問・各6択単一選択となる。仕様版35で追加したPRETEST選択肢本文を使用し、RETEST1/2・内部final_testもv5を使う。設問2・3はデータだけ保持し、現行の新規経路では出題・採点しない。テスト上限・採点・回次は[39](39_split_assessment.md)、仕様版32のPRETEST本文は[44](44_pretest_content_revision.md)、現行差分と版復元は[45](45_pretest_memory_distractors.md)を参照する。答え合わせはPRETEST・RETEST・内部final_testに適用し、各問の保存後に選択内容と正誤を示す。学習確認には誤答PRETESTの保存済みsnapshotを使う。

material-viewの初回表示時刻から実績を数え、未利用の先行生成を学習回数・教材表示者へ算入しない。アンケートは事前・事後のphaseと版を付けて既存の版付きJSONへ保存し、DB列を追加しない。旧5段階値・posttest v1/v2・既存評価列を変換しない。

## 開始前の残課題

A〜C正解等の配置はデバッグ用であり収集に使わない。管理者認証・アクセス対策、自動割付/人数上限は今回未実装。承認・同意/撤回・割付の運用と配布設定を別途確認する。実装完了だけで実験開始可能とはしない。

検証結果は[14](14_testing_acceptance.md)、切替・運用は[18](18_implementation_blueprint.md)・[19](19_experiment_operation_runbook.md)。過去の資料・検証・生AIログは書き換えない。

## 問題モードの廃止

現行実装は通常版だけを扱い、版切替の管理UI/API、版別集計、専用資産・分岐はありません。研究DB内の旧条件に関するデータと対応表を削除する場合は、アプリ停止後に[専用削除手順](../backend/scripts/purge_easy_mode_data.py)を明示設定で実行します。起動や通常のseedでデータを削除せず、設定されていない研究DBへの削除処理も実行しません。
