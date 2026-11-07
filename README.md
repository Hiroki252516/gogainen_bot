# 学習ログ駆動型AIチューター

2026-11-07現行条件：新規参加者は仕様版40 / `experiment-plan-2026-11-07-learning-material-target-800-v1`で登録します。事前アンケートv2、RAGを含む共通辞書v4、通常版テストsplit-actions-v5を維持します。教材モードは「教材内解説」に固定し、本文は800文字程度を目安にします。上下限による合否判定や長さを理由にした再生成は行いません。仕様版39以下と旧protocolは閲覧専用で、既存参加者のモード・回答・教材snapshot・監査記録は変更しません。[教材モード](docs/41_learning_glossary_material_mode.md)、[文字数目標](docs/42_learning_glossary_material_length.md)、[事前アンケート](docs/49_presurvey_baseline.md)、[辞書と履歴](docs/24_learning_glossary.md)、[受入記録](docs/14_testing_acceptance.md)を参照してください。

2026-11-03追加：管理画面の「設問1のみ出題」で、各用語1問（計3問）と設問1・2（計6問、初期値）を切り替えられます。新規参加者の登録時に固定し、既存参加者には反映しません。仕様版35で導入し、現行仕様版40でも維持する条件分岐は[docs/48](docs/48_first_question_only.md)を参照してください。以下の過去版の説明は採用時の記録です。

仕様版33 / `experiment-plan-2026-11-01-pretest-content-revision-v2`の採用時は、通常版PRETESTの指定選択肢本文を`split-actions-v3`へ更新しました。v1（仕様版27〜31）とv2（仕様版32）、旧データ・回答snapshotを履歴として保持し、当時は仕様版32以下を閲覧専用としました。RETEST1/2・内部final_test、設問数・採点、設問ペア答え合わせは維持しました。誤答PRETEST設問の学習確認では回答時の保存snapshotを再利用します。教材用語解説は登録時に固定し、本文の文字数条件とv3辞書による言い換え指示を追加しました。[仕様版27の採用記録](docs/39_split_assessment.md)、[仕様版28の答え合わせ](docs/40_question_pair_answer_review.md)、[仕様版29の用語解説モード](docs/41_learning_glossary_material_mode.md)、[仕様版30の文字数条件](docs/42_learning_glossary_material_length.md)、[仕様版31の辞書定義と言い換え](docs/43_glossary_definition_paraphrase.md)、[仕様版32のPRETEST改訂](docs/44_pretest_content_revision.md)、[仕様版33のPRETEST選択肢文面改訂](docs/45_pretest_memory_distractors.md)を参照してください。各変更の受入検証状況は[docs/14](docs/14_testing_acceptance.md)を参照してください。実験開始の承認や実AIでの確認とは区別します。

## 用語の補足をテストにも表示（仕様版26）

指定の9用語を注釈から除外し、残る16語を教材・回答後解説に加えて事前テスト・再テストにも表示します。テストは問題文・全選択肢の登場語を表示し、現行通常版の両群で共通です。内部final_testも対象です。

仕様版31当時の新規参加者に適用しました。v2は仕様版26当時の辞書履歴として無変更で残し、v3では指定4語の定義を更新しました。教材内解説モードでは定義を意味参照として使い、教材の文脈に合わせて言い換えます。現行辞書v4のRAG追加と履歴は[対象語・保存・移行と注意事項](docs/24_learning_glossary.md)を参照してください。

## 管理画面のパスワード

`/admin` を開くと、パスワード入力のポップアップが表示されます。パスワードは **`abc`** です。

管理API・CSV・対応表・seed・管理用の評価再計算も認証が必要です。認証は30分で失効し、「管理画面をロック」とbackend再起動でも解除されます。画面を離れる際にもログアウトを要求し、再入場・再読み込みでは再入力を求めます。ロック時に通信が失敗した場合は画面を隠したまま、認証解除の再試行を求めます。パスワードはブラウザのコードやlocalStorageへ保存せず、backendの `ADMIN_PASSWORD` で変更できます。変更後はbackendを再起動してください。セッションはbackendの単一プロセス内で管理します。

これは指定された共通パスワードによるローカル実験用の保護です。READMEを読める人にもパスワードが分かるため、研究者だけが扱う環境で使用します。同意内容の確定・実AI確認等の本実験開始条件は別途確認してください

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

通常版の事前テスト6選択肢と対応する訂正情報を改訂し、テストバンクをscenario-actions-v2へ更新しました。旧v1はアーカイブと旧DBレコードで保全し、新規参加者だけに適用します。全テスト・学習確認で選択肢の数値的な文長検査を撤廃しました。当時は教材600〜800文字条件を維持しましたが、現行の教材文字数は仕様版40の目標値のみです。[問題全文と分類根拠](docs/21_assessment_action_questions.md)、[版管理](docs/20_experiment_plan_alignment.md)、[現行の文字数目標](docs/42_learning_glossary_material_length.md)を参照してください。

## 用語の補足

教材・事前テスト・再テストの注釈は、広い画面では右側の追従欄に、狭い画面では開閉パネルに表示します。回答後解説の注釈は解説の下に表示します。確認問題自体・結果確認画面は対象外です。未登録語・除外語には注釈が付きません。現行の教材内解説モードでは辞書を意味参照として教材生成入力へ渡し、本文800文字程度を目安に生成します。文字数の上下限による合否判定や長さを理由にした再生成は行いません。過去のモード別文字数契約は履歴として保持します。[辞書全文・保存と運用](docs/24_learning_glossary.md)、[文字数目標と履歴](docs/42_learning_glossary_material_length.md)を参照してください。

仕様版39では新規参加者の教材モードを教材内解説に固定し、管理画面の切替UIとモード管理APIを削除しました。仕様版40では本文の文字数を800文字程度の目安だけにし、上下限による検証と長さを理由にした再生成を廃止しました。教材右側の注釈欄を隠し、回答後解説・テストの注釈と保存snapshotは維持します。辞書定義は意味の参照として文脈に合わせて言い換えます。仕様版39以下の保存条件は履歴として識別します。定義の意味的な正確さや理解向上は自動検査で実証されません。[仕様・条件差](docs/41_learning_glossary_material_mode.md)、[文字数条件](docs/42_learning_glossary_material_length.md)、[辞書言い換え](docs/43_glossary_definition_paraphrase.md)。

2026-10-21追加: 同意画面に提示された同意書と必須の学籍番号入力を追加しました。学籍番号は研究DB・AI入力・研究ログへ含めず、分離した対応表に保存します。管理画面下部で対応表CSVをダウンロードし、USBへの保存を確認してから個別/全件削除できます。対応表だけを削除しても研究データは残ります。撤回時の参加者削除は、研究DBの削除と対応表の削除待ちを先に確定し、対応表を別処理で削除します。削除待ちが残った場合は起動時または同じ削除操作の再試行で回復します。既出力CSV・USB・バックアップ等は研究者が別途処理してください。

責任者・保存場所・保管期間は保留のため動作確認用表示です。管理画面・管理APIには冒頭の共通パスワード認証を適用します。本実験開始前の課題は[対応表](docs/20_experiment_plan_alignment.md)と[運用手順](docs/19_experiment_operation_runbook.md)を参照してください。

Wordと承認された実装計画に沿い、教材・low設定・新アンケート・6仮説の記述集計を実装しています。[採用判断と残課題](docs/20_experiment_plan_alignment.md)と[評価定義](docs/12_evaluation_metrics.md)を先に確認してください。

現行の新規参加者には仕様版40 / `experiment-plan-2026-11-07-learning-material-target-800-v1`を保存します。仕様版39以下、NULL、旧protocol_idの参加者は閲覧・CSV出力専用で、進行・削除・補修・再計算・現行集計をしません。既存の版・回数・注釈・教材解説モードを補完しません。Participantの教材モードとRuntimeSettingの旧設定列はnullableのまま保持し、既存行を変更しません。

このリポジトリは、卒業研究で使う「誤概念タイプと学習ステージに基づく AI・情報系専門用語の概念理解支援システム」の仕様と実装を含みます。

`docs/` 以下に研究・設計仕様、`backend/` にFastAPIアプリ、`frontend/` にNext.jsアプリがあります。現行MVPの対象用語は、`llm_knowledge`、`multi_agent`、`memory_process` の3項目です。

## 研究の要点

### 現行の問題

新規参加者は通常版だけで登録され、問題版・集計版の切替はありません。現行の出題・集計は通常版に固定し、選択肢配置は新規参加者の設定として独立しています。

研究の比較対象は「AIを使うかどうか」ではありません。両群とも同じ種類の学習履歴を参照する通常AIを使い、実験群だけにbackendの明示的な診断・修正対象・誤概念の定義・タイプ別教授方針を追加した効果を比較します。統制群が生の回答履歴から自然に誤りを訂正することは許容し、「誤概念対応全般の有無」の比較とは位置づけません。

目標の研究仮説は、計画書の仮説一覧に合わせて次の6つです。分析表に残る古い番号は使わず、未指定の集計条件は独自に決めません。

1. 実験群は、統制群よりも、テスト間の正答率の伸びが大きい。
2. 実験群は統制群よりも、再テストで満点に到達するまでの学習セッション回数が少ない。
3. 実験群は統制群よりも、学習セッションで扱う一用語当たりの周回数が少ない。
4. 実験群は統制群よりも、同じ誤答タイプを再び選ぶ割合が低い。
5. 教材を閲覧した参加者において、実験群は統制群よりも、学習後アンケートの教材の評価が高い。
6. 実験群は統制群よりも、再テストで満点に到達した参加者の割合が高い。

大学生40名・各群20名、原則無作為割付が研究目標です。Word計画書のモデル記載はgpt-5.6-luna / lowですが、今回承認されたアプリ側の運用基準はgpt-6-luna / lowです。管理画面でGPT-6.1 Sol / GPT-6 Lunaを切り替えられ、変更はbackend稼働中の次回AI呼び出しから両群・進行中の参加者に適用されます。再起動後は環境設定へ戻り、実験途中に切り替えると同一参加者内でモデルが混在し得ます。実験前に設定を固定し、実送信監査を確認してください。目標のunknownと共通説明は意味や仕組みの説明、統制群の指示は共通情報からの通常説明です。事後アンケートは用語の事前知識6項目（知っていた／知らない）、一般4/教材6の1〜10段階、任意の自由記述を扱います。自由記述以外の表示項目はすべて必須です。

**今回の対応:** 共通/統制群指示、unknownの定義・仕組み・適用確認、low既定値、用語の事前知識6項目・一般4/教材6の10段階・任意自由記述、教材表示ログ、6仮説の管理表示・専用CSVを追加しました。旧値は変換せず版付きJSONへ保存します。自動割付・各群20名上限・正答位置の復旧は対象外です。管理認証は冒頭の2026-10-27追加分を参照してください。AIモデルは既定gpt-6-lunaで、管理画面のモデル/推論レベル設定はDBへ保存しない一時的なbackend内設定です。

これは研究上の評価目的である。現行実装では`final_test`はpretestで学習対象がない参加者に限られ、学習対象のある参加者は再テスト満点後に省略される。したがって、現行データには全員共通の最終テスト正答率はなく、測定経路を記録・区別して解釈する。

現行フローは事前テスト後のテストを最大2回、事前を含め最大3回に制限します。通常経路は「事前→学習→再テスト1→未達なら学習→再テスト2」、事前満点経路は「事前→学習前の追加テスト（内部final_test・表示は再テスト1）→未達なら学習→再テスト2」です。満点なら早期終了し、2回目で未達でも未達のまま結果を確認してアンケートへ進みます。未回答を含む採点バッチも1回、全問未回答の採点は拒否します。

問題YAMLは`backend/app/seed/content/standard/`（現行問題）と`archive/`（旧問題）に分けています。現行テストは`standard/learning_content.yml`を使います。現行の学習確認問題は別YAMLから作らず、確認1を同用語の`pretest_v1`、確認2を`retest_v1`から組み立てます（到達しない確認3は互換上`retest_v2`）。旧学習YAMLは履歴復元用に保持します。共有の現行用語辞書は`backend/app/seed/content/learning_glossary_v4.yml`に置き、v1〜v3は履歴用に変更せず保持します。v4でRAG（検索拡張生成）を注釈対象へ追加しました。現行テスト固有問題は9問（pretest 3＋retest 6）で、内部`final_test`は`retest_v1`を使用します。確認問題も各用語で正解/M1/M3/unknownを3/3/3/1持ちます。新規経路では3セッション目は到達しません。同じ学習セッションでは1用語につき1回答し、誤答後は解説を表示して次へ進みます。管理画面の選択肢配置を「デバッグ配置」または「ランダム配置」に切り替えられます。初期値はデバッグ配置で、配置切替は新規参加者から適用します。実験データ収集前にランダム配置を選んでください。2026-10-21の変更により、ランダム配置では「わからない」を最後のJに固定し、残る9択だけをA〜Iへ配置します。問題ごとに全員共通・再起動後も固定され、正解/M1/M3のラベル数を問題バンク全体で均衡させます。保存済みの回答・学習問題snapshotは書き換えません。採点は表示ラベルではなく選択肢ID・内部メタデータに基づきます。

教材生成・正答要約・誤答解説では、両群に共通用語・構成要素・RAG・`interaction_history`を渡します。履歴は同じ参加者・用語の全フェーズの採点済み回答で、問題・選択・全体正誤・時刻だけを含み、診断ラベルやAI解説は含めません。実験群だけに診断・対象主張・taxonomy・教授方針を追加します。確認問題は両群とも同じ診断連動規則を使いますが、統制群のLLMには診断・段階を渡しません。教授方略はbackendで固定し、実験群の教授契約と教材内transfer_checkを維持します。

## 実装で守る前提

両群の教材章立てはAIが決め、冒頭の##用語名と非空###節を維持します。実験群の教授内容・適用確認は節本文中の証拠で検査します。契約版はtutoring-teaching-contract-v7、taxonomy版はm1-m3-unknown-v3。証拠を自動補正せず、最大3試行後も不合格なら停止します。DB変更はnullable列追加に限定し、旧値と統合CSV固定ヘッダを維持します。

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

通常実行の既定は `AI_BACKEND=codex_app_server` です。OpenAI APIキーは使わず、ホスト側のCodex app-serverが保持するChatGPT/Codexログインを使います。

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
GET /api/admin/participants/{participant_id}/logs
GET /api/admin/participants/{participant_id}/logs.csv
```

CSVは `record_type, source_type, participant_id, display_code, phase, test_round, term_slug, event_time, question_shown_at, answered_at, response_time_sec, question_body, selected_option_body, question_body_snapshot, option_order_snapshot, summary, value_json` の形式で、回答履歴・学習状態・学習セッション・AIログなどを1ファイルにまとめます。回答単位の行は `record_type=answer`、`source_type=test_attempt` または `source_type=learning_turn` です。出力先は `exports/` です。

現行サマリーはpretest_score、retest_score、attainment_correct_rate、同種誤答/M1/M3別再発率を保存します。これらを新6仮説の確定した評価値と同一視しません。到達率の物理保存先だけ旧列を維持し、計算はis_correctを使います。周回名とfinal_score_sourceで測定経路を区別します。旧試用は保存値の閲覧/CSVだけとし、再計算や現行群集計には混ぜません。[評価指標と未確定条件](docs/12_evaluation_metrics.md) を参照してください。
