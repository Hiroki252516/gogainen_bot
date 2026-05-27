# 06. Codex App Server Integration

## 重要

このシステムでは OpenAI APIキーを使わない。ユーザーの ChatGPT/Codex ログインを使って、Codex app-server経由でAI機能を呼び出す。

ただし、Codex app-serverは通常の汎用LLM APIではなく、Codex rich client向けのJSON-RPCプロトコルである。そのため、AI呼び出し部分は `AIBackend` として隔離し、将来の仕様変更に対応できるようにする。

## 公式仕様メモ

Codex app-serverはJSON-RPC風のプロトコルを使う。主なトランスポートは以下。

- stdio JSONL
- WebSocket
- Unix socket

MVPでは、実装しやすさのためWebSocket接続を優先する。ただしWebSocket transportはExperimental/Unsupported扱いなので、接続層は差し替え可能にする。

## 認証方針

### 推奨: host Codexログイン

1. MacホストにCodex CLIをインストールする
2. `codex` または `codex login` で ChatGPT にログインする
3. ホスト上で `codex app-server --listen ws://127.0.0.1:4500` を起動する
4. backendコンテナから `ws://host.docker.internal:4500` に接続する

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

backendコンテナには同じtokenファイルをread-only mountする。

## JSON-RPC初期化

接続直後、必ず `initialize` を送る。その後 `initialized` 通知を送る。

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
    "capabilities": {
      "experimentalApi": false
    }
  }
}
```

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

## AI呼び出しの作り方

Codex app-serverの `thread/start` と `turn/start` を使い、毎回「構造化JSONを返すタスク」としてAIに依頼する。

診断・教授・採点でスレッドを分ける。

- diagnosis thread
- tutoring thread
- grading thread

## thread/start 例

```json
{
  "method": "thread/start",
  "id": 10,
  "params": {
    "model": "gpt-5.4",
    "cwd": "/workspace",
    "approvalPolicy": "never",
    "sandbox": "readOnly",
    "personality": "precise",
    "serviceName": "learning_log_ai_tutor"
  }
}
```

モデル名はCodex環境に依存するため、設定ファイルで指定可能にする。

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
    "outputSchema": {
      "type": "object",
      "properties": {
        "is_correct": { "type": "boolean" },
        "misconception_type": { "type": ["string", "null"] },
        "confidence": { "type": "number" },
        "reason": { "type": "string" }
      },
      "required": ["is_correct", "misconception_type", "confidence", "reason"],
      "additionalProperties": false
    }
  }
}
```

`outputSchema` が使えない、または不安定な場合は、プロンプトでJSONのみ返すようにし、backendでJSON抽出・検証・再試行する。

## 失敗時の扱い

AI呼び出しに失敗した場合、実験を止めずに以下のいずれかを行う。

1. MockAIBackendに切り替える
2. 管理者確認待ちにする
3. 「AI診断保留」として保存する
