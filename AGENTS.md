# Repository Instructions for Codex

## 仕様版54の現行条件（2026-11-12）

新規参加者は仕様版54 / `experiment-plan-2026-11-12-four-topic-instruction-tuning-perfect-test-early-exit-posttest-material-amount-clarity-removal-v1`で登録し、`four_topic_fundamentals`に固定する。問題バンクは`split-actions-four-topic-v3`、事前アンケートは`presurvey-four-topic-baseline-v4`、事後アンケートは`posttest-5point-v4`を使う。4用語版の`instruction_tuning`は「インストラクションチューニング」と表示する。事後はシステム評価1項目・教材評価6項目で、教材量の質問は「教材の量はどの程度でしたか」。全設問の採点後に満点なら結果表示snapshotに従って確認後または直接surveyへ進み、学習と後続テストを省略する。未達時の採点・学習経路・回数上限は維持する。現行指標は`four-hypotheses-v1`のH1〜H4で、旧6仮説は履歴として扱う。仕様版53以下の参加者操作は読み取り専用で記録を変更しないが、仕様版52の対応する2 protocolに限り、参加者の進行・回答・既存サマリーを変更せずH1〜H4評価サマリーを追加できる。仕様版51以下と未対応protocolは再計算しない。現行同意文書は`consent-2026-11-12-revised-v1`。研究用コードは登録時だけ受信して検証後に破棄し、DB・冪等性記録・ログ・エクスポート・AI入力・ブラウザ保存へ記録しない。学籍番号はアプリで取得せず、対応表は研究者がアプリ外で管理する。尺度・難易度・測定上の同等性・研究上の承認は未確認。[事前アンケート](docs/49_presurvey_baseline.md)、[4用語版](docs/51_four_topic_foundation_mode.md)、[事後アンケート](docs/52_posttest_five_point_evaluation.md)、[指標](docs/12_evaluation_metrics.md)、[受入記録](docs/14_testing_acceptance.md)。

## 仕様版48の履歴条件（2026-11-10）

仕様版48 / `experiment-plan-2026-11-10-presurvey-exposure-understanding-split-v1`では、問題モードは`application`、`basic_understanding`、`four_topic_fundamentals`の3値で、RuntimeSettingの保存済み値を登録時にParticipantへ固定した。未設定時の既定値は4用語版。標準2モードの事前アンケートは`presurvey-baseline-v3`、4用語版は`presurvey-four-topic-baseline-v2`を使う。各6用語について見聞き経験を必須回答とし、「ある」の場合のみ理解度を必須にする。それ以外の理解度はnullで保存する。直近30日のAI利用日数と、3行動の5段階自己評価（各項目に「評価できない」を含む）も取得した。事前テスト満点者の早期終了、4用語版の再テスト2までの固定進行を含む条件は仕様版49にも引き継いだ。仕様版48以下の記録・回答・集計は閲覧専用で保全する。[事前アンケート](docs/49_presurvey_baseline.md)、[評価指標](docs/12_evaluation_metrics.md)、[4用語版仕様](docs/51_four_topic_foundation_mode.md)。

## 仕様版46の条件（履歴・2026-11-09）

仕様版46 / `experiment-plan-2026-11-09-four-topic-default-two-retests-v1`では、事前テスト満点でも4用語すべてを学習し、再テスト1後も同様に学習して再テスト2へ進んだ。仕様版47で事前満点者の早期終了を導入した。仕様版46以下の保存記録は変更しない。

## 仕様版45の条件（履歴・2026-11-09）

仕様版45には二つのprotocolがある。`experiment-plan-2026-11-09-four-topic-two-retest-rounds-v1`は既定`application`で、4用語版のみ満点後も再テスト2まで学習を続けた。`experiment-plan-2026-11-09-four-topic-foundation-default-v1`はRuntimeSetting未設定時の既定値を4用語版にした。どちらも問題モードを登録時Participantへ固定し、保存済み設定は変更しない。保存記録・問題・回答snapshotはprotocolに応じて復元する。

## 仕様版44の条件（履歴・2026-11-09）

仕様版44 / `experiment-plan-2026-11-09-four-topic-foundation-v1`で4用語版を導入した。各用語1問・4問・10択、事前・再テスト1/2・内部final_testを持ち、満点時は通常モードと同じ早期終了条件だった。仕様版45では既定値変更と4用語版の固定2回フローが別protocolとして導入された。仕様版44の保存記録・問題・回答snapshotは履歴として復元する。

## 仕様版43の導入時条件（履歴・2026-11-08）

新規参加者は仕様版43 / `experiment-plan-2026-11-08-basic-understanding-question-mode-v1`で登録する。管理設定の問題モード`application`（既定、split-actions-v5）または`basic_understanding`（split-actions-basic-v1）を登録時Participantへ固定し、既存参加者へ遡及しない。各用語の設問1のみ（計3問）を出題し、既存の答え合わせ・結果非表示・事前アンケート・教材・採点・回数上限を維持する。仮説集計はモード別に分離し、モード間は合算しない。仕様版42以下・旧protocolは閲覧専用で、問題・回答・教材・snapshotは変更しない。基礎理解版の難易度低下、現行版との測定特性・難易度同等性、研究上の承認は未確認。[仕様](docs/50_basic_understanding_question_mode.md)。

## 仕様版42の履歴条件（2026-11-07）

仕様版42当時は`experiment-plan-2026-11-07-fixed-admin-settings-learning-material-target-800-control-shared-prompt-v1`を使用した。新規参加者は同意後に`presurvey-baseline-v2`の必須8項目へ回答する。事前・再テスト・内部final_testは各用語の設問1だけ（計3問）を出題し、各問回答後に設問ごとの答え合わせを行う。テスト全体の結果確認画面は表示しない。登録snapshotは`show_pretest_results=false`、`show_retest_results=false`、`show_question_reviews=true`、`first_question_only=true`、`learning_material_glossary_mode=integrated_material`で固定し、旧RuntimeSetting値は参照しない。これらの管理設定UI/API、教材モード表示、集計条件切替はなかった。仕様版43では問題モード設定が追加された。旧履歴値はDB・管理ログAPI・CSVに保持するが、参加者一覧・個別ログ画面には表示しない。

仕様版42の事後アンケート`posttest-10point-v3`はシステム評価2項目・教材評価6項目・任意自由記述を保存し、当時のH5はposttestだけを参照した（履歴）。共通辞書v4（RAGを含む17語）を使い、教材内解説では定義を意味参照として渡して文脈に合わせて言い換える。教材本文は800文字程度を目安にし、文字数の上下限による検証・再生成は行わず、監査用に実文字数と目標だけを記録する。教材生成は共通ルールを両群に適用し、統制群に群別の自然言語方略指示を加えず、提案群だけに診断・タイプ別教授指示を加える。仕様版41以下と別protocolは閲覧専用で、既存回答・教材・snapshot・監査記録を更新しない。詳細は[AI指示](docs/10_ai_prompt_contracts.md)、[事前アンケート](docs/49_presurvey_baseline.md)、[教材モード](docs/41_learning_glossary_material_mode.md)、[文字数契約](docs/42_learning_glossary_material_length.md)、[受入記録](docs/14_testing_acceptance.md)。

## 仕様版41の履歴条件（2026-11-07）

仕様版41には`experiment-plan-2026-11-07-fixed-admin-settings-control-shared-prompt-v1`、`experiment-plan-2026-11-07-learning-material-target-800-control-shared-prompt-v1`、`experiment-plan-2026-11-07-split-actions-v6-q1-only-v1`の別protocolがある。最初の二つは通常版バンクv5、三つ目は設問1のみのバンクv6を使った。仕様版42への統合後はいずれも履歴・閲覧専用とし、回答復元ではprotocol IDに応じてv5またはv6を選ぶ。仕様版41以下は閲覧専用。

## 仕様版39の履歴条件（2026-11-06）

当時は教材内解説を新規参加者に固定し、仕様版38以下を閲覧専用とした。現行仕様版54では仕様版53以下を閲覧専用とする。

## 仕様版37の履歴条件（2026-11-04）

当時のコードは仕様版37 / `experiment-plan-2026-11-04-presurvey-baseline-v2`。仕様版38〜53を経て現行仕様版54となり、現行では仕様版53以下は閲覧専用。

## 仕様版36の履歴条件（2026-11-04）

この番号には`experiment-plan-2026-11-04-presurvey-baseline-v1`と`experiment-plan-2026-11-04-rag-glossary-v1`の別protocol記録がある。どちらも閲覧専用で保持し、問題バンクv5で結果を復元する。辞書v4によるRAG注釈は現行仕様版54でも維持する。

## 仕様版35の履歴条件（2026-11-03）

仕様版35当時は通常版`split-actions-v5`と学習内容v15を使用した。全27問はPR #260（507ea4a）適用後の本文で、各問は正解1・M1二つ・M3二つ・unknown一つの6択。設問1・2だけを出題・採点し、設問3は保持する。設問1のみ出題設定、ペア答え合わせ、教材用語解説モードは登録時に固定する。教材内解説モードでは当時の辞書v3を意味参照としてAIへ渡し、逐語転載せず文脈に合わせて言い換える。仕様版35の結果はv5で復元する。現行仕様版54では辞書v4、教材内解説、目標800文字、統制群の共通prompt、およびモード別の固定テスト設定を維持する。仕様版36〜52を含む旧protocolは閲覧専用である。詳細は[事前アンケート](docs/49_presurvey_baseline.md)、[教材モード](docs/41_learning_glossary_material_mode.md)、[文字数条件](docs/42_learning_glossary_material_length.md)、[AI指示](docs/10_ai_prompt_contracts.md)、[RAG注釈](docs/49_rag_glossary.md)、[辞書](docs/24_learning_glossary.md)、[テスト履歴](docs/44_pretest_content_revision.md)〜[docs/48](docs/48_first_question_only.md)を参照する。受入検証と実験開始承認は別に扱う。

## 設問1のみ出題する設定（導入時の履歴）

仕様版35で管理設定として導入し、仕様版40で管理設定を廃止した。現行仕様版54の新規参加者は4用語版の各用語1問（計4問）に固定する。現行版・基礎理解版の計3問条件は旧参加者の記録復元用に保持する。保存済み回答と結果復元は変更しない。詳細は[docs/48](docs/48_first_question_only.md)・[docs/50](docs/50_basic_understanding_question_mode.md)・[docs/51](docs/51_four_topic_foundation_mode.md)。

## 仕様版28の答え合わせ（履歴）

通常版のPRETEST・RETEST・内部final_testで、用語ごとの設問1・2を保存後に同じテスト画面内で本人の選択内容と正誤を示し、続行で次の用語へ進む。答え合わせ中はページ/URL遷移せず、正答・解説・内部分類を表示しない。これは仕様版28の採用時記録である。現行仕様版54の新規参加者は4用語版の各用語1問を出題し、回答後に設問ごとに確認する。現行版・基礎理解版の設問1のみ条件は過去の記録復元用に保持する。必要な全設問が採点済みで全問正解なら結果表示snapshotに応じて全体結果確認後または直接surveyへ進み、学習・後続テストを省略する。未達時は従来の経路を維持する。設定UI/APIは廃止した。受入条件、API・snapshot・条件は[docs/40](docs/40_question_pair_answer_review.md)を参照する。

## 仕様版27の採用記録

仕様版27では通常版はsplit-actions-v1の6設問・4択単一選択で、設問3はデータのみ保持した。直前の誤答設問を用語ごとにまとめて教材・確認問題へ渡し、unknownが1つでもあれば用語全体のunknownを優先して教材入力から誤答を除き、M3優先時はM1も扱った。以下の版26記述と矛盾する箇所は[docs/39](docs/39_split_assessment.md)を優先する。版27時点でBackend全1,788件の通過を確認した記録と、現在のCIが5分割である運用情報は、仕様版28の受入検証とは区別する。実AI確認・研究条件の妥当性・実験開始の承認とは区別する。

## 用語注釈の不変条件

- 現行の共通固定辞書はlearning-glossary-v4の17語で、RAG（検索拡張生成）も注釈対象にする。v1〜v3は履歴として不変で保持する。AI、事前学習、ファインチューニング、プロンプトエンジニアリング、データベース、マルチエージェント、タスク、記憶プロセスの8語を注釈から除外する。長い除外語の一部からプロンプト・エージェントを抽出せず、独立して登場した場合は補足する。確認問題自体と結果確認画面は対象外。辞書・保存・移行はdocs/24・docs/49_rag_glossary.mdを参照する。
- 注釈は表示用JSONとして保存し、現行の教材内解説では辞書を両群共通の意味参照として教材本文の生成入力に渡す。現行仕様版54は本文800文字程度を目安にするだけで、文字数による合否判定・再試行は行わない。旧版のモード別文字数契約とログは履歴として保持する。教授契約版v7は維持する。再表示はsnapshotを使い、旧教材へ後付けしない。登録語しか扱わず、AIで未知語を補わない。

このリポジトリは、卒業研究用AIチューターのアプリケーションリポジトリです。目標仕様は実験計画書に合わせたdocs、現行挙動はコード・YAML・入力型・テストを基準にしてください。実行時の現行実験仕様版は54 / `experiment-plan-2026-11-12-four-topic-instruction-tuning-perfect-test-early-exit-posttest-material-amount-clarity-removal-v1`です。仕様版53以下は閲覧専用です。2026-11-12の同意文書・識別対応の変更はアプリ内の文書・運用更新であり、研究倫理上の承認を意味しません。受入検証と実験開始承認は別に扱ってください。

## Authoritative Documents

- `docs/00_project_summary.md` から順に `docs/19_experiment_operation_runbook.md` までを必ず読む。
- `docs/20_experiment_plan_alignment.md` を読み、目標仕様・現行実装・未対応・要確認を区別する。
- 仕様版33の履歴差分は`docs/45_pretest_memory_distractors.md`、仕様版34のv4比較表対応は`docs/46_split_assessment_choice_wording.md`、仕様版35の追加選択肢と分類仮説は`docs/47_split_assessment_added_choices.md`、事前アンケートv1/v2は`docs/49_presurvey_baseline.md`、RAG辞書追加は`docs/49_rag_glossary.md`を参照する。問題バンクv1〜v5と辞書v1〜v3、過去の採用記録は履歴として変更しない。
- 仕様版28の答え合わせ契約・API・保存・受入条件はdocs/40_question_pair_answer_review.mdを正とする。docs/39は仕様版27の採用時記録として保持する。
- `docs/99_sources_and_notes.md` は現行計画書の出典と設計判断の根拠として扱う。旧PPTX・旧案はhistory資料であり現行要件ではない。
- 実装依頼時の初期指示は `prompt.md` を使う。

## Research Invariants

- 新規参加者は4用語版に固定する。既存参加者の出題・採点・確認問題復元はsnapshotされた`test_content_mode`に対応する問題バンクだけを使い、集計もモード別に分離する。`/api/admin/test-content-mode`のGETは固定値を返し、PUTで他モードを要求した場合は409とする。旧`question_set_mode`設定APIとフィルターは廃止済みで、旧フィルター付き要求は422で拒否する。過去のeasy-mode削除手順は新しい`test_content_mode`・問題資産・記録を対象にせず、旧版へのフォールバックを実装しない。
- 登録時の`research_code`は半角数字1〜64桁を検証した後に破棄する。登録request_hashには研究用コードを含めず、別SQLiteを登録時に開かない。コードをログ・DB・export・AI入力・browser storageへ追加しない。学籍番号はアプリで取得しない。過去の対応表ファイル/行は登録・通常起動時に参照、移行、削除せず、対応表API/UIも復活させない。既存の明示的参加者削除cleanupは維持する。

- 現行の評価指標版は`four-hypotheses-v1`。H1は事前から初回再テストへの正答率差、H2は事前M1/M3項目に対する初回再テストでの同タイプ再選択率、H3は事前完了・非満点者を分母にした再テスト満点率、H4は教材評価6項目の個別集計。詳細な分母・欠測規則はdocs/12を正とし、現行API/UI/exportへ旧H5/H6を混ぜない。仕様版52参加者の新サマリーを作っても旧サマリー・生データは上書きしない。
- 目標は大学生40名/各群20名、原則無作為割付。low設定・事前知識6項目・事前AI利用2領域・事後システム評価1/教材評価6の5段階・任意自由記述・現行4仮説の記述集計は実装済み。自動割付・人数上限は対象外。式・対象はdocs/12・20の定義を守る。
- 共通説明とunknownは意味や仕組みを扱う。unknownの証拠はmandatory_elements.definitionとteaching_contract.mechanism_explanation/transfer_check。旧6項目を必須に戻さない。
- 比較対象は「AIあり/なし」ではなく、「通常AIチューター」と「ログ適応型AIチューター」。
- 現行分類はM1/M3/unknownのみ。両群へ同じ用語の全フェーズの採点済み回答履歴を渡す。提案群だけに明示的な診断・対象主張・taxonomy・タイプ別教授方針を追加する。方略はbackendで固定する。
- 確認問題の診断連動規則は両群共通。統制群のLLMへ分類・診断由来段階を渡さず、共通履歴内にも診断情報を混ぜない。統制群の自然な誤り訂正は許容する。
- 被験者画面に内部分類、群名、教授方略を直接表示しない。
- 選択肢配置は管理画面のDB保存設定で切り替える。既定値は`debug_fixed`で、新規参加者だけに適用する。実験データ収集前に`randomized`へ変更し、正答位置の手掛かりがないことを確認する。判定は表示ラベルでなく選択肢ID・内部メタデータで行う。
- 現行コードでは新規だけ仕様版54 / `experiment-plan-2026-11-12-four-topic-instruction-tuning-perfect-test-early-exit-posttest-material-amount-clarity-removal-v1`を保存し、`retest_cycles_completed=0`で開始する。この列は学習後retestだけを数える。新規は`presurvey-four-topic-baseline-v4`、`posttest-5point-v4`、`split-actions-four-topic-v3`を使用する。事後はシステム評価1項目・教材評価6項目で、`system_clarity`は含めない。現行評価はH1〜H4。仕様版53以下の記録は保存時のprotocol・問題・アンケート版で復元し、既存行の設定・回数・回答・評価を補完・変更しない。仕様版52の対応2 protocolには参加者データや既存サマリーを変更せずH1〜H4評価サマリーだけを追加でき、仕様版51以下と未対応protocolは再計算しない。全問採点済みの満点後は結果表示snapshotに従ってsurveyへ進み、学習・後続テストを省略する。
- 両群の教材の小見出し・数・順序・まとめ方はAIが決める。冒頭の##用語名と非空の###セクションだけを要求し、実験群の必須教授内容・transfer_checkは本文内証拠で検証する。固定見出しから証拠文を自動補正しない。
- 教材内のtransfer_checkは維持するが、独立した追加テスト・旧支援量・自由回答処理を戻さない。
- 過去のapplication/basic_understandingの対象は`llm_knowledge`、`multi_agent`、`memory_process`。現行新規4用語版の対象は`transformer`、`llm_training_stages`、`multi_agent_four_topic`、`memory_process_four_topic`。
- テスト回答中はチャット・ヒント・即時正解を表示しない。現行新規参加者は4用語各1問を出題し、複数選択は正解3つまたはJ単独。回答後は本人の選択した選択肢ごとの正誤と設問全体の正誤を示し、未選択肢の正誤は表示しない。既存Participantは保存snapshotのモード/問題で復元する。過去の設問ペア表示契約はdocs/40を参照する。
- 学習確認は1用語・1セッションあたり最大3回答。必要な全設問を採点し全問正解した事前・再テスト1/2・内部`final_test`の後はsurveyへ進み、学習・後続テストを省略する。未達時はモード別の誤答用語を学習する。再テスト2の採点後は正誤にかかわらずsurveyへ進む。採点済みバッチは1回とし、全問未回答は採点しない。
- 新規Participantのテストは`four_topic_fundamentals`=`split-actions-four-topic-v3`に固定し、4用語各1問・計4問を出題する。4用語バンクはA〜C正解、D〜F=M1、G〜I=M3、J=unknownの10択。activeキーはpretest_v1、retest_v1/v2。内部`final_test` APIと履歴復元契約は保持するが、新規4用語フローでは使わない。既存Participantは保存済み`test_content_mode`・protocol・snapshotから各時点のバンクを選ぶ。旧バンクは復元用に保持し、版付きconstruct_keyで既存本文・選択肢を上書きしない。学習確認は直前テストの保存snapshotを利用する。通常の学習v15と教材条件は維持する。
- 選択肢配置は管理画面のDB保存設定で切り替える。既定値は`debug_fixed`で、新規参加者だけに適用する。実験データ収集前に`randomized`へ変更し、正答位置の手掛かりがないことを確認する。判定は表示ラベルでなく選択肢ID・内部メタデータで行う。

## AI Backend Rules

- OpenAI APIキーを要求しない。
- OpenAI SDKで通常APIを直接呼ばない。
- AI呼び出しは必ず `AIBackend` インターフェース経由にする。
- AIタスクは教材生成・正答要約・誤答解説だけ。採点・分類・状態更新・方略決定はbackendで行う。
- 通常実行では `CodexAppServerBackend` を使い、ユーザーのChatGPT/Codexログイン済みapp-serverへ接続する。
- アプリ既定のAI設定は `gpt-6-luna / low`。管理画面では `gpt-6.1-sol` / `gpt-6-luna` / `gpt-6-astra`、low/medium/high/xhigh/max、および初期OFFのCodex Fast modeを一時切替でき、両群・進行中参加者の次回呼び出しから適用する。Fast modeはapp-serverのturn単位service tierで指定し、OFF時にも`default`を明示する。選択値はDBに保存せず、Fast modeはbackend再起動でOFFへ戻る。対応モデル・アカウントに依存し、使用量が増えるため、実験中は設定を固定する。研究計画書原本のgpt-5.6-luna記載は変更せず、アプリ設定との差を明示する。同一参加者内での実験中切替は条件・モデル混在を生む。
- `MockAIBackend` は自動テスト・障害切り分け専用にし、通常実験データへ混ぜない。
- `AI_BACKEND=codex_app_server` ではMockへ自動フォールバックしない。
- ChatGPT/Codex認証情報、アクセストークン、APIキーをDBに保存しない。

## Implementation Priorities

1. 研究ログの完全性
2. Codex app-server経由の実AI応答
3. 実験フローの正確性
4. 評価指標とCSV出力
5. MockAIBackendでのテスト再現性
6. UIの見た目

## Editing Policy

- 仕様整理の依頼ではMarkdownだけを編集する。
- 文書更新だけでプロンプト・Schema・環境設定・API・DB・実行版を変更しない。実装開始は別途明示的な依頼を必要とする。
- 目標プロンプトの引用と現行コードの送信原文を区別する。旧6仮説サマリーを現行4仮説の確定済み評価値として扱わない。
- 実装開始の依頼では、仕様にない独自判断を最小限にし、判断した内容はREADMEまたは該当docsに追記する。
- 要確認事項はdocs/20で管理し、決定されていない分析方法・新しいunknownの検査項目を実装者が補完しない。その他の運用はdocs/19・99を参照する。
