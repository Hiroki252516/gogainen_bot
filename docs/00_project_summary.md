# 実験の概要と現行仕様

## 仕様版33の現行コード

現行コードは仕様版33 / `experiment-plan-2026-11-01-pretest-content-revision-v2`。通常版PRETESTは`split-actions-v3`へ切り替え、仕様版32のv2から指定されたLLM・マルチエージェント・記憶プロセスの選択肢本文を更新する。RETEST1/2・内部final_testの問題文、6設問の採点と設問ペア答え合わせは維持し、誤答PRETEST設問の学習確認には保存済みsnapshotを使う。仕様版27〜31の`split-actions-v1`と仕様版32のv2、既存参加者記録を履歴復元用に保全し、仕様版32以下は閲覧専用。仕様版28の設問ペア答え合わせ[40](40_question_pair_answer_review.md)、仕様版29のモード[41](41_learning_glossary_material_mode.md)、仕様版30の文字数条件[42](42_learning_glossary_material_length.md)、仕様版31の辞書と言い換え[43](43_glossary_definition_paraphrase.md)、仕様版32のPRETEST改訂[44](44_pretest_content_revision.md)、仕様版33の差分[45](45_pretest_memory_distractors.md)を参照する。受入検証の実行状況は[14](14_testing_acceptance.md)に記録する。

## 仕様版28の採用・易しい版停止時の記録

2026-10-30から易しい版の新規実行を停止した。新規登録は通常版固定、既存易しい版参加者は閲覧専用で、易しい版の群集計・仮説CSVも停止する。参加者・回答・snapshot・評価・易しい版YAMLと問題IDは復元用に保持し、個別ログ・生ログ出力は維持する。詳細は[22](22_question_set_modes.md)と[14](14_testing_acceptance.md)。

通常版のPRETEST・RETEST・内部final_testで、設問1・2の両方を保存した後に同じテスト画面内で選択内容と正誤を示し、続行で次の用語へ進む。設定・API・保存・受入条件は[40](40_question_pair_answer_review.md)を参照する。

この節は仕様版28導入・易しい版停止時点の記録である。当時のprotocolは`experiment-plan-2026-10-30-question-review-v1`。この機能は現行仕様版33でも維持する。仕様版27の採用時記録[39](39_split_assessment.md)は保持し、受入検証の実行状況は[14](14_testing_acceptance.md)に記録する。

## 仕様版26で採用した共通の用語注釈辞書（現行版33でも維持）

以下は採用時点の記録を含む。現在の保存版・readonly境界は冒頭の仕様版33の記述を正とする。

仕様版26で共通固定辞書learning-glossary-v2の16語を導入した。v2は履歴用に無変更で保持し、現在はv3をテスト・回答後解説・教材注釈と教材内解説モードに使う。仕様版31で導入した教材内解説では辞書を意味参照として渡し、本文では定義を逐語転載せず自然に言い換える。教材snapshotや回答後・テストの保存済みsnapshotは更新しない。AI、事前学習、ファインチューニング、プロンプトエンジニアリング、RAG、データベース、マルチエージェント、タスク、記憶プロセスの9語を注釈から除外する。長い除外語の一部からプロンプト・エージェントを抽出せず、独立して登場した場合は補足する。仕様版26の当時は新規だけprotocol_id=`experiment-plan-2026-10-27-test-glossary-v2`を保存し、版25以下を閲覧専用としていた。詳細は[24](24_learning_glossary.md)、[41](41_learning_glossary_material_mode.md)、[42](42_learning_glossary_material_length.md)、[43](43_glossary_definition_paraphrase.md)、版25で採用した問題本文・分類理由は[38](38_round_two_revision.md)。

Word「卒業研究計画書_6.7挿入済み.docx」とユーザー承認済み実装計画を根拠とする。出典・確定判断・残課題は[20](20_experiment_plan_alignment.md)、指標は[12](12_evaluation_metrics.md)。

## 研究と実装

- 比較は履歴を使う通常AIチューター（control）と、明示的診断・修正対象・訂正情報・taxonomy・タイプ別教授方針を追加するAIチューター（proposed）。統制群の自然な誤り訂正を許容する。
- 対象3概念：llm_knowledge、multi_agent、memory_process。大学生40名/各群20名・原則無作為割付を目標とし、アプリは研究者のA/Bコードを使用する。
- 6仮説：初回の正答率の伸び、満点までの用語別セッション数、用語内不正解数、同種誤答再選択率、教材評価、満点到達割合。記述集計のみ。
- backendが固定採点・分類・方略決定を行う。M1/M3/unknown、M3優先。AIは教材・正答要約・誤答解説のみ。
- 共通説明とunknownは意味や仕組みを説明する。unknownは定義・仕組み・教材内適用確認を本文証拠で検査し、旧6項目を必須としない。
- 本文は注釈欄のみで600〜800文字、教材内解説で600〜1200文字。自由な章立て。実験群の本文証拠検査は意味的な正しさや理解の証明ではない。
- アプリ側既定はgpt-6-luna / low。管理画面でgpt-6.1-sol / gpt-6-lunaを一時切替できる。設定はbackendプロセス内だけに保持し、次回呼び出しから両群・進行中参加者に適用、再起動で環境値へ戻る。実験中の変更は同一参加者内のモデル混在を生み得るため、収集時は固定する。研究計画書原本にはgpt-5.6-luna / lowと記載されており、Wordは変更していない。アプリ標準条件との一致を警告・実送信監査で識別する。実AI失敗時にMockへ切り替えない。
- アンケートは経験4有無、一般4/教材6の1〜10、必須自由記述。教材未表示者の6項目は自動対象外。

## 版・保存・フロー

現行コードは新規参加者に仕様版33と`experiment-plan-2026-11-01-pretest-content-revision-v2`を保存する。仕様版32以下、旧protocol_id、NULL・未対応版は閲覧専用で保全する。既存行へ版・protocol・答え合わせ設定・確認時刻・教材解説モードを補完しない。

通常版テストは現行split-actions-v3により、3用語×2設問の6設問・4択単一選択となる。仕様版33ではPRETESTの指定選択肢本文を更新し、RETEST1/2・内部final_testは仕様版32のv2と同じ文面を使う。設問3はデータだけ保持し、activeな問題・表示・採点には使わない。易しい版の従来形式は履歴資産として保持するが、現在の参加者フローでは利用しない。テスト上限・採点・回次は[39](39_split_assessment.md)、仕様版32のPRETEST本文は[44](44_pretest_content_revision.md)、現行差分と版復元は[45](45_pretest_memory_distractors.md)を参照する。答え合わせは通常版のPRETEST・RETEST・内部final_testに適用し、採点は6設問完了後に行う。学習確認には誤答PRETESTの保存済みsnapshotを使う。

material-viewの初回表示時刻から実績を数え、未利用の先行生成を学習回数・教材表示者へ算入しない。新アンケート・指標は版付きJSONへ保存し、旧5段階値や既存評価列を変換しない。

## 開始前の残課題

A〜C正解等の配置はデバッグ用であり収集に使わない。管理者認証・アクセス対策、自動割付/人数上限は今回未実装。承認・同意/撤回・割付の運用と配布設定を別途確認する。実装完了だけで実験開始可能とはしない。

検証結果は[14](14_testing_acceptance.md)、切替・運用は[18](18_implementation_blueprint.md)・[19](19_experiment_operation_runbook.md)。過去の資料・検証・生AIログは書き換えない。

## 易しい版の履歴保全

問題版設定のAPI形状と保存済みquestion_set_modeは後方互換のため維持するが、管理画面は切替を表示せず、GETは通常版を返す。新規登録も保存済みRuntimeSettingがeasyでも通常版に固定する。易しい版の参加者APIによる再開・回答は拒否し、表示のcurrent-stepは閲覧専用を返す。evaluation-summary・logs/overviewの群集計、6仮説CSVはeasy指定を422で拒否する。参加者一覧・個別ログ・参加者別CSV・全件生ログには既存記録を表示する。question_set_mode列、YAML、問題ID、snapshot、DB記録、旧版用の復元対応は変更・削除しない。[停止後の運用と契約](22_question_set_modes.md)・[履歴用問題全文](23_easy_question_bank.md)を参照する。
