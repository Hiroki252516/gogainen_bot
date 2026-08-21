# 06. Codex App Server Integration

## 重要

このシステムでは OpenAI APIキーを使わない。ユーザーの ChatGPT/Codex ログインを使って、Codex app-server経由でAI機能を呼び出す。

ただし、Codex app-serverは通常の汎用LLM APIではなく、Codex rich client向けのJSON-RPCプロトコルである。そのため、AI呼び出し部分は `AIBackend` として隔離し、将来の仕様変更に対応できるようにする。

## ローカルCLI確認メモ

2026-05-28時点でローカルの `codex-cli 0.131.0` と `codex app-server generate-json-schema --experimental` では以下が確認できた。

- `--listen <URL>` は `stdio://`, `unix://`, `ws://IP:PORT`, `off` を受け付ける
- `--ws-auth` は `capability-token` と `signed-bearer-token` を受け付ける
- `--ws-token-file` でcapability tokenファイルを指定できる
- `generate-json-schema --out <DIR>` でプロトコルJSON Schemaを生成できる
- v2 schemaには `thread/start`, `turn/start`, `account/read`, `account/login/start`, `account/login/cancel` が含まれる
- `turn/start` は `outputSchema` を受け付ける
- `item/agentMessage/delta`, `item/completed`, `turn/completed` で最終JSONを取得できる
- `account/read` でChatGPTログイン済みアカウントとplanTypeを確認できる

app-serverは実験用LLM APIではなくCodex rich client向けプロトコルなので、将来更新時は `codex app-server generate-json-schema --experimental --out <tmpdir>` を再実行し、その時点のschemaに合わせる。

## 認証方針

### 推奨: host Codexログイン

1. MacホストにCodex CLIをインストールする
2. `codex` または `codex login` で ChatGPT にログインする
3. ホスト上で `codex app-server --listen ws://127.0.0.1:4500` を起動する
4. Docker Desktop for Mac上のbackendから `ws://host.docker.internal:4500` に接続する

### セキュリティ

- app-serverを `0.0.0.0` で公開しない
- localhostまたはDocker内部からのみ接続する
- 可能なら `--ws-auth capability-token --ws-token-file /path/to/token` を使う
- ChatGPTトークンをアプリDBに保存しない
- `~/.codex/auth.json` をアプリから読み書きしない

## app-server起動例

### 開発用・ローカルのみ

```bash
codex app-server --listen ws://127.0.0.1:4500
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

## JSON-RPC初期化

接続直後、必ず `initialize` を送る。以後、schemaに従って通知・レスポンスを処理する。

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

実装時にschemaが `initialized` 通知を要求する場合は送る。要求がない場合は送らない。app-server部分は固定実装ではなく、schema駆動で小さく保つ。

## アカウント状態確認

```json
{
  "method": "account/read",
  "id": 2,
  "params": { "refreshToken": false }
}
```

未ログインの場合、フロントエンドに「Codexログインが必要」と表示する。

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

診断・教授・採点で用途を分ける。

- diagnosis thread
- tutoring thread
- grading thread
- feedback thread

スレッドを用途ごとに使い回すか、毎回ephemeralにするかは実装時に選ぶ。MVPでは再現性とログ単純化のため、用途ごとにephemeral threadを作る方針でよい。

## thread/start 例

```json
{
  "method": "thread/start",
  "id": 10,
  "params": {
    "model": "gpt-5.6-luna",
    "cwd": "/tmp",
    "approvalPolicy": "never",
    "sandbox": "read-only",
    "baseInstructions": "You are a structured-output educational diagnosis assistant.",
    "ephemeral": true
  }
}
```

モデルは設定値 `CODEX_MODEL` から渡し、現行実験設定は `gpt-5.6-luna` とする。

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
        "text": "以下の回答を診断し、指定JSONスキーマだけを返してください..."
      }
    ],
    "approvalPolicy": "never",
    "sandboxPolicy": { "type": "readOnly", "networkAccess": false },
    "effort": "medium",
    "outputSchema": {
      "type": "object",
      "properties": {
        "is_correct": { "type": "boolean" },
        "misconception_type": { "type": ["string", "null"] },
        "diagnosis_confidence": { "type": "number" },
        "evidence": { "type": "string" }
      },
      "required": ["is_correct", "misconception_type", "diagnosis_confidence", "evidence"],
      "additionalProperties": false
    }
  }
}
```

`outputSchema` が使えない、または不安定な場合は、プロンプトでJSONのみ返すようにし、backendでJSON抽出・検証・再試行する。

現行実験設定の推論レベルは `medium` とする。app-server側のschemaが変わった場合は、その時点のschemaに合わせてpayloadを検証する。

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
8. JSONオブジェクトとして抽出し、app-serverの `outputSchema` 制約に合う出力だけを受け付ける
9. `ai_call_logs` にrequest/response/errorを保存
10. `DiagnosisResult` などの内部型へ変換

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
| schema_validation_failed | AI出力を検証できませんでした | 再試行後、保留 |
| turn_failed | AI応答生成に失敗しました | ai_call_logsに保存 |
| timeout | AI応答がタイムアウトしました | 再試行または保留 |

## 実装しないこと

- OpenAI APIキー入力画面
- ChatGPTアクセストークンのDB保存
- `~/.codex/auth.json` の読み書き
- app-serverをインターネットへ公開する機能
- app-serverの仕様を研究ロジックへ直接埋め込むこと
