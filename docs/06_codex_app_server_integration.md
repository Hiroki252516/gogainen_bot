# 06. Codex App Server Integration

## 目標設定と現行設定

アプリ側標準条件は両群共通のgpt-6-luna / low。Word計画書原本にあるgpt-5.6-luna / lowの記載は別の目標記録であり、原本は変更していない。管理画面でgpt-6.1-sol / gpt-6-lunaと推論レベルlow/medium/highを一時切替できる。モデル・推論レベルは一呼び出しの開始時に一緒に確定し、その呼び出しのthread/start、turn/start、監査ログに同一値を使う。切替は両群・進行中参加者にも次回呼び出しから適用し、backend再起動後は環境値へ戻る。収集中の切替は同一参加者内のモデル混在を生み得るため、実験前に設定を固定する。実送信model/effortを監査し、過去の検証記録は書き換えない。[対応表](20_experiment_plan_alignment.md)を参照する。

仕様版28の設問ペア答え合わせは、保存済みAttemptの選択内容・正誤を表示するもので、AI生成タスクやapp-server呼び出しを追加しない。[詳細](40_question_pair_answer_review.md)。

利用可能性は設定候補への掲載だけでは保証されない。モデルがアカウントで利用できない場合、app-serverのエラーをそのまま失敗として扱い、別モデルやMockへ自動変更しない。接続中アカウントでの実際の生成成功を実験開始前に確認する。

## 重要

このシステムでは OpenAI APIキーを使わない。ユーザーの ChatGPT/Codex ログインを使って、Codex app-server経由でAI機能を呼び出す。

ただし、Codex app-serverは通常の汎用LLM APIではなく、Codex rich client向けのJSON-RPCプロトコルである。そのため、AI呼び出し部分は `AIBackend` として隔離し、将来の仕様変更に対応できるようにする。

## ローカルCLI確認メモ

2026-05-28時点でローカルの `codex-cli 0.131.0` と `codex app-server generate-json-schema --experimental` では以下が確認できた。

- `--listen <URL>` は `stdio://`, `unix://`, `ws://IP:PORT`, `off` を受け付ける
- `--ws-auth` は `capability-token` と `signed-bearer-token` を受け付ける
- `--ws-token-file` でcapability tokenファイルを指定できる
- `generate-json-schema --out <DIR>` でプロトコルJSON Schemaを生成できる
- v2 schemaには `thread/start`, `turn/start`, `account/read`, `account/login/start`, `account/login/cancel`, `account/logout` が含まれる
- `turn/start` は `outputSchema` を受け付ける
- `item/agentMessage/delta`, `item/completed`, `turn/completed` で最終JSONを取得できる
- `account/read` でChatGPTログイン済みアカウントとplanTypeを確認できる

app-serverは実験用LLM APIではなくCodex rich client向けプロトコルなので、将来更新時は `codex app-server generate-json-schema --experimental --out <tmpdir>` を再実行し、その時点のschemaに合わせる。

## 認証方針

### 推奨: host Codexログイン

1. ホストOSにCodex CLIをインストールする
2. `codex` または `codex login` で ChatGPT にログインする
3. ルート`.env`の`CODEX_APP_SERVER_LISTEN_URL`を設定し、`scripts/start-codex-app-server.sh`または`.ps1`で起動する
4. backendからルート`.env`の`CODEX_APP_SERVER_URL`へ接続する。現行Composeの既定はhost networkと`ws://127.0.0.1:4500`である。bridgeネットワークを選ぶ場合は`ws://host.docker.internal:4500`へ上書きする

### セキュリティ

- app-serverを `0.0.0.0` で公開しない
- localhostまたはDocker内部からのみ接続する
- 可能なら `--ws-auth capability-token --ws-token-file /path/to/token` を使う
- ChatGPTトークンをアプリDBに保存しない
- `~/.codex/auth.json` をアプリから読み書きしない

## app-server起動例

### 開発用・ローカルのみ

```bash
./scripts/start-codex-app-server.sh
```

Windows PowerShell:

```powershell
.\scripts\start-codex-app-server.ps1
```

### capability tokenを使う場合

```bash
mkdir -p .local
openssl rand -hex 32 > .local/codex-ws-token
codex app-server \
  --listen ws://127.0.0.1:4500 \
  --ws-auth capability-token \
  --ws-token-file "$(pwd)/.local/codex-ws-token"
```

capability tokenを使う場合は、backendコンテナに同じtokenファイルをread-only mountする。
現行の標準Composeにはtokenファイルのmount定義がないため、Dockerでこの方式を使う場合はCompose overrideでread-only mountを追加するか、backendをローカル直接起動する。`CODEX_WS_TOKEN_FILE`だけを`.env`へ設定しても、標準Composeがホスト上のファイルを自動的に共有するわけではない。

## JSON-RPC初期化

接続直後、必ず `initialize` を送る。以後、schemaに従って通知・レスポンスを処理する。

Codex app-serverの[公式Protocol仕様](https://learn.chatgpt.com/docs/app-server#protocol)では、wire上のメッセージから汎用JSON-RPCの `jsonrpc` ヘッダーを省略する。`initialized` 通知は `method` / `params` のみとし、`id` を付けない。PR #145のレビューで追加を求められたが、このCodex固有の契約に従い現行通知を維持する。

```json
{
  "method": "initialize",
  "id": 1,
  "params": {
    "clientInfo": {
      "name": "learning_log_ai_tutor",
      "title": "Learning Log AI Tutor",
      "version": "0.1.0"
    },
    "capabilities": {}
  }
}
```

現行clientは `initialize` の応答後に `initialized` 通知を送り、それから `account/read` 等を実行する。app-server部分はschema駆動で小さく保つ。

### WSL + Docker Desktopの接続

2026-10-21の起動障害修正では、WSL CLIを0.140.0から0.163.0へ更新した。失敗ログの直接原因は `gpt-5.6-luna` が新しいCodexを要求したこと。モデル・推論設定は変更しない。将来の互換性は実際のCLIと実応答で確認する。

WSL向けoverrideは `scripts/start-codex-app-server.sh --docker` のUnix socketをbackendへread-only mountし、`CODEX_APP_SERVER_URL=unix:///codex-app-server.sock` で接続する。`AIBackend` と既存WebSocket接続を維持し、Unix接続だけ `websockets.unix_connect` を使用する。socket用ディレクトリは700、ChatGPT認証ファイルはホストに保持する。socketの実体をmountするため、app-server再起動後はbackendもforce-recreateする。起動コマンドは[README](../README.md#wsl--docker-desktopこのリポジトリのoverride使用時)。

## アカウント状態確認

```json
{
  "method": "account/read",
  "id": 2,
  "params": { "refreshToken": false }
}
```

未ログインの場合、管理画面のAI statusに未ログイン状態を表示し、ChatGPTログインまたはデバイスコードの導線を表示する。

## ChatGPTログイン

ブラウザフローまたはデバイスコードフローをサポートする。

### Browser flow

```json
{
  "method": "account/login/start",
  "id": 3,
  "params": { "type": "chatgpt" }
}
```

返却される `authUrl` をユーザーに開かせる。

### Device code flow

```json
{
  "method": "account/login/start",
  "id": 4,
  "params": { "type": "chatgptDeviceCode" }
}
```

返却される `verificationUrl` と `userCode` をUIに表示する。

### Cancel

```json
{
  "method": "account/login/cancel",
  "id": 5,
  "params": { "loginId": "..." }
}
```

## AI呼び出しの作り方

Codex app-serverの `thread/start` と `turn/start` を使い、毎回「構造化JSONを返すタスク」としてAIに依頼する。

教材生成・正答要約・誤答解説で用途を分ける。

- tutoring thread（教材生成）
- correct-answer summary / distractor explanation thread

構造化呼出しごとにephemeral threadを作り、generate_tutoring_turn、generate_correct_answer_summary、explain_selected_distractorの3purposeをログに残す。

全問固定複数選択で、採点・分類をapp-serverへ依存しない。旧AI診断・自由回答採点・自己説明フィードバック・状態要約の実行経路はない。過去ログは読出しだけにする。

## thread/start 例

```json
{
  "method": "thread/start",
  "id": 10,
  "params": {
    "model": "gpt-6-luna",
    "cwd": "/tmp",
    "approvalPolicy": "never",
    "sandbox": "read-only",
    "baseInstructions": "You are a structured-output tutoring and answer-feedback assistant.",
    "ephemeral": true
  }
}
```

モデルは起動時の `CODEX_MODEL` を基準とし、管理画面での一時上書きを含む有効値をthread/startとturn/startへ渡す。管理選択肢は `gpt-6.1-sol` と `gpt-6-luna`、アプリ標準値は `gpt-6-luna` である。未指定の環境既定もこれに合わせるが、明示された環境変数は優先する。

`cwd` は既定で `/tmp` にする。アプリが研究仕様リポジトリ配下の `AGENTS.md` をAIタスクへ混入させないためである。

## turn/start 例

```json
{
  "method": "turn/start",
  "id": 11,
  "params": {
    "threadId": "thr_xxx",
    "input": [
      {
        "type": "text",
        "text": "目的: tutoring_turn。共通用語・RAG・interaction_historyから教材を生成し、teaching_strategyをgeneral_explanationに固定してください..."
      }
    ],
    "approvalPolicy": "never",
    "sandboxPolicy": { "type": "readOnly", "networkAccess": false },
    "effort": "low",
    "outputSchema": {
      "type": "object",
      "properties": {
        "tutor_message": { "type": "string" },
        "teaching_strategy": { "type": "string", "enum": ["general_explanation"] }
      },
      "required": ["tutor_message", "teaching_strategy"],
      "additionalProperties": false
    }
  }
}
```

`outputSchema` とプロンプトでJSON契約をapp-serverへ指定し、backendは最終応答からJSONオブジェクトを抽出する。現行backendはローカルで完全なJSON Schema/型検証を行わず、app-server側の`outputSchema`と各呼び出し後のキー参照に依存する。JSONオブジェクトとして解析できない場合はエラーとして扱い、自動再試行は行わない。

現行コードと環境例の推論既定値はlow。app-serverのschemaが変わった場合は、その時点のschemaへoutputSchemaとpayloadを合わせる。実送信監査でmodel/effortとprotocol_idを確認する。

## ストリーミング処理

app-serverからは `turn/started`, `item/started`, `item/agentMessage/delta`, `item/completed`, `turn/completed`, `error` などの通知が来る可能性がある。実装では通知を処理しつつ、AIBackendの戻り値は最終JSONだけに正規化する。

MVPではフロントエンドにAI生成途中のストリームを見せなくてよい。バックエンド内部で完了まで待つ。

## AIBackendの戻り値正規化

`CodexAppServerBackend` は以下を行う。

1. JSON-RPC接続
2. initialize
3. account/read
4. thread/start
5. turn/start
6. turn completedまで通知を読む
7. 最終assistant messageからJSON抽出
8. 最終応答からJSONオブジェクトを抽出する（構造化契約の主な制約はapp-serverへ渡した `outputSchema` に委ねる）
9. `ai_call_logs` にrequest/response/errorを保存
10. 用途ごとのJSON辞書を呼び出し側へ返す

各Codex呼び出しでは、`AICallLog.request_payload.effective_request`に送信直前の実際の`thread/start`設定、`turn/start`の全文prompt・JSON Schema・モデル・推論レベルを保存する。両値とアプリ標準比較基準・一致判定も記録する。併せてprompt/taxonomy版、Schema SHA-256、RAG query・section・chunk ID・本文SHA-256、教材生成試行番号、送信状態を記録する。認証ヘッダー・tokenは保存しない。接続や送信前の失敗では、送信試行と実送信の状態を区別する。Mockの入力にはこのCodex実送信監査を付けない。

仕様版26でも共通interaction_historyの版・件数・SHA-256、共通出題規則版とactual_ai_inputを記録する。モデルへは共通履歴の診断除外投影を送り、proposedだけに診断・対象主張・教授方針を追加する。input_projectionはサーバー側投影であり、送信済みかどうかはeffective_request.transmissionを確認する。仕様版4で追加した学習後retest回数制限はbackendの遷移制御であり、AI promptの送信内容を変更しない。

章立てはAIが決め、本文構造と実験群の本文証拠をbackendで検査する。unknownのmandatory_elementsをtype/definitionへ変更し、teaching_contractの仕組み・適用確認と合わせる。不一致を補正せず同backendへ再生成させ、章立て・検証を保存する。契約版はtutoring-teaching-contract-v7-easy-level。

app-serverへのoutputSchema指定とbackendの構造・契約・証拠文字列検査は、内容の事実検証とは別である。教材の正しさ、反駁の妥当性、言い換えによる正答漏えい、意味的な過去解説混入まで自動保証しない。[AI契約](10_ai_prompt_contracts.md#出力検証) に自動検査・プロンプト指示・目視確認の境界を記載する。

この監査には学習者の選択・回答・学習履歴が含まれる場合があるため、参加者ログAPI・CSVと同様に研究者限定で扱う。管理APIには2026-10-27追加の共通パスワード認証を適用するが、取得済みファイルの管理と実配布環境での匿名アクセス拒否確認は別途必要。[セキュリティ仕様](15_security_privacy.md)を参照する。DB列およびCSV固定列は追加せず、既存JSON payload内へ記録する。

## 失敗時の扱い

AI呼び出しに失敗した場合、通常実行ではMockへ自動フォールバックしない。

1. `AI_BACKEND=codex_app_server` で失敗した場合は `ai_call_logs.status = failed` とする
2. APIは503と日本語エラーを返す
3. 管理画面にapp-server接続状態とログイン状態を表示する
4. `AI_BACKEND=mock` はテスト・切り分け用途として明示指定した場合だけ使う

実験データにMock由来のAI判断が混入しないよう、`codex_app_server` モードでは `fallback_provider=mock` を作らない。

## エラー分類

| error_code | UI表示 | 処理 |
|---|---|---|
| app_server_unreachable | Codex app-serverに接続できません | 起動手順を表示 |
| not_logged_in | Codexへのログインが必要です | login startを案内 |
| auth_failed | app-server認証に失敗しました | token確認を案内 |
| schema_validation_failed | AI出力をJSONとして解析できませんでした | ai_call_logsに保存し、APIエラーとして扱う |
| turn_failed | AI応答生成に失敗しました | ai_call_logsに保存 |
| timeout | AI応答がタイムアウトしました | ai_call_logsに保存し、APIエラーとして扱う |

## 実装しないこと

- OpenAI APIキー入力画面
- ChatGPTアクセストークンのDB保存
- `~/.codex/auth.json` の読み書き
- app-serverをインターネットへ公開する機能
- app-serverの仕様を研究ロジックへ直接埋め込むこと
