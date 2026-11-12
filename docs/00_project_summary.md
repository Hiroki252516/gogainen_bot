# 実験の概要と現行仕様

## 仕様版51の現行コード（2026-11-12）

新規参加者は仕様版51 / `experiment-plan-2026-11-12-perfect-test-early-exit-v1`で登録する。事前・再テスト・内部`final_test`で必要な全設問が採点済みかつ全問正解なら、問題モードを問わず事後アンケートへ進み、学習・後続テストを省略する。4用語版の再テスト1満点時も固定学習対象を作らない。結果表示設定がONなら結果確認後、OFFなら直接surveyへ進む。未達時の学習・再テスト経路は維持する。3モード、問題バンク、事前アンケート`presurvey-baseline-v4`／`presurvey-four-topic-baseline-v3`、事後アンケート`posttest-5point-v2`、H1〜H6の定義・分母・欠測規則は変更しない。仕様版50以下の記録は閲覧専用で保全する。測定特性や研究上の承認は未確認。[実験フロー](02_experiment_flow.md)、[事前アンケート](49_presurvey_baseline.md)、[4用語版](51_four_topic_foundation_mode.md)、[事後アンケート](52_posttest_five_point_evaluation.md)、[評価指標](12_evaluation_metrics.md)、[受入記録](14_testing_acceptance.md)。

## 仕様版48の履歴条件（2026-11-10）

新規参加者は仕様版48 / `experiment-plan-2026-11-10-presurvey-exposure-understanding-split-v1`で登録した。`application`、`basic_understanding`、`four_topic_fundamentals`の3モード、登録時snapshot、4用語版の問題・確認問題を維持した。事前アンケートは6用語の見聞き経験を尋ね、「ある」のときだけ理解度を追加回答した。AI利用頻度は直近30日の日数、使いこなしは3行動の自己評価で取得した。通常2モードは`presurvey-baseline-v3`、4用語版は`presurvey-four-topic-baseline-v2`で保存し、理解度を尋ねない場合はnullとした。事前テスト満点者は、表示設定ONなら結果確認後、OFFなら直接事後アンケートへ進み、学習・内部`final_test`・再テストを行わない。未達者は従来どおり誤答用語だけを学習する。4用語版の事前未達経路では、再テスト1後の学習・再テスト2までの固定フローを維持した。早期終了者は`pretest_perfect_early_exit`として別集計し、H1/H2/H6は対象外として適用分母と対象外数を示す。H3〜H5の対象外規則を維持した。仕様版47以下・旧protocolは閲覧専用で既存記録を変更しない。[事前アンケート](49_presurvey_baseline.md)、[4用語版](51_four_topic_foundation_mode.md)、[評価指標](12_evaluation_metrics.md)。

## 仕様版46の履歴条件（2026-11-09）

仕様版46 / `experiment-plan-2026-11-09-four-topic-default-two-retests-v1`では、4用語版の事前テスト満点後も学習し、再テスト1・2へ進んだ。仕様版47で事前満点時の経路を変更した。仕様版46以下の回答・教材・snapshotは当時の内容で保全する。

## 仕様版45の履歴条件（2026-11-09）

仕様版45には二つのprotocolがある。`experiment-plan-2026-11-09-four-topic-two-retest-rounds-v1`は現行版を既定とし、4用語版のみ満点後も再テスト2まで学習を続けた。`experiment-plan-2026-11-09-four-topic-foundation-default-v1`は未設定時の既定を4用語版にした。両protocolとも保存済みモードを変更せず、参加者ごとに登録時snapshotした。既存データはprotocol別に復元する。

## 仕様版44の導入時コード（履歴）

仕様版44 / `experiment-plan-2026-11-09-four-topic-foundation-v1`で4用語版を導入した。各用語1問・4問・10択とし、満点時は他モードと同じ早期終了条件だった。仕様版45で既定値変更と固定2回フローを別protocolとして導入した。仕様版44の問題・回答・snapshotは保存時の内容を保つ。

## 仕様版43当時のコード（履歴・2026-11-08）

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

当時のprotocolは`experiment-plan-2026-10-30-question-review-v1`。設問ペア確認の履歴契約は現行仕様版51でも復元互換性のため保持するが、新規参加者は選択した問題モードの対象設問を出題し、各問の回答後に確認する。過去に存在した設定UI/APIは廃止した。仕様版27の採用時記録[39](39_split_assessment.md)は保持し、受入検証の実行状況は[14](14_testing_acceptance.md)に記録する。

## 仕様版26で採用した共通の用語注釈辞書（現行仕様版51でも維持）

以下は採用時点の記録を含む。現在の保存版・readonly境界は冒頭の仕様版51の記述を正とする。

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

現行コードは新規参加者に仕様版51のprotocolを保存し、仕様版50以下のprotocol・NULLや未対応版は閲覧専用で保全する。登録時snapshot、テスト・学習・採点・表示設定、教材条件は直前の現行条件を引き継ぐ。4用語版の現行問題バンクは`split-actions-four-topic-v2`、事前アンケートは標準2モードが`presurvey-baseline-v4`、4用語版が`presurvey-four-topic-baseline-v3`、事後アンケートは`posttest-5point-v2`。事前回答は事後アンケート・仮説指標へ合算しない。教材生成は本文800文字程度を目安とし、統制群に群別方略指示を加えず、提案群だけに診断・教授方略指示を追加する。

現行版・基礎理解版は各用語の設問1、計3問・各6択単一選択、4用語版は4問・各10択で正解3つまたはJ単独を選択する。必要な全設問が採点済みで全問正解なら、全モードで事前・再テスト後に学習・後続テストを省略して事後アンケートへ進む。4用語版も再テスト1満点後は固定学習対象を設定しない。未達の場合は問題モードに応じた誤答用語を学習し、再テスト2まで進む。内部`final_test`は過去記録の復元用に維持し、新規参加者の通常経路では使用しない。学習確認には直前テストで誤答した問題の保存済みsnapshotを使う。回答後は選択内容と選択肢別・設問全体の正誤を表示する。テスト上限・採点・回次は[39](39_split_assessment.md)、旧問題本文は[44](44_pretest_content_revision.md)以降の履歴を参照する。詳細は[問題モード](50_basic_understanding_question_mode.md)・[4用語版](51_four_topic_foundation_mode.md)・[アンケート](49_presurvey_baseline.md)・[評価指標](12_evaluation_metrics.md)。

material-viewの初回表示時刻から実績を数え、未利用の先行生成を学習回数・教材表示者へ算入しない。アンケートは事前・事後のphaseと版を付けて既存の版付きJSONへ保存し、DB列を追加しない。旧10段階回答、`posttest-5point-v1`、既存評価列を変換しない。

## 開始前の残課題

A〜C正解等の配置はデバッグ用であり収集に使わない。管理者認証・アクセス対策、自動割付/人数上限は今回未実装。承認・同意/撤回・割付の運用と配布設定を別途確認する。実装完了だけで実験開始可能とはしない。

検証結果は[14](14_testing_acceptance.md)、切替・運用は[18](18_implementation_blueprint.md)・[19](19_experiment_operation_runbook.md)。過去の資料・検証・生AIログは書き換えない。

## 旧問題版設定の廃止（履歴）

以前のeasy-mode整理で旧`question_set_mode`列・APIを廃止した。これは現在の問題モードを廃止したものではない。仕様版51では新規参加者の`test_content_mode`に応じて通常版・基礎理解版・4用語版のバンクを使う。管理設定は新規参加者だけに適用し、登録済みParticipantの問題・回答・snapshotを切り替えない。版付きconstruct keyと保存snapshotから当時の問題を復元し、異なるバンクへフォールバックしない。研究DB内の旧条件に関するデータを削除する操作は、専用手順・明示設定を確認して扱い、起動や通常seedから削除しない。
