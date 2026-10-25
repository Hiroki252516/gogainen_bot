# 学習ログ駆動型AIチューター

## 通常版の確認問題更新（仕様版12）

通常版LLM知識の最初の確認問題を、指定された大学の履修案内AIの問題へ更新しました。学習バンクv5を新規参加者へ適用し、旧v3は原文のまま履歴参照用に保持します。残り8確認問題・易しい版v4・テスト問題・AIプロンプトは変更しません。仕様版11以下は閲覧専用です。[問題全文と分類根拠](docs/25_learning_confirmation_revision.md)、[版管理](docs/20_experiment_plan_alignment.md)を参照してください。

## 前回のF改善（仕様版11採用時の記録）

通常版の事前テスト問1のFを指定文へ変更しました。M1判定・訂正情報・他の本文は維持します。通常版テストはscenario-actions-v4、protocolはexperiment-plan-2026-10-25-pretest-f-wording-v1です。旧v3をアーカイブと別DB IDで保全し、新規参加者だけに適用します。版10以下は閲覧専用です。

## 前回のA・B改善（仕様版10採用時の記録）

通常版の事前テスト問1のA・Bを、実装する処理が分かる表現へ変更しました。両方とも正解のままで、問題文・他の選択肢・訂正情報は変更しません。通常版テストはscenario-actions-v3、protocolはexperiment-plan-2026-10-25-pretest-wording-v1です。旧v2はアーカイブと別DBレコードで保全し、新規参加者だけに適用します。旧版9以下は閲覧専用で、途中の記録を付け替えません。

## 前回の事前テスト改善（仕様版9採用時の記録）

通常版の事前テスト6選択肢と対応する訂正情報を改訂し、テストバンクをscenario-actions-v2へ更新しました。旧v1はアーカイブと旧DBレコードで保全し、新規参加者だけに適用します。通常版・易しい版の全テスト・学習確認で選択肢の数値的な文長検査を撤廃しました。空欄・重複・役割数の検査と教材600〜800文字条件は維持します。文長が回答の手掛かりとなる可能性は残ります。[問題全文と分類根拠](docs/21_assessment_action_questions.md)、[版管理](docs/20_experiment_plan_alignment.md)を参照してください。

## 用語の補足

教材と回答後のAI解説の下に、登場した専門用語の意味を固定辞書から常時表示します。通常版・易しい版、両群に共通で、問題・選択肢・テストには付けません。本文や600〜800文字の条件、AI指示は変えません。現行の仕様版12では旧版11以下は閲覧専用です。[辞書全文・保存と運用](docs/24_learning_glossary.md)を参照してください。未登録語には注釈が付きません。

2026-10-21追加: 同意画面に提示された同意書と必須の学籍番号入力を追加しました。学籍番号は研究DB・AI入力・研究ログへ含めず、分離した対応表に保存します。管理画面下部で対応表CSVをダウンロードし、USBへの保存を確認してから個別/全件削除できます。対応表だけを削除しても研究データは残ります。撤回時の参加者削除は、研究DBの削除と対応表の削除待ちを先に確定し、対応表を別処理で削除します。削除待ちが残った場合は起動時または同じ削除操作の再試行で回復します。既出力CSV・USB・バックアップ等は研究者が別途処理してください。

責任者・保存場所・保管期間は保留のため動作確認用表示です。管理者認証は今回追加していません。本実験開始前の課題は[対応表](docs/20_experiment_plan_alignment.md)と[運用手順](docs/19_experiment_operation_runbook.md)を参照してください。

Wordと承認された実装計画に沿い、教材・low設定・新アンケート・6仮説の記述集計を実装しています。[採用判断と残課題](docs/20_experiment_plan_alignment.md)と[評価定義](docs/12_evaluation_metrics.md)を先に確認してください。

実験仕様版12では、新規参加者にprotocol_id=experiment-plan-2026-10-25-learning-confirmation-v1と再テスト回数0を保存します。既存版11以下、NULL、旧protocol_idを含む記録は閲覧・CSV出力専用で、進行・削除・補修・再計算・新集計をしません。既存参加者の回数欄は保存値のまま保持し、推定・補完しません。更新前の資料はdocs/historyに保全しています。

このリポジトリは、卒業研究で使う「誤概念タイプと学習ステージに基づく AI・情報系専門用語の概念理解支援システム」の仕様と実装を含みます。

`docs/` 以下に研究・設計仕様、`backend/` にFastAPIアプリ、`frontend/` にNext.jsアプリがあります。現行MVPの対象用語は、`llm_knowledge`、`multi_agent`、`memory_process` の3項目です。

## 研究の要点

### 通常版・易しい版

管理画面の「新規参加者に適用する問題版」で通常版／易しい版を選びます。既定は通常版。開始時に版が固定され、後から設定を変えても進行中の参加者には影響しません。選択肢配置とは独立して4通りを使えます。両版を別バンクで保持し、各版にテスト9固有問・学習確認9問を用意します。通常版の改訂時も旧バンクを保全します。

易しい版では、学校・旅行・メモなど身近な問題と、両群共通の初心者向け教材・解説指示を使います。教材600〜800文字、教授内容・本文証拠、採点・回数制限は同じです。「集計する問題版」は設定とは独立し、群集計・6仮説・専用CSVを版別に表示します。生ログは両版を保持します。問題と説明条件がともに変わるため、版間の成績差を問題難易度だけの効果とは解釈しません。

操作・保存・検証条件は[22](docs/22_question_set_modes.md)、易しい版の問題全文と誤答分類根拠は[23](docs/23_easy_question_bank.md)を参照してください。

研究の比較対象は「AIを使うかどうか」ではありません。両群とも同じ種類の学習履歴を参照する通常AIを使い、実験群だけにbackendの明示的な診断・修正対象・誤概念の定義・タイプ別教授方針を追加した効果を比較します。統制群が生の回答履歴から自然に誤りを訂正することは許容し、「誤概念対応全般の有無」の比較とは位置づけません。

目標の研究仮説は、計画書の仮説一覧に合わせて次の6つです。分析表に残る古い番号は使わず、未指定の集計条件は独自に決めません。

1. 実験群は、統制群よりも、テスト間の正答率の伸びが大きい。
2. 実験群は統制群よりも、再テストで満点に到達するまでの学習セッション回数が少ない。
3. 実験群は統制群よりも、学習セッションで扱う一用語当たりの周回数が少ない。
4. 実験群は統制群よりも、同じ誤答タイプを再び選ぶ割合が低い。
5. 教材を閲覧した参加者において、実験群は統制群よりも、学習後アンケートの教材の評価が高い。
6. 実験群は統制群よりも、再テストで満点に到達した参加者の割合が高い。

大学生40名・各群20名、原則無作為割付が研究目標です。Word計画書のモデル記載はgpt-5.6-luna / lowですが、今回承認されたアプリ側の運用基準はgpt-6-luna / lowです。管理画面でGPT-6.1 Sol / GPT-6 Lunaを切り替えられ、変更はbackend稼働中の次回AI呼び出しから両群・進行中の参加者に適用されます。再起動後は環境設定へ戻り、実験途中に切り替えると同一参加者内でモデルが混在し得ます。実験前に設定を固定し、実送信監査を確認してください。目標のunknownと共通説明は意味や仕組みの説明、統制群の指示は共通情報からの通常説明です。事後アンケートは経験の有無、1〜10段階評価、教材評価6項目、自由記述を扱います。

**今回の対応:** 共通/統制群指示、unknownの定義・仕組み・適用確認、low既定値、経験4有無・一般4/教材6の10段階・必須自由記述、教材表示ログ、6仮説の管理表示・専用CSVを追加しました。旧値は変換せず版付きJSONへ保存します。自動割付・各群20名上限・正答位置の復旧・管理者認証は対象外です。AIモデルは既定gpt-6-lunaで、管理画面のモデル/推論レベル設定はDBへ保存しない一時的なbackend内設定です。

これは研究上の評価目的である。現行実装では`final_test`はpretestで学習対象がない参加者に限られ、学習対象のある参加者は再テスト満点後に省略される。したがって、現行データには全員共通の最終テスト正答率はなく、測定経路を記録・区別して解釈する。

現行フローは事前テスト後のテストを最大2回、事前を含め最大3回に制限します。通常経路は「事前→学習→再テスト1→未達なら学習→再テスト2」、事前満点経路は「事前→学習前の追加テスト（内部final_test・表示は再テスト1）→未達なら学習→再テスト2」です。満点なら早期終了し、2回目で未達でも未達のまま結果を確認してアンケートへ進みます。未回答を含む採点バッチも1回、全問未回答の採点は拒否します。

問題YAMLは`backend/app/seed/content/standard/`（通常版）、`easy/`（易しい版）、`archive/`（旧問題）に分けて管理します。通常版のテストは `standard/learning_content.yml`、学習確認は `standard/learning_questions_v5.yml`、易しい版は `easy/learning_content_easy.yml` と `easy/learning_questions_v4_easy.yml` を使用します。共有の用語辞書は`backend/app/seed/content/learning_glossary_v1.yml`に置きます。activeなテスト固有問題は各版9問（pretest 3＋retest 6）で、内部 `final_test` は `retest_v1` を使用します。学習確認は各版9問（3用語×3学習セッション）で、各問は正解/M1/M3/unknownを3/3/3/1持ちます。新規経路では3セッション目は到達しません。同じ学習セッション内は最大3回答し、誤答時は問題を変えず教材だけ再生成します。管理画面の選択肢配置を「デバッグ配置」または「ランダム配置」に切り替えられます。初期値はデバッグ配置で、モードの切替は新規参加者から適用します。実験データ収集前にランダム配置を選んでください。2026-10-21の変更により、ランダム配置では「わからない」を最後のJに固定し、残る9択だけをA〜Iへ配置します。問題ごとに全員共通・再起動後も固定され、正解/M1/M3のラベル数を問題バンク全体で均衡させます。保存済みの回答・学習問題snapshotは書き換えません。採点は表示ラベルではなく選択肢ID・内部メタデータに基づきます。

教材生成・正答要約・誤答解説では、両群に共通用語・構成要素・RAG・`interaction_history`を渡します。履歴は同じ参加者・用語の全フェーズの採点済み回答で、問題・選択・全体正誤・時刻だけを含み、診断ラベルやAI解説は含めません。実験群だけに診断・対象主張・taxonomy・教授方針を追加します。確認問題は両群とも同じ診断連動規則を使いますが、統制群のLLMには診断・段階を渡しません。教授方略はbackendで固定し、実験群の教授契約と教材内transfer_checkを維持します。

## 実装で守る前提

両群の教材章立てはAIが決め、冒頭の##用語名と非空###節を維持します。実験群の教授内容・適用確認は節本文中の証拠で検査します。契約版はtutoring-teaching-contract-v7-easy-level、taxonomy版はm1-m3-unknown-v3。証拠を自動補正せず、最大3試行後も不合格なら停止します。DB変更はnullable列追加に限定し、旧値と統合CSV固定ヘッダを維持します。

この自動検証は、契約内の対象ID・方略・必須フィールド・本文証拠の一致・章立て・文字数・禁止文字列を確認するものです。教材の事実的正しさ、反駁の妥当性、言い換えによる正答漏えい、意味的な過去解説の混入まで保証するものではありません。プロンプト上の指示と自動検査を区別し、教材内容は研究者が目視確認します。詳細は [AI契約の検証範囲](docs/10_ai_prompt_contracts.md#出力検証) を参照してください。

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

**管理者アクセスは未対策です。** 現行の管理画面・管理APIには管理者認証・権限確認がなく、参加者画面にも管理画面リンクがあります。移動時の確認ダイアログやChatGPT/Codexログインは管理者のアクセス制御ではありません。ログ・CSVを「研究者限定で扱う」は運用方針であり、参加者からのアクセスをシステムが防止する保証ではありません。本実験開始前のアクセス対策は未解決事項です。詳細は [セキュリティ仕様](docs/15_security_privacy.md) を参照してください。

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
