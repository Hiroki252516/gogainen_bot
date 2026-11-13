# 学習ログ駆動型AIチューター

2026-11-12現行条件：新規参加者は仕様版54 / `experiment-plan-2026-11-12-four-topic-instruction-tuning-perfect-test-early-exit-posttest-material-amount-clarity-removal-v1`で登録し、問題モードは4用語版に固定します。問題バンクは`split-actions-four-topic-v3`、事前アンケートは`presurvey-four-topic-baseline-v4`です。標準2モード用の事前アンケート`presurvey-baseline-v4`は過去記録の復元に使います。現行同意文書は`consent-2026-11-12-revised-v1`です。研究用コードは登録処理中に検証するだけで、DB・冪等性記録・ログ・出力・AI入力・ブラウザ保存には残しません。学籍番号はアプリで取得せず、研究用コード・学籍番号・参加者IDの対応表は研究者がアプリ外で管理します。対応表の管理UI/APIはなく、旧対応表SQLiteと行は保全します。事後アンケートは`posttest-5point-v4`で、システム評価1項目・教材評価6項目・任意自由記述を含み、教材量の質問は「教材の量はどの程度でしたか」です。必要な全設問が採点済みかつ全問正解なら、事前・再テスト1/2・内部`final_test`後に結果表示snapshotに応じて確認後または直接surveyへ進み、学習・後続テストを省略します。H5は中核4項目の数値平均、難易度・教材量は別分布です。仕様版53の複数protocolと仕様版51・52のprotocolは当時の記録復元用に保持し、仕様版53以下の参加者・回答・snapshotは保全して変更しません。尺度・H5の妥当性、問題の難易度・同等性、研究上の承認は未確認です。[事前アンケート](docs/49_presurvey_baseline.md)、[4用語版](docs/51_four_topic_foundation_mode.md)、[事後アンケート](docs/52_posttest_five_point_evaluation.md)、[評価指標](docs/12_evaluation_metrics.md)、[受入記録](docs/14_testing_acceptance.md)。

仕様版48では事前アンケートを経験・理解度の条件付き回答へ改訂し、仕様版49では事後アンケートを5段階化しました。仕様版50で質問文を更新し、仕様版51・52で問題バンク・用語表記・事後項目を別protocolとして更新しました。仕様版53の二つのprotocolを仕様版54で統合し、全テスト満点後の早期終了と事後アンケートv4を適用します。変更は新規参加者だけに適用し、既存回答には遡及しません。

2026-11-07履歴：仕様版41には`experiment-plan-2026-11-07-fixed-admin-settings-control-shared-prompt-v1`と`experiment-plan-2026-11-07-learning-material-target-800-control-shared-prompt-v1`の異なるprotocolがありました。仕様版42では両方の変更を統合し、仕様版41の両protocolは閲覧専用です。2026-11-03履歴：仕様版35では管理画面の「設問1のみ出題」で各用語1問（計3問）と設問1・2（計6問）を切り替えていました。仕様版40で計3問に固定し、設定UI/APIを廃止しています。導入時の記録は[docs/48](docs/48_first_question_only.md)を参照してください。以下の過去版の説明は採用時の記録です。

仕様版33 / `experiment-plan-2026-11-01-pretest-content-revision-v2`の採用時は、通常版PRETESTの指定選択肢本文を`split-actions-v3`へ更新しました。v1（仕様版27〜31）とv2（仕様版32）、旧データ・回答snapshotを履歴として保持し、当時は仕様版32以下を閲覧専用としました。RETEST1/2・内部final_test、設問数・採点、設問ペア答え合わせは維持しました。誤答PRETEST設問の学習確認では回答時の保存snapshotを再利用します。教材用語解説は登録時に固定し、本文の文字数条件とv3辞書による言い換え指示を追加しました。[仕様版27の採用記録](docs/39_split_assessment.md)、[仕様版28の答え合わせ](docs/40_question_pair_answer_review.md)、[仕様版29の用語解説モード](docs/41_learning_glossary_material_mode.md)、[仕様版30の文字数条件](docs/42_learning_glossary_material_length.md)、[仕様版31の辞書定義と言い換え](docs/43_glossary_definition_paraphrase.md)、[仕様版32のPRETEST改訂](docs/44_pretest_content_revision.md)、[仕様版33のPRETEST選択肢文面改訂](docs/45_pretest_memory_distractors.md)を参照してください。各変更の受入検証状況は[docs/14](docs/14_testing_acceptance.md)を参照してください。実験開始の承認や実AIでの確認とは区別します。

## 用語の補足をテストにも表示（仕様版26）

指定の9用語を注釈から除外し、残る16語を教材・回答後解説に加えて事前テスト・再テストにも表示します。テストは問題文・全選択肢の登場語を表示し、現行通常版の両群で共通です。内部final_testも対象です。

仕様版31当時の新規参加者に適用しました。v2は仕様版26当時の辞書履歴として無変更で残し、v3では指定4語の定義を更新しました。教材内解説モードでは定義を意味参照として使い、教材の文脈に合わせて言い換えます。現行辞書v4のRAG追加と履歴は[対象語・保存・移行と注意事項](docs/24_learning_glossary.md)を参照してください。

## 管理画面のパスワード

`/admin` を開くと、パスワード入力のポップアップが表示されます。パスワードは **`abc`** です。

管理API・CSV・seed・管理用の評価再計算も認証が必要です。認証は30分で失効し、「管理画面をロック」とbackend再起動でも解除されます。画面を離れる際にもログアウトを要求し、再入場・再読み込みでは再入力を求めます。ロック時に通信が失敗した場合は画面を隠したまま、認証解除の再試行を求めます。パスワードはブラウザのコードやlocalStorageへ保存せず、backendの `ADMIN_PASSWORD` で変更できます。変更後はbackendを再起動してください。セッションはbackendの単一プロセス内で管理します。研究用コード・学籍番号・参加者IDの対応表を管理するAPIは提供しません。

これは指定された共通パスワードによるローカル実験用の保護です。READMEを読める人にもパスワードが分かるため、研究者だけが扱う環境で使用します。同意内容の確定・実AI確認等の本実験開始条件は別途確認してください

## リリース運用

`main`へのpushを契機にRelease PleaseがリリースPRを作成・更新します。機能PRのマージだけではタグやGitHub Releaseは作られません。リリースPRの変更内容と`CHANGELOG.md`を確認してマージすると、バージョン更新、`vX.Y.Z`タグ、GitHub Releaseが作成されます。デプロイや成果物の公開は行いません。

バージョンはアプリ全体で管理し、初期値は`0.1.0`です。コミットはConventional Commits形式にします。`feat:`はminor、`fix:`はpatch、`feat!:`など`!`付きはmajorの更新になります。`docs:`や`chore:`だけの変更では通常リリースPRは作成されません。

Release PleaseのworkflowにはGitHub Appのinstallation tokenを使います。Repository variable `APP_CLIENT_ID`とRepository secret `APP_PRIVATE_KEY`を設定し、Appをこのrepositoryへインストールしてください。AppにはContents、Issues、Pull requestsの書き込み権限が必要です。App tokenで作成したリリースPRでは既存のPR CIが実行されます。

## 確認問題・再テストV2の更新（仕様版25採用時の記録）

通常版のLLM知識・記憶プロセスの確認V2と、3用語の再テストV2を指定文へ更新しました。LLM再テストは大学・教職員版を採用します。対象の確認V2はapplicationへ変更し、合意した3組だけ同文再使用を許可します。V1・内部final_test・マルチエージェント確認V2・採点・回数上限は維持します。

新規だけ仕様版25・通常版学習v15／テストscenario-actions-v9を使用し、旧学習v14・旧テストv8と既存記録を保持します。仕様版24以下は閲覧専用です。[問題全文・例外の範囲・分類理由・保存契約](docs/38_round_two_revision.md)を参照してください。

## 再テストV1の5選択肢改訂（仕様版24採用時の記録）

通常版マルチエージェントV1のE/Fと、記憶プロセスV1のE/H/Iを指定文へ更新しました。場面・設問・段落表示と判定は維持し、内部final_testも同じV1を共用します。他の問題・訂正情報・教授プロンプト・採点・回数上限は変更しません。

新規だけ仕様版24・テストscenario-actions-v8を使用し、旧v7と既存記録を保全します。学習版は通常版14です。仕様版23以下は閲覧専用です。[本文・分類理由・保存と検証条件](docs/37_multi_memory_retest_one_revision.md)を参照してください。

## LLM知識の再テストV1改訂（仕様版23採用時の記録）

通常版LLM知識・再テストV1の場面説明とA/B/D/G/H/Iを指定文へ更新しました。場面4項目と設問の5段落表示とし、内部final_testも共用します。他の問題・訂正情報・教授プロンプト・採点・回数上限は維持します。

新規だけ仕様版23・テストscenario-actions-v7を使用し、旧v6と既存記録を保全します。学習版は通常版14です。仕様版22以下は閲覧専用です。[本文・分類理由・保存と検証条件](docs/36_llm_retest_one_revision.md)を参照してください。

## 初回確認問題4か所の更新（仕様版22採用時の記録）

通常版マルチエージェントV1のG、記憶プロセスV1の場面説明後半・F・Hを指定文へ更新しました。判定と記憶V1の3段落表示を維持し、他の問題・AI指示・採点・回数上限は変更しません。

新規だけ仕様版22・通常版学習v14を使用し、旧v13以前と既存記録を保全します。仕様版21以下は閲覧専用です。通常版テストはscenario-actions-v6のままです。[本文・分類理由・保存と検証条件](docs/35_multi_memory_round_one_revision.md)を参照してください。

## LLM知識の確認問題D・Hの更新（仕様版21採用時の記録）

通常版のLLM知識・初回確認問題のD（M1）とH（M3）を指定文へ更新しました。他の選択肢・問題、直前に改訂した再テスト4問、訂正情報・AI指示・採点・回数上限は変更しません。

新規だけ仕様版21・通常版学習v13を使用し、旧学習v12と既存記録を保全します。通常版テストはscenario-actions-v6のままです。仕様版20以下は閲覧専用です。[今回の本文・分類理由・保存と検証条件](docs/34_llm_round_one_dh_revision.md)を参照してください。

## 前回のF改善（仕様版11採用時の記録）

通常版の事前テスト問1のFを指定文へ変更しました。M1判定・訂正情報・他の本文は維持します。通常版テストはscenario-actions-v4、protocolはexperiment-plan-2026-10-25-pretest-f-wording-v1です。旧v3をアーカイブと別DB IDで保全し、新規参加者だけに適用します。版10以下は閲覧専用です。

## 前回のA・B改善（仕様版10採用時の記録）

通常版の事前テスト問1のA・Bを、実装する処理が分かる表現へ変更しました。両方とも正解のままで、問題文・他の選択肢・訂正情報は変更しません。通常版テストはscenario-actions-v3、protocolはexperiment-plan-2026-10-25-pretest-wording-v1です。旧v2はアーカイブと別DBレコードで保全し、新規参加者だけに適用します。旧版9以下は閲覧専用で、途中の記録を付け替えません

## 前回の事前テスト改善（仕様版9採用時の記録）

通常版の事前テスト6選択肢と対応する訂正情報を改訂し、テストバンクをscenario-actions-v2へ更新しました。旧v1はアーカイブと旧DBレコードで保全し、新規参加者だけに適用します。全テスト・学習確認で選択肢の数値的な文長検査を撤廃しました。当時は教材600〜800文字条件を維持しましたが、現行の教材文字数は仕様版42の目標値のみです。[問題全文と分類根拠](docs/21_assessment_action_questions.md)、[版管理](docs/20_experiment_plan_alignment.md)、[現行の文字数目標](docs/42_learning_glossary_material_length.md)を参照してください。

## 用語の補足

教材・事前テスト・再テストの注釈は、広い画面では右側の追従欄に、狭い画面では開閉パネルに表示します。回答後解説の注釈は解説の下に表示します。確認問題自体・結果確認画面は対象外です。未登録語・除外語には注釈が付きません。現行の教材内解説モードでは辞書を意味参照として教材生成入力へ渡し、本文800文字程度を目安に生成します。文字数の上下限による合否判定や長さを理由にした再生成は行いません。過去のモード別文字数契約は履歴として保持します。[辞書全文・保存と運用](docs/24_learning_glossary.md)、[文字数目標と履歴](docs/42_learning_glossary_material_length.md)を参照してください。

仕様版39で新規参加者の教材モードを教材内解説に固定しました。現行仕様版54でも維持します。管理画面の教材モード切替UIとモード管理APIはなく、教材右側の注釈欄を隠し、回答後解説・テストの注釈と保存snapshotは維持します。辞書定義を意味の参照として文脈に合わせて言い換えます。教材本文は800文字程度を目安にし、文字数の上下限検証と長さを理由にした再生成は行いません。[AI指示](docs/10_ai_prompt_contracts.md)、[仕様・条件差](docs/41_learning_glossary_material_mode.md)、[文字数目標](docs/42_learning_glossary_material_length.md)、[辞書言い換え](docs/43_glossary_definition_paraphrase.md)。

2026-10-21履歴: 同意画面に学籍番号を必須入力し、対応表の表示・CSV・削除をアプリ内で行う仕様を採用していた時期がある。対応表SQLiteファイルと既存行は保全するが、2026-11-12以降、対応表管理API/UIは提供しない。

2026-11-11履歴（fix/issue-317）: 研究用コードを分離SQLiteへ保存し、管理画面/APIで対応表を管理していた時期がある。この保存・管理機能は2026-11-12に廃止した。既存の別SQLiteファイルと行は参照・移行・削除せず保持し、参加者の明示的な削除時だけ該当IDの行を後処理する。

2026-11-12現行: 同意書には研究責任者の連絡先、データの保存場所、外付けUSBでの対応表保管、10年間の保管を記載します。新規登録では研究用コードを一時受信し、データベース等には保存しません。研究者は外部Excel対応表を別途管理し、撤回時の照合・アプリ内参加者削除・外部コピーの取扱いを行います。今回の文書・実装変更は指導教員または研究倫理上の承認を意味しません。詳細は[データ保護](docs/15_security_privacy.md)、[API仕様](docs/08_backend_api_spec.md)、[運用手順](docs/19_experiment_operation_runbook.md)を参照してください。

Wordと承認された実装計画に沿い、教材・low設定・新アンケート・6仮説の記述集計を実装しています。[採用判断と残課題](docs/20_experiment_plan_alignment.md)と[評価定義](docs/12_evaluation_metrics.md)を先に確認してください。

現行の新規参加者には仕様版54の統合protocolを保存します。仕様版53以下、NULL・未対応版の参加者は閲覧・CSV出力専用です。進行・削除・補修・再計算・現行集計を行わず、版・回数・注釈・教材解説モード・問題モードを補完しません。ParticipantとRuntimeSettingのnullable設定列や保存済み記録は書き換えません。

このリポジトリは、卒業研究で使う「誤概念タイプと学習ステージに基づく AI・情報系専門用語の概念理解支援システム」の仕様と実装を含みます。

`docs/` 以下に研究・設計仕様、`backend/` にFastAPIアプリ、`frontend/` にNext.jsアプリがあります。過去の現行版・基礎理解版は`llm_knowledge`、`multi_agent`、`memory_process`、4用語版は`transformer`、`llm_training_stages`、`multi_agent_four_topic`、`memory_process_four_topic`を対象とします。新規参加者は4用語版に固定され、既存参加者のsnapshotには遡及しません。

## 研究の要点

### 現行の問題

新規参加者は4用語版に固定します。管理画面の問題モード切替はなく、互換APIは4用語版の固定値を返します。4用語版はTransformer、LLMの学習段階、マルチエージェント、記憶プロセスの4問を10択で出題し、3つ選択またはJ単独とします。テストと学習確認は参加者snapshotに応じて復元し、6仮説・参加者別出力はモードごとに分離します。必要な全設問が採点済みで全問正解した事前・再テスト1/2・内部`final_test`の後は、結果表示snapshotに従ってsurveyへ進み、学習・後続テストを省略します。未達時は誤答用語の学習を含む既存経路を続けます。内部`final_test`は過去記録復元用に維持し、新規通常経路では使用しません。仕様版53以下の参加者記録は当時の問題・アンケート版で復元し、現行モードへ付け替えません。研究用コードは登録時だけ検証し、アプリには保持しません。対応表はアプリ外で研究者が管理し、学籍番号入力・対応表管理UI/APIはありません。

研究の比較対象は「AIを使うかどうか」ではありません。両群とも同じ種類の学習履歴を参照する通常AIを使い、実験群だけにbackendの明示的な診断・修正対象・誤概念の定義・タイプ別教授方針を追加した効果を比較します。統制群が生の回答履歴から自然に誤りを訂正することは許容し、「誤概念対応全般の有無」の比較とは位置づけません。

目標の研究仮説は、計画書の仮説一覧に合わせて次の6つです。分析表に残る古い番号は使わず、未指定の集計条件は独自に決めません。

1. 実験群は、統制群よりも、テスト間の正答率の伸びが大きい。
2. 実験群は統制群よりも、再テストで満点に到達するまでの学習セッション回数が少ない。
3. 実験群は統制群よりも、学習セッションで扱う一用語当たりの周回数が少ない。
4. 実験群は統制群よりも、同じ誤答タイプを再び選ぶ割合が低い。
5. 教材を閲覧した参加者において、実験群は統制群よりも、学習後アンケートの教材の評価が高い。
6. 実験群は統制群よりも、再テストで満点に到達した参加者の割合が高い。

大学生40名・各群20名、原則無作為割付が研究目標です。Word計画書のモデル記載はgpt-5.6-luna / lowですが、アプリ側の運用基準はgpt-6-luna / lowです。仕様版54でも教材生成は両群に共通指示・共通入力を使い、提案群だけに診断・タイプ別教授指示を追加します。統制群の`teaching_strategy`値は出力Schemaで固定しますが、方略を説明する自然言語指示は送りません。現行事後アンケートはシステム評価1・教材評価6の1〜5段階と任意自由記述です。

**過去の対応記録（仕様版39まで）:** 計画書に沿う共通/統制群指示、unknownの定義・仕組み・適用確認、low既定値、用語の事前知識6項目・一般4/教材6の10段階・任意自由記述、教材表示ログ、6仮説の管理表示・専用CSVを追加しました。仕様版40で統制群の群別自然言語指示を削除し、仕様版43でも共通指示のみを使います。仕様版41から教材本文800文字程度を目安とし、長さによる合否判定・再生成を行いません。旧アンケート値は変換せず版付きJSONへ保存します。自動割付・各群20名上限・正答位置の復旧は対象外です。管理認証は冒頭の2026-10-27追加分を参照してください。AIモデルは既定gpt-6-lunaで、モデル・推論レベル・Fast mode設定はDBへ保存しない一時的なbackend内設定です。Fast modeは使用量が増えるため、実験中は設定を固定してください。

これは研究上の評価目的です。新規参加者は事前テスト後に最大2回の再テストを受けます。必要な全設問が採点済みで全問正解した場合、事前・再テスト1/2のいずれでも、結果表示snapshotに応じて確認後または直接surveyへ進み、学習・後続テストを省略します。事前未達者は誤答用語を学習し、再テスト1未達後も誤答用語の学習を挟んで再テスト2へ進みます。再テスト2採点後は正誤にかかわらずsurveyへ進みます。内部`final_test`は履歴復元用に維持し、新規通常経路では使用しません。未回答を含む採点バッチも1回とし、全問未回答の採点は拒否します。早期終了の測定特性・研究上の承認を前提にしません。

問題YAMLは`backend/app/seed/content/standard/`（現行問題）と`archive/`（旧問題）に分けています。仕様版54の新規参加者は`four_topic_fundamentals`に固定され、`four_topic_fundamentals_v3.yml`を使って4用語各1問（計4問）を出題します。`split_assessment_v5.yml`（現行版）と`split_assessment_basic_v1.yml`（基礎理解版）は過去参加者の記録復元用に保持し、新規登録では選択しません。4用語版の事前・再テスト1/2は同じ問題と選択肢を使い、A〜Cの3つまたはJ単独を選びます。必要な全設問が採点済みで全問正解なら、事前・再テスト1/2のいずれでもそのテスト後に学習・後続テストを省略しsurveyへ進みます。未達者は誤答対象を学習し、最大2回の再テストへ進みます。内部`final_test`は過去記録の復元契約として維持し、新規参加者は通常経路で使用しません。学習確認は直前テストで誤答した問題の保存snapshotを再利用します。旧問題・旧学習YAMLは履歴復元用に保持します。共有の現行用語辞書は`backend/app/seed/content/learning_glossary_v4.yml`に置きます。ログ・CSV/XLSX・6仮説は異なるモード間で合算しません。選択肢配置はデバッグ配置またはランダム配置で、ランダム配置では「わからない」を最後のJに固定します。保存済みの回答・学習問題snapshotは書き換えず、採点は表示ラベルではなく選択肢ID・内部メタデータに基づきます。[4用語版の詳細](docs/51_four_topic_foundation_mode.md)。

教材生成・正答要約・誤答解説では、両群に共通用語・構成要素・RAG・`interaction_history`を渡します。履歴は同じ参加者・用語の全フェーズの採点済み回答で、問題・選択・全体正誤・時刻だけを含み、診断ラベルやAI解説は含めません。実験群だけに診断・対象主張・taxonomy・教授方針を追加します。確認問題は両群とも同じ診断連動規則を使いますが、統制群のLLMには診断・段階を渡しません。教授方略はbackendで固定し、実験群の教授契約と教材内transfer_checkを維持します。

## 実装で守る前提

両群の教材章立てはAIが決め、冒頭の##用語名と非空###節を維持します。実験群の教授内容・適用確認は節本文中の証拠で検査します。契約版はtutoring-teaching-contract-v7、taxonomy版はm1-m3-unknown-v3。証拠を自動補正せず、最大3試行後も不合格なら停止します。DB変更はnullable列追加に限定します。仕様版44は既存の問題モード・ログ列を再利用して第3モードを追加し、仕様版45では既定モードの変更と固定2回フローを別protocolとして導入しました。仕様版46では両条件を統合します。CSV/XLSXの従来列と過去値を維持します。

この自動検証は、契約内の対象ID・方略・必須フィールド・本文証拠の一致・章立て・禁止文字列を確認するものです。教材本文の文字数は目標値に対する参考情報として記録し、合否判定には使いません。教材の事実的正しさ、反駁の妥当性、言い換えによる正答漏えい、意味的な過去解説の混入まで保証するものではありません。プロンプト上の指示と自動検査を区別し、教材内容は研究者が目視確認します。詳細は [AI契約の検証範囲](docs/10_ai_prompt_contracts.md#出力検証) を参照してください。

- OpenAI APIキーは使わない
- OpenAI SDKで通常APIを直接呼ばない
- AI呼び出しは `AIBackend` 抽象インターフェース経由にする
- 通常実行では `CodexAppServerBackend` を使い、ユーザーのChatGPT/CodexログインでAIを呼び出す
- `MockAIBackend` は自動テスト・CI・app-server切り分け専用に残す
- ChatGPT/Codex認証情報をDBへ保存しない
- 被験者画面に内部分類・群名・教授方略を直接表示しない
- 回答、出題時刻、回答時刻、回答時間、backendの固定採点・分類、AI教材・解説、学習ステージ更新を研究ログとして保存する
- 管理画面とCSVでは、テスト回答と学習ターン回答を `answer_history` として同じ回答履歴に統合する
- 回答ログの `attempts.test_round` に `test`、`retest_1`、`retest_2` の周回名を保存し、内部処理用の `phase` と区別する
- 実験分析に必要なCSVを出力できるようにする
- 全用語の問題variantを事前後の採点済み回次で選び、final_test後や未回答用語でも同じ問題を再出題しない。学習後回数retest_cycles_completedと、final_test込みのpost_pretest_tests_completedを区別する。

**管理画面・管理APIには共通パスワード認証があります。** パスワードと操作方法は冒頭を参照してください。実際の配布環境で匿名アクセス拒否を確認し、取得済みログ・CSVは研究者が別途管理してください。詳細は [セキュリティ仕様](docs/15_security_privacy.md) を参照してください。

## 推奨構成

- frontend: Next.js + TypeScript
- backend: FastAPI + Python
- db: PostgreSQL
- ai-adapter: Codex app-server JSON-RPC client
- analysis: CSV export + pandas互換出力
- dev runtime: Docker / Docker Compose

## 仕様書一覧

| File | 内容 |
|---|---|
| `docs/00_project_summary.md` | 研究とシステムの全体像 |
| `docs/01_research_requirements.md` | 研究課題、仮説、実験条件 |
| `docs/02_experiment_flow.md` | 被験者フローと状態遷移 |
| `docs/03_misconception_taxonomy.md` | 現行M1/M3/unknown分類 |
| `docs/04_scaffolding_and_tutoring.md` | 固定教授方略、教材必須要素、教材内適用確認 |
| `docs/05_system_architecture.md` | システム構成とモジュール境界 |
| `docs/06_codex_app_server_integration.md` | Codex app-server連携方針 |
| `docs/07_data_model.md` | DBテーブル、enum、保存ルール |
| `docs/08_backend_api_spec.md` | REST API仕様 |
| `docs/09_frontend_ux_flow.md` | 画面遷移、UI要件、禁止表示 |
| `docs/10_ai_prompt_contracts.md` | AI入出力スキーマとプロンプト契約 |
| `docs/11_seed_questions.md` | 問題バンク、選択肢判定、variantと参加者ごとの版管理 |
| `docs/12_evaluation_metrics.md` | 評価指標、CSV、分析仕様 |
| `docs/13_docker_development.md` | Docker開発環境 |
| `docs/14_testing_acceptance.md` | テスト・受け入れ条件 |
| `docs/15_security_privacy.md` | セキュリティと個人情報方針 |
| `docs/16_implementation_tasks.md` | 実装タスク分解 |
| `docs/17_traceability_matrix.md` | 研究計画から仕様への対応表 |
| `docs/18_implementation_blueprint.md` | 将来実装時のディレクトリ・サービス設計 |
| `docs/19_experiment_operation_runbook.md` | 実験運用手順 |
| `docs/20_experiment_plan_alignment.md` | 計画書の出典・対応・未対応・要確認事項 |
| `docs/21_assessment_action_questions.md` | 新9問の本文・選択肢・誤答分類根拠と研究上の限界 |
| `docs/99_sources_and_notes.md` | 計画書の参考文献、理論と設計判断、旧資料の扱い |

## 起動方法

### WSL + Docker Desktop（このリポジトリのoverride使用時）

`docker-compose.override.yml` はfrontend/backend/dbをComposeネットワークに接続する。frontendは `backend:8000`、backendはPostgreSQLの `db:5432` を使う。既存PostgreSQL volumeを保持し、SQLiteからの自動移行はしない。

WSLのCodex CLIが古いと `gpt-5.6-luna` が「newer version of Codex」で失敗する。CLIを更新してから、ターミナル1で次を実行し、開いたままにする。

```bash
codex update
./scripts/start-codex-app-server.sh --docker
```

ターミナル2:

```bash
docker compose up --build
```

`--docker` は `.local/codex-app-server/server.sock` を作り、backendへsocketだけをread-only mountする。接続先は `unix:///codex-app-server.sock`。4500番の公開・ホストIP指定・認証ファイルのコンテナコピーは不要。app-serverを再起動した場合は、socketの再マウントのため `docker compose up -d --force-recreate backend` も実行する。`http://localhost:3000/admin` のAI状態で接続とログインを確認する。

### Docker Compose

先にホストOSでCodex app-serverを起動します。接続先はルート`.env`で設定します。

```bash
cp .env.example .env
./scripts/start-codex-app-server.sh
```

Windows PowerShellでは次を実行します。

```powershell
Copy-Item .env.example .env
.\scripts\start-codex-app-server.ps1
```

その後、アプリを起動します。

```bash
docker compose up --build
```

- frontend: http://localhost:3000
- backend health: http://localhost:8000/api/health
- admin: http://localhost:3000/admin

DockerではPostgreSQLを使用します。現行Composeの既定は`BACKEND_NETWORK_MODE=host`で、backendは`CODEX_APP_SERVER_URL=ws://127.0.0.1:4500`のapp-serverへ接続します。bridge構成へ変更する場合だけ、接続先を通常`ws://host.docker.internal:4500`へ上書きし、DB接続先やネットワーク設定も合わせて調整します。`rag_agent_knowledge_base/` はread-onlyでbackendへマウントされ、初期seedはYAMLを検証したうえでbackend起動時に自動投入されます。

### ローカル開発

```bash
cp .env.example .env
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

別ターミナル:

```bash
cd frontend
npm install
npm run dev
```

ローカル開発の既定DBはSQLiteです。研究本番に近い確認はDocker Composeで行ってください。

## テスト

```bash
cd backend && pytest
cd frontend && npm test
cd frontend && npm run build
```

GitHub ActionsのBackend testsは、収集したテストをファイル単位で5つの独立したジョブへ分割し、全ジョブを実行します。各ジョブのログには所要時間上位20件が表示され、集約チェック`Backend tests`は全ジョブが成功した場合にのみ成功します。ジョブごとにテストDBは分離されます。同一環境内で複数のpytestを並列実行するとテストDBが競合するため、ローカルでは上記の全件実行を使ってください。

## AIバックエンド

通常実行の既定は `AI_BACKEND=codex_app_server` です。OpenAI APIキーは使わず、ホスト側のCodex app-serverが保持するChatGPT/Codexログインを使います。管理画面のCodex Fast modeは初期OFFで、対応モデル・アカウントに応じて次回呼び出しから有効になります。使用量が増え、速度向上幅はモデルにより異なります。backend再起動でOFFに戻ります。

```bash
./scripts/start-codex-app-server.sh
```

以下は現行Docker Composeと.env.exampleの既定値です。low以外の管理上書きは警告・監査されます。実験前に配布設定と両群の実送信を確認してください。

```env
AI_BACKEND=codex_app_server
BACKEND_NETWORK_MODE=host
CODEX_APP_SERVER_URL=ws://127.0.0.1:4500
CODEX_APP_SERVER_LISTEN_URL=ws://127.0.0.1:4500
CODEX_APP_SERVER_CWD=/tmp
CODEX_MODEL=gpt-6-luna
CODEX_REASONING_EFFORT=low
RAG_BASE_DIR=/rag_agent_knowledge_base
```

bridge構成を選ぶ場合のapp-server接続例は`CODEX_APP_SERVER_URL=ws://host.docker.internal:4500`です。このURLだけを既定のhost network構成へ混ぜず、backendからのホスト名解決・4500番への到達、DB接続先・ポート公開も確認してください。詳しくは [Docker開発仕様](docs/13_docker_development.md) を参照してください。

ローカルでbackendを直接起動する場合は、backendが動くホストから到達できるURLへ`CODEX_APP_SERVER_URL`を変更します。通常は`ws://127.0.0.1:4500`です。`MockAIBackend` は `AI_BACKEND=mock` を明示したテスト用途に限ります。app-serverが未起動または未ログインの場合、AI呼び出しはMockへ自動フォールバックせず、`ai_call_logs` に失敗として記録されます。

## トラブルシューティング

- frontendからbackendへ接続できない場合は、`.env`の`FRONTEND_INTERNAL_API_BASE_URL`を確認します。Docker Desktopでは通常`http://host.docker.internal:8000`です。
- `/api/admin/ai/status` が未接続なら、`.env`の`CODEX_APP_SERVER_URL`と`CODEX_APP_SERVER_LISTEN_URL`を確認し、`scripts/start-codex-app-server.sh`または`.ps1`でapp-serverを起動します。WindowsでDockerからホストへ到達できない場合は、`CODEX_APP_SERVER_LISTEN_URL`を環境に合わせて変更し、ファイアウォールで4500番ポートを許可してください。
- AI呼び出しが `usageLimitExceeded` で503になる場合は、ChatGPT/Codexアカウントの利用枠が回復してから再実行します。通常実行ではMockへ自動切替しません。

## 管理画面ログとCSV

管理画面では、ログを全体ログと被験者別ログに分けて確認できます。

```text
GET /api/admin/logs/overview
GET /api/admin/logs/overview.csv
GET /api/admin/logs/overview.xlsx
GET /api/admin/participants/{participant_id}/logs
GET /api/admin/participants/{participant_id}/logs.csv
GET /api/admin/participants/{participant_id}/logs.xlsx
GET /api/admin/export/hypothesis_metrics.csv
GET /api/admin/export/hypothesis_metrics.xlsx
GET /api/admin/export/hypothesis_group_summary.csv
GET /api/admin/export/hypothesis_group_summary.xlsx
```

CSVは `record_type, source_type, participant_id, display_code, phase, test_round, term_slug, event_time, question_shown_at, answered_at, response_time_sec, question_body, selected_option_body, question_body_snapshot, option_order_snapshot, summary, value_json` の形式で、回答履歴・学習状態・学習セッション・AIログなどを1ファイルにまとめます。回答単位の行は `record_type=answer`、`source_type=test_attempt` または `source_type=learning_turn` です。出力先は `exports/` です。

現行サマリーはpretest_score、retest_score、attainment_correct_rate、同種誤答/M1/M3別再発率を保存します。これらを新6仮説の確定した評価値と同一視しません。到達率の物理保存先だけ旧列を維持し、計算はis_correctを使います。周回名とfinal_score_sourceで測定経路を区別します。旧試用は保存値の閲覧/CSVだけとし、再計算や現行群集計には混ぜません。[評価指標と未確定条件](docs/12_evaluation_metrics.md) を参照してください。
