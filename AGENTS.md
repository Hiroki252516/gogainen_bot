# Repository Instructions for Codex

## 仕様版44の現行条件（2026-11-09）

新規参加者は仕様版44 / `experiment-plan-2026-11-09-four-topic-foundation-v1`で登録する。管理設定`test_content_mode`は`application`（既定）、`basic_understanding`、`four_topic_fundamentals`の3値で、登録時Participantへ固定し既存参加者へ遡及しない。4用語版はTransformer、LLMの学習段階、マルチエージェント、記憶プロセス各1問、計4問・10択で、正解3つまたはJ単独を選ぶ。事前・再テスト1/2・内部final_testは同一問題を用い、確認問題は誤答した問題のsnapshotを使う。4用語用事前アンケート、RAG節指定、学習対象、確認UI、4問分母の指標に対応する。6仮説とログ/CSV/XLSXはモード別に分け、合算しない。仕様版43以下・旧protocolは閲覧専用で既存問題・回答・教材・snapshot・監査記録を変更しない。反復による練習効果、モード間の測定特性・難易度同等性、研究上の承認は未確認。[4用語版仕様](docs/51_four_topic_foundation_mode.md)。

## 仕様版43の導入時条件（履歴・2026-11-08）

新規参加者は仕様版43 / `experiment-plan-2026-11-08-basic-understanding-question-mode-v1`で登録する。管理設定の問題モード`application`（既定、split-actions-v5）または`basic_understanding`（split-actions-basic-v1）を登録時Participantへ固定し、既存参加者へ遡及しない。各用語の設問1のみ（計3問）を出題し、既存の答え合わせ・結果非表示・事前アンケート・教材・採点・回数上限を維持する。仮説集計はモード別に分離し、モード間は合算しない。仕様版42以下・旧protocolは閲覧専用で、問題・回答・教材・snapshotは変更しない。基礎理解版の難易度低下、現行版との測定特性・難易度同等性、研究上の承認は未確認。[仕様](docs/50_basic_understanding_question_mode.md)。

## 仕様版42の履歴条件（2026-11-07）

仕様版42当時は`experiment-plan-2026-11-07-fixed-admin-settings-learning-material-target-800-control-shared-prompt-v1`を使用した。新規参加者は同意後に`presurvey-baseline-v2`の必須8項目へ回答する。事前・再テスト・内部final_testは各用語の設問1だけ（計3問）を出題し、各問回答後に設問ごとの答え合わせを行う。テスト全体の結果確認画面は表示しない。登録snapshotは`show_pretest_results=false`、`show_retest_results=false`、`show_question_reviews=true`、`first_question_only=true`、`learning_material_glossary_mode=integrated_material`で固定し、旧RuntimeSetting値は参照しない。これらの管理設定UI/API、教材モード表示、集計条件切替はなかった。仕様版43では問題モード設定が追加された。旧履歴値はDB・管理ログAPI・CSVに保持するが、参加者一覧・個別ログ画面には表示しない。

事後アンケート`posttest-10point-v3`はシステム評価2項目・教材評価6項目・任意自由記述を保存し、H5はposttestだけを参照する。共通辞書v4（RAGを含む17語）を使い、教材内解説では定義を意味参照として渡して文脈に合わせて言い換える。教材本文は800文字程度を目安にし、文字数の上下限による検証・再生成は行わず、監査用に実文字数と目標だけを記録する。教材生成は共通ルールを両群に適用し、統制群に群別の自然言語方略指示を加えず、提案群だけに診断・タイプ別教授指示を加える。仕様版41以下と別protocolは閲覧専用で、既存回答・教材・snapshot・監査記録を更新しない。詳細は[AI指示](docs/10_ai_prompt_contracts.md)、[事前アンケート](docs/49_presurvey_baseline.md)、[教材モード](docs/41_learning_glossary_material_mode.md)、[文字数契約](docs/42_learning_glossary_material_length.md)、[受入記録](docs/14_testing_acceptance.md)。

## 仕様版41の履歴条件（2026-11-07）

仕様版41には`experiment-plan-2026-11-07-fixed-admin-settings-control-shared-prompt-v1`、`experiment-plan-2026-11-07-learning-material-target-800-control-shared-prompt-v1`、`experiment-plan-2026-11-07-split-actions-v6-q1-only-v1`の別protocolがある。最初の二つは通常版バンクv5、三つ目は設問1のみのバンクv6を使った。仕様版42への統合後はいずれも履歴・閲覧専用とし、回答復元ではprotocol IDに応じてv5またはv6を選ぶ。仕様版41以下は閲覧専用。

## 仕様版39の履歴条件（2026-11-06）

当時は教材内解説を新規参加者に固定し、仕様版38以下を閲覧専用とした。現行仕様版44では仕様版43以下を閲覧専用とする。

## 仕様版37の履歴条件（2026-11-04）

当時の現行コードは仕様版37 / `experiment-plan-2026-11-04-presurvey-baseline-v2`。事前アンケートv2の4段階回答を適用した。仕様版38〜43を経て現行仕様版44となり、仕様版43以下は閲覧専用。

## 仕様版36の履歴条件（2026-11-04）

この番号には`experiment-plan-2026-11-04-presurvey-baseline-v1`と`experiment-plan-2026-11-04-rag-glossary-v1`の別protocol記録がある。どちらも閲覧専用で保持し、問題バンクv5で結果を復元する。辞書v4によるRAG注釈は現行仕様版44でも維持する。

## 仕様版35の履歴条件（2026-11-03）

仕様版35当時は通常版`split-actions-v5`と学習内容v15を使用した。全27問はPR #260（507ea4a）適用後の本文で、各問は正解1・M1二つ・M3二つ・unknown一つの6択。設問1・2だけを出題・採点し、設問3は保持する。設問1のみ出題設定、ペア答え合わせ、教材用語解説モードは登録時に固定する。教材内解説モードでは当時の辞書v3を意味参照としてAIへ渡し、逐語転載せず文脈に合わせて言い換える。仕様版35の結果はv5で復元する。現行仕様版44では辞書v4、教材内解説、目標800文字、統制群の共通prompt、および3種類の固定テストモードを維持する。仕様版36〜43を含む旧protocolは閲覧専用である。詳細は[事前アンケート](docs/49_presurvey_baseline.md)、[教材モード](docs/41_learning_glossary_material_mode.md)、[文字数条件](docs/42_learning_glossary_material_length.md)、[AI指示](docs/10_ai_prompt_contracts.md)、[RAG注釈](docs/49_rag_glossary.md)、[辞書](docs/24_learning_glossary.md)、[テスト履歴](docs/44_pretest_content_revision.md)〜[docs/48](docs/48_first_question_only.md)を参照する。受入検証と実験開始承認は別に扱う。

## 設問1のみ出題する設定（導入時の履歴）

仕様版35で管理設定として導入した。仕様版40で管理設定を廃止し、現行仕様版44では現行版・基礎理解版を各3問、4用語版を4問へ固定する。旧参加者の保存値と結果復元は変更しない。詳細は[docs/48](docs/48_first_question_only.md)・[docs/50](docs/50_basic_understanding_question_mode.md)・[docs/51](docs/51_four_topic_foundation_mode.md)。

## 仕様版28の答え合わせ（履歴）

通常版のPRETEST・RETEST・内部final_testで、用語ごとの設問1・2を保存後に同じテスト画面内で本人の選択内容と正誤を示し、続行で次の用語へ進む。答え合わせ中はページ/URL遷移せず、正答・解説・内部分類を表示しない。これは仕様版28の採用時記録である。仕様版44では現行版・基礎理解版は3用語、4用語版は4用語について各1問を用語ページで出題し、回答後に同画面で確認する。4用語版は選択済み選択肢の個別正誤と設問全体の正誤を分ける。テスト全体結果は非表示とし、設定UI/APIは廃止した。受入条件、API・snapshot・条件は[docs/40](docs/40_question_pair_answer_review.md)を参照する。

## 仕様版27の採用記録

仕様版27では通常版はsplit-actions-v1の6設問・4択単一選択で、設問3はデータのみ保持した。直前の誤答設問を用語ごとにまとめて教材・確認問題へ渡し、unknownが1つでもあれば用語全体のunknownを優先して教材入力から誤答を除き、M3優先時はM1も扱った。以下の版26記述と矛盾する箇所は[docs/39](docs/39_split_assessment.md)を優先する。版27時点でBackend全1,788件の通過を確認した記録と、現在のCIが5分割である運用情報は、仕様版28の受入検証とは区別する。実AI確認・研究条件の妥当性・実験開始の承認とは区別する。

## 用語注釈の不変条件

- 現行の共通固定辞書はlearning-glossary-v4の17語で、RAG（検索拡張生成）も注釈対象にする。v1〜v3は履歴として不変で保持する。AI、事前学習、ファインチューニング、プロンプトエンジニアリング、データベース、マルチエージェント、タスク、記憶プロセスの8語を注釈から除外する。長い除外語の一部からプロンプト・エージェントを抽出せず、独立して登場した場合は補足する。確認問題自体と結果確認画面は対象外。辞書・保存・移行はdocs/24・docs/49_rag_glossary.mdを参照する。
- 注釈は表示用JSONとして保存し、現行の教材内解説では辞書を両群共通の意味参照として教材本文の生成入力に渡す。現行仕様版44は本文800文字程度を目安にするだけで、文字数による合否判定・再試行は行わない。旧版のモード別文字数契約とログは履歴として保持する。教授契約版v7は維持する。再表示はsnapshotを使い、旧教材へ後付けしない。登録語しか扱わず、AIで未知語を補わない。

このリポジトリは、卒業研究用AIチューターのアプリケーションリポジトリです。目標仕様は実験計画書に合わせたdocs、現行挙動はコード・YAML・入力型・テストを基準にしてください。実行時の現行実験仕様版は44です。受入検証と実験開始承認は別に扱ってください。

## Authoritative Documents

- `docs/00_project_summary.md` から順に `docs/19_experiment_operation_runbook.md` までを必ず読む。
- `docs/20_experiment_plan_alignment.md` を読み、目標仕様・現行実装・未対応・要確認を区別する。
- 仕様版33の履歴差分は`docs/45_pretest_memory_distractors.md`、仕様版34のv4期待値fixtureは`backend/tests/fixtures/split_assessment_v4_expected.yml`、仕様版35の追加選択肢と分類仮説は`docs/47_split_assessment_added_choices.md`、事前アンケートv1/v2は`docs/49_presurvey_baseline.md`、RAG辞書追加は`docs/49_rag_glossary.md`を参照する。問題バンクv1〜v5と辞書v1〜v3、過去の採用記録は履歴として変更しない。
- 仕様版28の答え合わせ契約・API・保存・受入条件はdocs/40_question_pair_answer_review.mdを正とする。docs/39は仕様版27の採用時記録として保持する。
- `docs/99_sources_and_notes.md` は現行計画書の出典と設計判断の根拠として扱う。旧PPTX・旧案はhistory資料であり現行要件ではない。
- 実装依頼時の初期指示は `prompt.md` を使う。

## Research Invariants

- 仕様版44の新規参加者は`experiment-plan-2026-11-09-four-topic-foundation-v1`を保存する。既存2モードを維持して第3モード`four_topic_fundamentals`を加える。4用語版のカタログ順は`transformer`、`llm_training_stages`、`multi_agent_four_topic`、`memory_process_four_topic`。各テストは各用語1問・計4問・各10択、正解A〜C・M1 D〜F・M3 G〜I・unknown Jで、3択またはJ単独。pretest/retest_1/retest_2/final_testは同じ本文・選択肢を使い、学習確認は直前の誤答Attempt snapshotを再利用する。教材RAGはTransformerの1.1.2.4、LLM学習段階の1.1.3.2を`rag_ready_教材`から検索する。専用presurveyは4用語知識4項目とAI利用2項目。集計は4問・4用語分母で別モードとして算出し、既存2モードと合算しない。仕様版43以下・旧protocolの記録を変更しない。詳細はdocs/51を参照。

- 現行コードでは新規だけ仕様版44 / `experiment-plan-2026-11-09-four-topic-foundation-v1`を保存し、仕様版43以下と旧protocolは閲覧専用とする。通常学習はv15、テスト問題モードはapplication・basic_understanding・four_topic_fundamentals。通常2モードの事前アンケートは`presurvey-baseline-v2`、4用語版は`presurvey-four-topic-baseline-v1`、事後は`posttest-10point-v3`。基本の教材内解説、辞書v4、Survey phase/version保存、設問別答え合わせ、全体結果非表示、旧バンク復元を維持する。6仮説・ログ・CSV/XLSXはモード別に分離する。教材本文800文字程度の目標と統制群の共通prompt/提案群の診断指示も維持する。既存ParticipantSurvey.phase/version/responses_jsonを使いDB列は増やさない。H5はposttest phaseだけを参照する。詳細はdocs/10・40〜44・47・48・docs/49_presurvey_baseline.md・docs/49_rag_glossary.md・docs/50_basic_understanding_question_mode.md・docs/51_four_topic_foundation_mode.md。

- 通常版事前の版9〜11、過去のV1/V2/V3/V4改訂を保持する。仕様版34では`split-actions-v4`、仕様版35では`split-actions-v5`を追加し、選択肢本文・追加案を別バンクへ保存する。仕様版27〜31は`split-actions-v1`、32はv2、33はv3、34はv4で結果を復元する。保存snapshotは変更しない。
- 全テスト・学習確認で、選択肢の文字数下限・文長比・文字数差による拒否はしない。非空・重複・役割数・教授対象の検査を維持する。教材は仕様版44で800文字程度を目安にするが、文字数による合否判定や再試行はしない。文長均一や難易度同等を保証しない。

- 新規参加者の出題・採点・確認問題復元はsnapshotされた`test_content_mode`に対応する問題バンクだけを使い、集計もモード別に分離する。旧`question_set_mode`設定APIとフィルターは廃止済みで、旧フィルター付き要求は422で拒否する。過去のeasy-mode削除手順は新しい`test_content_mode`・問題資産・記録を対象にせず、旧版へのフォールバックを実装しない。

- 研究仮説は計画書の6つ。番号はdocs/01・12・17で統一し、比較回次・集計単位・欠測の未指定部分を独断で決めない。
- 目標は大学生40名/各群20名、原則無作為割付。low設定・事前知識6項目・事前AI利用2評定・事後システム評価2/教材評価6の10段階・任意自由記述・6仮説の記述集計は実装済み。自動割付・人数上限は対象外。式・対象はdocs/12・20の承認済み定義を守る。
- 共通説明とunknownは意味や仕組みを扱う。unknownの証拠はmandatory_elements.definitionとteaching_contract.mechanism_explanation/transfer_check。旧6項目を必須に戻さない。
- 比較対象は「AIあり/なし」ではなく、「通常AIチューター」と「ログ適応型AIチューター」。
- 現行分類はM1/M3/unknownのみ。両群へ同じ用語の全フェーズの採点済み回答履歴を渡す。提案群だけに明示的な診断・対象主張・taxonomy・タイプ別教授方針を追加する。方略はbackendで固定する。
- 確認問題の診断連動規則は両群共通。統制群のLLMへ分類・診断由来段階を渡さず、共通履歴内にも診断情報を混ぜない。統制群の自然な誤り訂正は許容する。
- 被験者画面に内部分類、群名、教授方略を直接表示しない。
- テスト回答中はチャット・ヒント・即時正解を表示しない。仕様版44のapplication/basic_understandingは3用語各1問、four_topic_fundamentalsは4用語各1問を用語ページで出題する。通常2モードは単一選択、4用語版は正解3つまたはJ単独の複数選択。回答後は同一画面内で本人の選択内容と正誤を示す。4用語版では選択済み選択肢の個別正誤と設問全体の正誤を分け、未選択肢の正誤は示さない。過去の設問ペア表示契約はdocs/40を参照する。
- 学習確認は1用語・1セッションあたり最大3回答。事前テスト後のテストはfinal_testも含め最大2回、事前込み最大3回。未回答を含む採点済みバッチを1回とし、全問未回答は採点しない。1回目未達は学習、2回目未達は未達のままアンケートへ進める。満点ならいつでもアンケートへ進める。
- 現行の新規テストはParticipant.test_content_modeに応じてapplication=`split-actions-v5`、basic_understanding=`split-actions-basic-v1`、four_topic_fundamentals=`split-actions-four-topic-v1`を使う。最初の2モードは各3用語・計3問、4用語モードは各1問・計4問。すべて各モードの設問1を出題し、applicationの設問2・3はバンクに保持する。4用語バンクはA〜C正解、D〜F=M1、G〜I=M3、J=unknownの10択。activeキーはpretest_v1、retest_v1/v2。final_testは各モードのretest_v1と同じ内容を使う。旧バンクは復元用に保持し、版付きconstruct_keyで既存本文・選択肢を上書きしない。学習確認は直前テストの保存snapshotを利用する。通常の学習v15と教材条件は維持する。
- 選択肢配置は管理画面のDB保存設定で切り替える。既定値は `debug_fixed` で、新規参加者だけに適用する。実験データ収集前に `randomized` へ変更し、正答位置の手掛かりがないことを確認する。判定は表示ラベルでなく選択肢ID・内部メタデータで行う。
- 現行コードでは新規だけ仕様版44 / `experiment-plan-2026-11-09-four-topic-foundation-v1`を保存し、`retest_cycles_completed=0`で開始する。この列は学習後retestだけを数え、共通上限用のpost_pretest_tests_completedは採点済みfinal_testを加えて導出する。共通回数用DB列は追加しない。Participantの教材モード、テスト表示・答え合わせ・出題単位・問題モードを新規登録時に固定する。旧RuntimeSetting設定列は履歴保全のため残し、廃止済み設定は参照・更新しない。仕様版43以下、旧protocol_id/NULL・未対応版は閲覧専用。旧行の版・進行・回答・評価・回数を更新/削除せず、補修も版とprotocol_idで限定する。
- 両群の教材の小見出し・数・順序・まとめ方はAIが決める。冒頭の##用語名と非空の###セクションだけを要求し、実験群の必須教授内容・transfer_checkは本文内証拠で検証する。固定見出しから証拠文を自動補正しない。
- 教材内のtransfer_checkは維持するが、独立した追加テスト・旧支援量・自由回答処理を戻さない。
- application/basic_understandingの対象は`llm_knowledge`、`multi_agent`、`memory_process`。four_topic_fundamentalsの対象は`transformer`、`llm_training_stages`、`multi_agent_four_topic`、`memory_process_four_topic`。

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
- 目標プロンプトの引用と現行コードの送信原文を区別する。既存ログを新6仮説の確定済み評価値として扱わない。
- 実装開始の依頼では、仕様にない独自判断を最小限にし、判断した内容はREADMEまたは該当docsに追記する。
- 要確認事項はdocs/20で管理し、決定されていない分析方法・新しいunknownの検査項目を実装者が補完しない。その他の運用はdocs/19・99を参照する。
