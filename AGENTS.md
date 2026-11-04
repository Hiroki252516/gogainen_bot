# Repository Instructions for Codex

## 仕様版37の現行条件（2026-11-04）

現行コードは仕様版37 / `experiment-plan-2026-11-04-presurvey-baseline-v2`。仕様版36以下は閲覧専用で、既存参加者・回答・教材・snapshotを更新しない。新規参加者は同意後に必須事前アンケート（`presurvey-baseline-v2`）を回答し、その後に事前テストへ進む。事前知識6項目は「知らない／聞いたことがある／意味を知っている／説明できる」の4択で、AI利用頻度・AI活用自己評価の2項目も保存する。事後アンケートは`posttest-10point-v3`でシステム評価2項目・教材評価6項目・任意自由記述を保存し、旧v1/v2の事後記録は不変で保持する。H5はphase=posttestだけを参照する。詳細は[docs/49](docs/49_presurvey_baseline.md)。

## 仕様版35の履歴条件（2026-11-03）

現行コードは仕様版35 / `experiment-plan-2026-11-03-split-added-choices-v1`。仕様版34以下は閲覧専用で、既存参加者・教材・snapshotを更新しない。通常版テストは`split-actions-v5`を使い、v4を土台に全27設問へ追加M1・M3を収録し、PR #260の選択肢56本文の修正を反映する。v4自体は履歴バンクとして保持する。正解1・M1二つ・M3二つ・unknown一つの6択で、デバッグ配置はA=正解、B/C=M1、D/E=M3、F=unknown。設問1・2だけを出題・採点し、設問3はバンクに保持する。ランダム配置ではunknownをFに固定し、残る5択を決定的にA〜Eへ配置する。v1は仕様版27〜31、v2は32、v3は33、v4は34、v5は35の履歴バンク対応。誤答設問の学習確認は保存済みsnapshotの本文・選択肢を再利用する。直前回次は検証済みtest_roundの順序で決め、回答時刻やUUIDによって別の回次を選ばない。教材の用語解説モードは新規参加者のみ登録時snapshotで固定する。「教材内解説」だけ辞書v3を両群共通の教材生成任意入力として渡し、定義文を転載せず、意味を保って文脈に合わせて言い換えるよう指示する。本文で使う登録語だけを説明し、文字数契約（注釈欄のみ600〜800、教材内解説600〜1200）を維持する。教材内解説では教材用注釈欄を隠し、回答後解説・テスト注釈と保存snapshotを維持する。詳細は[docs/24](docs/24_learning_glossary.md)・[docs/43](docs/43_glossary_definition_paraphrase.md)・[docs/44](docs/44_pretest_content_revision.md)・[docs/45](docs/45_pretest_memory_distractors.md)・[docs/46](docs/46_split_assessment_choice_wording.md)・[docs/47](docs/47_split_assessment_added_choices.md)。受入検証と実験開始承認は別に扱う。

## 設問1のみ出題する設定（2026-11-03）

管理画面の「設問1のみ出題」は初期値OFF。新規参加者にfirst_question_onlyを登録時固定し、ONなら各用語の設問1だけ（計3問）、OFF/旧NULLなら設問1・2（計6問）を出題・採点する。事前・再テスト1/2・内部final_test・学習確認を対象とする。設問2・3と旧snapshotを保持する。仕様版35・protocol・v5を維持し既存参加者を補完しない。指標分母は出題条件に合わせ、3問/6問の集計を混ぜない。以降の6設問固定の記述にはこの条件分岐を優先する。詳細は[docs/48](docs/48_first_question_only.md)。

## 2026-10-30 易しい版の停止

易しい版停止時点（仕様版28・protocol維持）で新規参加者を通常版に固定した。保存済みRuntimeSettingの旧`easy`値も新規登録には使わず、管理画面は通常版固定を表示する。既存易しい版参加者は閲覧専用で、参加者向け画面/APIから再開・回答できない。易しい版の群集計・仮説CSVは停止し、版指定は422とする。参加者一覧・個別ログ・参加者別CSV・全件生ログは参照可能。既存参加者、回答、snapshot、評価、YAML、問題ID、DB列は変更・削除しない。現在の詳細と検証状況は[docs/22](docs/22_question_set_modes.md)、[docs/14](docs/14_testing_acceptance.md)、[docs/20](docs/20_experiment_plan_alignment.md)を参照する。

## 仕様版28の答え合わせ（履歴）

通常版のPRETEST・RETEST・内部final_testで、用語ごとの設問1・2を保存後に同じテスト画面内で本人の選択内容と正誤を示し、続行で次の用語へ進む。答え合わせ中はページ/URL遷移せず、正答・解説・内部分類を表示しない。新しい「設問ごとの答え合わせ」スイッチは初期値ONで、通常版の新規参加者だけ登録時に固定する。既存のPRETEST全体結果表示スイッチは独立維持する。これは仕様版28の採用時記録である。受入条件、API・snapshot・条件は[docs/40](docs/40_question_pair_answer_review.md)を参照する。

## 仕様版27の採用記録

仕様版27では通常版はsplit-actions-v1の6設問・4択単一選択で、設問3はデータのみ保持した。直前の誤答設問を用語ごとにまとめて教材・確認問題へ渡し、unknownが1つでもあれば用語全体のunknownを優先して教材入力から誤答を除き、M3優先時はM1も扱った。易しい版の当時の受入条件は履歴資料であり、現在は停止済み。以下の版26記述と矛盾する箇所は[docs/39](docs/39_split_assessment.md)を優先する。版27時点でBackend全1,788件の通過を確認した記録と、現在のCIが5分割である運用情報は、仕様版28の受入検証とは区別する。実AI確認・研究条件の妥当性・実験開始の承認とは区別する。

## 用語注釈の不変条件

- 現行の共通固定辞書はlearning-glossary-v3の16語。仕様版26のv2は履歴として不変で保持する。AI、事前学習、ファインチューニング、プロンプトエンジニアリング、RAG、データベース、マルチエージェント、タスク、記憶プロセスの9語を注釈から除外する。長い除外語の一部からプロンプト・エージェントを抽出せず、独立して登場した場合は補足する。確認問題自体と結果確認画面は対象外。辞書・保存・移行はdocs/24を参照する。
- 注釈は表示用JSONとして保存し、既定モードではAI入力・生成本文・共通回答履歴に混ぜない。教材内解説モードだけ辞書を両群共通の任意入力として渡す。教材文字数はannotation_onlyで600〜800、integrated_materialで600〜1200。教授契約版v7は維持する。再表示はsnapshotを使い、旧教材へ後付けしない。登録語しか扱わず、AIで未知語を補わない。

このリポジトリは、卒業研究用AIチューターのアプリケーションリポジトリです。目標仕様は実験計画書に合わせたdocs、現行挙動はコード・YAML・入力型・テストを基準にしてください。実行時の現行実験仕様版は37です。受入検証と実験開始承認は別に扱ってください。

## Authoritative Documents

- `docs/00_project_summary.md` から順に `docs/19_experiment_operation_runbook.md` までを必ず読む。
- `docs/20_experiment_plan_alignment.md` を読み、目標仕様・現行実装・未対応・要確認を区別する。
- 仕様版33の履歴差分は`docs/45_pretest_memory_distractors.md`、仕様版34のv4比較表対応は`docs/46_split_assessment_choice_wording.md`、仕様版35の追加選択肢と分類仮説は`docs/47_split_assessment_added_choices.md`を参照する。v1〜v5と過去の採用記録は履歴として変更しない。
- 仕様版28の答え合わせ契約・API・保存・受入条件はdocs/40_question_pair_answer_review.mdを正とする。docs/39は仕様版27の採用時記録として保持する。
- `docs/99_sources_and_notes.md` は現行計画書の出典と設計判断の根拠として扱う。旧PPTX・旧案はhistory資料であり現行要件ではない。
- 実装依頼時の初期指示は `prompt.md` を使う。

## Research Invariants

- 現行コードでは新規だけ仕様版37 / `experiment-plan-2026-11-04-presurvey-baseline-v2`を保存し、仕様版36以下は閲覧専用とする。通常版は学習15・テストsplit-actions-v5。テスト・学習、設問1のみ設定、注釈、旧バンク復元の条件は上記およびdocs/47・48に従う。新規参加者は同意後にpresurvey-baseline-v2の必須8項目を回答してから事前テストへ進む。用語知識6項目は4段階文字列カテゴリで記録する。posttest-10point-v3はシステム評価2・教材評価6・任意自由記述を保存する。旧posttest v1/v2回答は変更せず、H5はphase=posttestだけを参照する。ParticipantSurveyのphase/version/responses_jsonを使い、DB列を追加しない。アンケート仕様はdocs/49。

- 通常版事前の版9〜11、過去のV1/V2/V3/V4改訂を保持する。仕様版34では`split-actions-v4`、仕様版35では`split-actions-v5`を追加し、選択肢本文・追加案を別バンクへ保存する。仕様版27〜31は`split-actions-v1`、32はv2、33はv3、34はv4で結果を復元する。保存snapshotは変更しない。
- 両版の全テスト・学習確認で、選択肢の文字数下限・文長比・文字数差による拒否はしない。非空・重複・役割数・教授対象の検査を維持する。教材モード別の文字数検査（注釈欄のみ600〜800、教材内解説600〜1200）とは区別し、文長均一や難易度同等を保証しない。

- 問題版は現行の新規登録では通常版に固定する。旧easy値を持つ参加者の再開・回答を拒否するが、易しい版のYAML・Question ID・snapshotと記録は履歴復元用に保持する。問題variantや保存版が欠落しても他版へフォールバックしない。
- 易しい版の旧生成条件・explanation_level=beginnerは履歴仕様として保存する。易しい版の新規出題・教材生成と群集計・6仮説CSVは停止し、易しい版指定の集計APIは422を返す。個別ログ・参加者CSV・全件生ログは維持する。詳細はdocs/22。

- 研究仮説は計画書の6つ。番号はdocs/01・12・17で統一し、比較回次・集計単位・欠測の未指定部分を独断で決めない。
- 目標は大学生40名/各群20名、原則無作為割付。low設定・事前知識6項目・事前AI利用2評定・事後システム評価2/教材評価6の10段階・任意自由記述・6仮説の記述集計は実装済み。自動割付・人数上限は対象外。式・対象はdocs/12・20の承認済み定義を守る。
- 共通説明とunknownは意味や仕組みを扱う。unknownの証拠はmandatory_elements.definitionとteaching_contract.mechanism_explanation/transfer_check。旧6項目を必須に戻さない。
- 比較対象は「AIあり/なし」ではなく、「通常AIチューター」と「ログ適応型AIチューター」。
- 現行分類はM1/M3/unknownのみ。両群へ同じ用語の全フェーズの採点済み回答履歴を渡す。提案群だけに明示的な診断・対象主張・taxonomy・タイプ別教授方針を追加する。方略はbackendで固定する。
- 確認問題の診断連動規則は両群共通。統制群のLLMへ分類・診断由来段階を渡さず、共通履歴内にも診断情報を混ぜない。統制群の自然な誤り訂正は許容する。
- 被験者画面に内部分類、群名、教授方略を直接表示しない。
- テスト回答中はチャット・ヒント・即時正解を表示しない。通常版では同じ用語の設問1・2を保存後、docs/40に従い同一画面内で本人の選択内容と正誤を示す。正答選択肢は表示しない。
- 学習確認は1用語・1セッションあたり最大3回答。事前テスト後のテストはfinal_testも含め最大2回、事前込み最大3回。未回答を含む採点済みバッチを1回とし、全問未回答は採点しない。1回目未達は学習、2回目未達は未達のままアンケートへ進める。満点ならいつでもアンケートへ進める。
- 現行通常版テストはsplit-actions-v5で、1用語2設問×3用語の6設問・各6択。設問3もバンクには保持する。PR #260適用後のv5本文をPRETEST・RETEST1/2へ保存する。易しい版とアーカイブのYAMLは`backend/app/seed/content/standard/`、`easy/`、`archive/`に分ける。通常版activeキーはpretest_v1、retest_v1/v2。final_testはretest_v1を共用し、その後は全用語をretest_v2へ進める。用語別回答件数で回次を選ばない。scenario-actions-v9とsplit-actions-v1〜v5を含む旧問題を保持し、版付きconstruct_keyで本文・選択肢を上書きしない。学習確認は直前PRETESTの保存snapshotを利用する。学習確認v15の9問は維持するが、3セッション目は新規経路で到達しない。
- 選択肢配置は管理画面のDB保存設定で切り替える。既定値は `debug_fixed` で、新規参加者だけに適用する。実験データ収集前に `randomized` へ変更し、正答位置の手掛かりがないことを確認する。判定は表示ラベルでなく選択肢ID・内部メタデータで行う。
- 現行コードでは新規だけ仕様版37 / `experiment-plan-2026-11-04-presurvey-baseline-v2`を保存し、`retest_cycles_completed=0`で開始する。この列は学習後retestだけを数え、共通上限用のpost_pretest_tests_completedは採点済みfinal_testを加えて導出する。共通回数用DB列は追加しない。RuntimeSetting/Participant.learning_material_glossary_modeはnullableで保存し、既存行へ補完しない。仕様版36以下、旧protocol_id/NULL・未対応版は閲覧専用。旧行の版・進行・回答・評価・回数を更新/削除せず、補修も版とprotocol_idで限定する。
- 両群の教材の小見出し・数・順序・まとめ方はAIが決める。冒頭の##用語名と非空の###セクションだけを要求し、実験群の必須教授内容・transfer_checkは本文内証拠で検証する。固定見出しから証拠文を自動補正しない。
- 教材内のtransfer_checkは維持するが、独立した追加テスト・旧支援量・自由回答処理を戻さない。
- 現行MVP対象用語は `llm_knowledge`、`multi_agent`、`memory_process` の3項目とする。

## AI Backend Rules

- OpenAI APIキーを要求しない。
- OpenAI SDKで通常APIを直接呼ばない。
- AI呼び出しは必ず `AIBackend` インターフェース経由にする。
- AIタスクは教材生成・正答要約・誤答解説だけ。採点・分類・状態更新・方略決定はbackendで行う。
- 通常実行では `CodexAppServerBackend` を使い、ユーザーのChatGPT/Codexログイン済みapp-serverへ接続する。
- アプリ既定のAI設定は `gpt-6-luna / low`。管理画面では `gpt-6.1-sol` / `gpt-6-luna` と low/medium/highを一時切替でき、両群・進行中参加者の次回呼び出しから適用する。DBには保存せずbackend再起動でCODEX_MODEL/CODEX_REASONING_EFFORTへ戻す。研究計画書原本のgpt-5.6-luna記載は変更せず、アプリ設定との差を明示する。同一参加者内での実験中切替はモデル混在を生むため、収集時は設定を固定する。
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
