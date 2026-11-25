# Repository Instructions for Codex

## 仕様版64の現行条件（2026-11-24）

新規参加者は仕様版64 / `experiment-plan-2026-11-23-participant-code-primary-identifier-presurvey-weekly-frequency-understanding-anchor-v1`で登録し、`four_topic_fundamentals`に固定する。問題バンクは`split-actions-four-topic-v4`、事前アンケートは`presurvey-four-topic-baseline-v12`、事後アンケートは`posttest-5point-v5`を使う。週あたりAI利用日数は0〜7日の整数を`ai_usage_days_per_week`に保存し、理解度は経験「ある」の用語だけに回答目安1・2・4・5を示す。参加者コード（半角数字1〜64桁）を`Participant.id`として保存し、画面・ログ・CSV/XLSX等で識別に使うがAI入力には含めない。学籍番号は取得せず、対応表は研究者がアプリ外で管理する。参加者APIではCookieセッション認証を使わず、参加者コードで対象データを識別する。仕様版63以下のID・回答・snapshotは変更せず読み取り専用とする。仕様版52の対応protocolでは参加者記録を変えず評価サマリーのみ追加でき、仕様版51以下・未対応protocolは再計算対象外。尺度・問題の妥当性、研究上の承認は未確認。詳細はdocs/07、08、15、19、49、51、52、12、14を参照する。

## 仕様版63の履歴条件（2026-11-23）

統合前のブランチには、参加者コードを主識別子として保存するprotocolと、週次AI利用頻度・理解度の回答目安を更新するprotocolが別々に存在した。仕様版64では両方を統合し、新規参加者にだけ適用する。仕様版63の記録は保存時のprotocolと内容を保持する。

## 仕様版62の履歴条件（2026-11-22）

仕様版62ではブランチ上に異なる2 protocolがあった。`experiment-plan-2026-11-22-presurvey-understanding-anchor-guidance-v1`では理解度の目安を1・2・4・5の4段階に更新し、AI利用日数は30日区分のままとした。`experiment-plan-2026-11-22-presurvey-weekly-ai-usage-frequency-v1`ではAI利用日数を週0〜7日の整数に変更した。両方で事前アンケートv11が使われていたため、統合後の新規参加者にはv12を適用する。旧回答JSONは変換しない。

## 仕様版61の履歴条件（2026-11-19）

仕様版61 / `experiment-plan-2026-11-19-presurvey-guidance-example-v1`では、事前アンケートに`presurvey-four-topic-baseline-v10`を使い、直近30日のAI利用日数を`ai_usage_frequency_30d`に保存した。

## 仕様版60の履歴条件（2026-11-19）

仕様版60 / experiment-plan-2026-11-19-presurvey-wording-refinement-v1では、事前presurvey-four-topic-baseline-v9、事後posttest-5point-v5を使った。経験質問は「実験を始める前に」、理解度質問は「基本的な仕組み」を尋ね、第三経験選択肢は「判断できない」、対象語は「事後学習」とした。理解度の回答目安とAI自己評価3項目目の例はまだ設けていなかった。仕様版61では仕様版60以下を読み取り専用とする。
## 仕様版59の履歴条件（2026-11-19）

仕様版59 / `experiment-plan-2026-11-19-survey-neutral-scales-no-na-v1`では、`split-actions-four-topic-v4`、事前`presurvey-four-topic-baseline-v8`、事後`posttest-5point-v5`を使った。理解度は`neither`を含む5段階、自己評価・事後評価は整数1〜5のみだった。事前経験質問は「実験の説明を受ける前に」、理解度質問は「基本的な意味や働き」を尋ね、4番目の用語を「人の評価・好みを用いる事後学習」、経験の第三選択肢を「覚えていない」と表示した。仕様版59以下の回答は変換しない。

## 仕様版58の履歴条件（2026-11-14）

仕様版58 / `experiment-plan-2026-11-14-presurvey-ai-proficiency-question-wording-v1`では、`split-actions-four-topic-v4`、`presurvey-four-topic-baseline-v7`、`posttest-5point-v4`を使用した。理解度は`slightly`を含む5段階、AI自己評価と事後評価には「評価できない」を許容した。仕様版59以降は読み取り専用とし、回答値を変換しない。

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

当時は教材内解説を新規参加者に固定し、仕様版38以下を閲覧専用とした。現行仕様版64では仕様版62以下を閲覧専用とする。

## 仕様版37の履歴条件（2026-11-04）

当時のコードは仕様版37 / `experiment-plan-2026-11-04-presurvey-baseline-v2`。仕様版38〜62を経て現行仕様版64となり、現行では仕様版62以下は閲覧専用。

## 仕様版36の履歴条件（2026-11-04）

この番号には`experiment-plan-2026-11-04-presurvey-baseline-v1`と`experiment-plan-2026-11-04-rag-glossary-v1`の別protocol記録がある。どちらも閲覧専用で保持し、問題バンクv5で結果を復元する。辞書v4によるRAG注釈は現行仕様版64でも維持する。

## 仕様版35の履歴条件（2026-11-03）

仕様版35当時は通常版`split-actions-v5`と学習内容v15を使用した。全27問はPR #260（507ea4a）適用後の本文で、各問は正解1・M1二つ・M3二つ・unknown一つの6択。設問1・2だけを出題・採点し、設問3は保持する。設問1のみ出題設定、ペア答え合わせ、教材用語解説モードは登録時に固定する。教材内解説モードでは当時の辞書v3を意味参照としてAIへ渡し、逐語転載せず文脈に合わせて言い換える。仕様版35の結果はv5で復元する。現行仕様版64では辞書v4、教材内解説、目標800文字、統制群の共通prompt、およびモード別の固定テスト設定を維持する。仕様版36〜63を含む旧protocolは閲覧専用である。詳細は[事前アンケート](docs/49_presurvey_baseline.md)、[教材モード](docs/41_learning_glossary_material_mode.md)、[文字数条件](docs/42_learning_glossary_material_length.md)、[AI指示](docs/10_ai_prompt_contracts.md)、[RAG注釈](docs/49_rag_glossary.md)、[辞書](docs/24_learning_glossary.md)、[テスト履歴](docs/44_pretest_content_revision.md)〜[docs/48](docs/48_first_question_only.md)を参照する。受入検証と実験開始承認は別に扱う。

## 設問1のみ出題する設定（導入時の履歴）

仕様版35で管理設定として導入し、仕様版40で設定UI/APIを廃止した。現行仕様版64の新規参加者は4用語版の各用語1問（計4問）に固定する。`application`・`basic_understanding`の計3問条件は既存参加者の記録復元用に保持する。保存済み回答と結果復元は変更しない。詳細は[docs/48](docs/48_first_question_only.md)・[docs/50](docs/50_basic_understanding_question_mode.md)・[docs/51](docs/51_four_topic_foundation_mode.md)。

## 仕様版28の答え合わせ（履歴）

通常版のPRETEST・RETEST・内部final_testで、用語ごとの設問1・2を保存後に同じテスト画面内で本人の選択内容と正誤を示し、続行で次の用語へ進む。答え合わせ中はページ/URL遷移せず、正答・解説・内部分類を表示しない。これは仕様版28の採用時記録である。現行仕様版64の新規参加者は4用語版の各用語1問を出題し、回答後に設問ごとに確認する。`application`・`basic_understanding`の設問1のみ条件は既存記録の復元用に保持する。必要な全設問が採点済みで全問正解なら結果表示snapshotに応じて全体結果確認後または直接surveyへ進み、学習・後続テストを省略する。未達時は従来の経路を維持する。受入条件、API・snapshot・条件は[docs/40](docs/40_question_pair_answer_review.md)を参照する。

## 仕様版27の採用記録

仕様版27では通常版はsplit-actions-v1の6設問・4択単一選択で、設問3はデータのみ保持した。直前の誤答設問を用語ごとにまとめて教材・確認問題へ渡し、unknownが1つでもあれば用語全体のunknownを優先して教材入力から誤答を除き、M3優先時はM1も扱った。以下の版26記述と矛盾する箇所は[docs/39](docs/39_split_assessment.md)を優先する。版27時点でBackend全1,788件の通過を確認した記録と、現在のCIが5分割である運用情報は、仕様版28の受入検証とは区別する。実AI確認・研究条件の妥当性・実験開始の承認とは区別する。

## 用語注釈の不変条件

- 現行の共通固定辞書はlearning-glossary-v4の17語で、RAG（検索拡張生成）も注釈対象にする。v1〜v3は履歴として不変で保持する。AI、事前学習、ファインチューニング、プロンプトエンジニアリング、データベース、マルチエージェント、タスク、記憶プロセスの8語を注釈から除外する。長い除外語の一部からプロンプト・エージェントを抽出せず、独立して登場した場合は補足する。確認問題自体と結果確認画面は対象外。辞書・保存・移行はdocs/24・docs/49_rag_glossary.mdを参照する。
- 注釈は表示用JSONとして保存し、現行の教材内解説では辞書を両群共通の意味参照として教材本文の生成入力に渡す。現行仕様版64は本文800文字程度を目安にするだけで、文字数による合否判定・再試行は行わない。旧版のモード別文字数契約とログは履歴として保持する。教授契約版v7は維持する。再表示はsnapshotを使い、旧教材へ後付けしない。登録語しか扱わず、AIで未知語を補わない。

このリポジトリは、卒業研究用AIチューターのアプリケーションリポジトリです。目標仕様は実験計画書に合わせたdocs、現行挙動はコード・YAML・入力型・テストを基準にしてください。実行時の現行実験仕様版は64 / `experiment-plan-2026-11-23-participant-code-primary-identifier-presurvey-weekly-frequency-understanding-anchor-v1`です。仕様版63以下は参加者操作に対して閲覧専用です。文書・実装更新は研究上の承認を意味しません。受入検証と実験開始承認は別に扱ってください。

## Authoritative Documents

- `docs/00_project_summary.md` から順に `docs/19_experiment_operation_runbook.md` までを必ず読む。
- `docs/20_experiment_plan_alignment.md` を読み、目標仕様・現行実装・未対応・要確認を区別する。
- 仕様版33の履歴差分は`docs/45_pretest_memory_distractors.md`、仕様版34のv4比較表対応は`docs/46_split_assessment_choice_wording.md`、仕様版35の追加選択肢と分類仮説は`docs/47_split_assessment_added_choices.md`、事前アンケートv1/v2は`docs/49_presurvey_baseline.md`、RAG辞書追加は`docs/49_rag_glossary.md`を参照する。問題バンクv1〜v5と辞書v1〜v3、過去の採用記録は履歴として変更しない。
- 仕様版28の答え合わせ契約・API・保存・受入条件はdocs/40_question_pair_answer_review.mdを正とする。docs/39は仕様版27の採用時記録として保持する。
- `docs/99_sources_and_notes.md` は現行計画書の出典と設計判断の根拠として扱う。旧PPTX・旧案はhistory資料であり現行要件ではない。
- 実装依頼時の初期指示は `prompt.md` を使う。

## Research Invariants

- 新規参加者は4用語版に固定する。既存参加者の出題・採点・確認問題復元はsnapshotされた`test_content_mode`に対応する問題バンクだけを使い、集計もモード別に分離する。`/api/admin/test-content-mode`のGETは固定値を返し、PUTで他モードを要求した場合は409とする。旧`question_set_mode`設定APIとフィルターは廃止済みで、旧フィルター付き要求は422で拒否する。過去のeasy-mode削除手順は新しい`test_content_mode`・問題資産・記録を対象にせず、旧版へのフォールバックを実装しない。
- 仕様版64の新規登録では`participant_code`を半角数字1〜64桁として検証し、参加者の主キーとしてDB・関連ログ・CSV/XLSX・ファイル名へ保存する。冪等性記録にはコードを含む要求のSHA-256 fingerprintのみ保存し、登録応答には参加者コードが含まれる。コードをAIモデルへの入力に含めず、UIでは必要なアプリ内識別子として保存する。仕様版62以下の既存参加者IDと記録は変更しない。学籍番号はアプリで取得しない。コードと学籍番号の対応表は研究者がアプリ外で管理し、アプリ内の管理API/UIを設けない。既存対応表SQLiteは通常起動・登録時に開かず、明示削除時の旧行cleanupだけを維持する。

- 現行の評価指標版は`four-hypotheses-v1`。H1は事前から初回再テストへの正答率差、H2は事前M1/M3項目に対する初回再テストでの同タイプ再選択率、H3は事前完了・非満点者を分母にした再テスト満点率、H4は教材評価6項目の個別集計。詳細な分母・欠測規則はdocs/12を正とし、現行API/UI/exportへ旧H5/H6を混ぜない。仕様版52参加者の新サマリーを作っても旧サマリー・生データは上書きしない。
- 目標は大学生40名/各群20名、原則無作為割付。low設定・事前知識6項目・事前AI利用2領域・事後システム評価1/教材評価6の5段階・任意自由記述・現行4仮説の記述集計は実装済み。自動割付・人数上限は対象外。式・対象はdocs/12・20の定義を守る。
- 共通説明とunknownは意味や仕組みを扱う。unknownの証拠はmandatory_elements.definitionとteaching_contract.mechanism_explanation/transfer_check。旧6項目を必須に戻さない。
- 比較対象は「AIあり/なし」ではなく、「通常AIチューター」と「ログ適応型AIチューター」。
- 現行分類はM1/M3/unknownのみ。両群へ同じ用語の全フェーズの採点済み回答履歴を渡す。提案群だけに明示的な診断・対象主張・taxonomy・タイプ別教授方針を追加する。方略はbackendで固定する。
- 確認問題の診断連動規則は両群共通。統制群のLLMへ分類・診断由来段階を渡さず、共通履歴内にも診断情報を混ぜない。統制群の自然な誤り訂正は許容する。
- 被験者画面に内部分類、群名、教授方略を直接表示しない。
- テスト回答中はチャット・ヒント・即時正解を表示しない。新規参加者は4用語各1問を出題し、複数選択は正解3つまたはJ単独。回答後は選択肢別（本人が選んだ項目のみ）と設問全体の正誤を示す。未選択肢の正誤は表示しない。既存参加者は保存snapshotで復元する。過去の設問ペア表示契約はdocs/40を参照する。
- 学習確認は1用語・1セッションあたり最大3回答。必要な全設問を採点して全問正解した事前・再テスト1/2・内部`final_test`の後はsurveyへ進み、学習・後続テストを省略する。未達時は誤答用語を学習する。再テスト2後は正誤にかかわらずsurveyへ進む。採点済みバッチは1回とし、全問未回答は採点しない。
- 新規Participantのテストは`four_topic_fundamentals`=`split-actions-four-topic-v4`に固定し、4用語各1問・計4問を出題する。A〜Cは正解、D〜FはM1、G〜IはM3、Jはunknownの10択。内部`final_test` APIは履歴復元用に保持し、新規通常経路では使わない。既存Participantは保存済みモード・protocol・snapshotに基づいて当時の問題を復元し、版付きconstruct_keyで本文・選択肢を上書きしない。学習確認は直前テストの保存snapshotを利用する。通常の学習v15と教材条件は維持する。
- 選択肢配置は管理画面のDB保存設定で切り替える。既定値は`debug_fixed`で、新規参加者だけに適用する。実験データ収集前に`randomized`へ変更し、正答位置の手掛かりがないことを確認する。判定は表示ラベルでなく選択肢ID・内部メタデータで行う。
- 現行コードでは仕様版64 / `experiment-plan-2026-11-23-participant-code-primary-identifier-presurvey-weekly-frequency-understanding-anchor-v1`だけを新規参加者に適用し、`retest_cycles_completed=0`で開始する。問題バンクv4、事前アンケートv12（週0〜7日のAI利用日数を整数で保存）、事後アンケートv5、4仮説指標を使う。理解度は経験ありの場合だけ回答目安1・2・4・5付きで尋ねる。参加者コードは主キーとして保存し、画面・ログ・出力に使うがAIモデルには送らない。参加者APIではCookieセッション認証を行わない。仕様版63以下のID・回答・snapshotは変更しない。仕様版52の対応2 protocolは参加者記録を変えずH1〜H4評価サマリーのみ追加可能。仕様版51以下・未対応protocolは再計算対象外。
- 両群の教材の小見出し・数・順序・まとめ方はAIが決める。冒頭の##用語名と非空の###セクションだけを要求し、実験群の必須教授内容・transfer_checkは本文内証拠で検証する。固定見出しから証拠文を自動補正しない。
- 教材内のtransfer_checkは維持するが、独立した追加テスト・旧支援量・自由回答処理を戻さない。
- 過去のapplication/basic_understandingの対象は`llm_knowledge`、`multi_agent`、`memory_process`。現行新規4用語版の対象は`transformer`、`llm_training_stages`、`multi_agent_four_topic`、`memory_process_four_topic`。

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
