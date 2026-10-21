# 13. Docker Development

## 計画書の目標と環境例

現行既定モデル/推論設定はgpt-5.6-luna / low。実施前に配布設定・管理上書き・実送信を確認する。[D04](20_experiment_plan_alignment.md#現行実装との差分)を参照する。今回の検証は隔離SQLiteとローカル実行であり、配布先PostgreSQL/Dockerの確認とは区別する。

## Target Environment

- MacBook Air M4
- Apple Silicon / ARM64
- Docker Desktop for Mac
- Docker Compose V2

## 現行Docker Compose構成

### WSL向けoverride（2026-10-21）

以下の基本構成とは別に、このリポジトリの `docker-compose.override.yml` は `network_mode: !reset null` でbackendのhost network設定を除去し、3サービスをdefaultネットワークへ接続する（タグ対応のComposeを使用する）。frontendから `http://backend:8000`、backendから `db:5432` を使い、既存PostgreSQL volumeを継続使用する。DB種別の切替や過去データの移行は自動実行しない。

AI接続はWSL上のUnix socketをread-only mountする。先に `./scripts/start-codex-app-server.sh --docker`、別ターミナルで `docker compose up --build` を実行する。socketが存在しないときはディレクトリを自動作成せず起動を拒否する。app-server再起動後は `docker compose up -d --force-recreate backend` でsocketを再マウントする。`/api/admin/ai/status` のHTTP 200だけで接続成功とはせず、本文の `app_server_reachable` / `logged_in` を確認する。CLI更新を要求するモデルエラーには `codex update` を実行し、モデルを無断変更しない。

### 基本構成（overrideなし）

```yaml
services:
  frontend:
    build:
      context: ./frontend
      args:
        INTERNAL_API_BASE_URL: ${FRONTEND_INTERNAL_API_BASE_URL}
    ports:
      - "${FRONTEND_PORT}:3000"
    environment:
      NEXT_PUBLIC_API_BASE_URL: ${NEXT_PUBLIC_API_BASE_URL}
      INTERNAL_API_BASE_URL: ${FRONTEND_INTERNAL_API_BASE_URL}
    extra_hosts:
      - "host.docker.internal:host-gateway"
    depends_on:
      - backend

  backend:
    build: ./backend
    network_mode: ${BACKEND_NETWORK_MODE}
    environment:
      APP_ENV: ${APP_ENV}
      DATABASE_URL: ${DATABASE_URL}
      AI_BACKEND: ${AI_BACKEND}
      CODEX_APP_SERVER_URL: ${CODEX_APP_SERVER_URL}
      CODEX_WS_TOKEN_FILE: ${CODEX_WS_TOKEN_FILE}
      CODEX_APP_SERVER_CWD: ${CODEX_APP_SERVER_CWD}
      CODEX_TURN_TIMEOUT_SEC: ${CODEX_TURN_TIMEOUT_SEC}
      CODEX_MODEL: ${CODEX_MODEL}
      CODEX_REASONING_EFFORT: ${CODEX_REASONING_EFFORT}
      RAG_BASE_DIR: ${RAG_BASE_DIR}
      MAX_LEARNING_TARGETS: ${MAX_LEARNING_TARGETS}
      MAX_TURNS_PER_TERM: ${MAX_TURNS_PER_TERM}
      EXPORT_DIR: ${EXPORT_DIR}
      FRONTEND_ORIGIN: ${FRONTEND_ORIGIN}
    volumes:
      - ./exports:/app/exports
      - ./rag_agent_knowledge_base:/rag_agent_knowledge_base:ro
      - ./rag_ready_教材:/rag_ready_教材:ro
    depends_on:
      - db

  db:
    image: postgres:16
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    ports:
      - "${POSTGRES_PORT}:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

`.env.example`の初期値は`BACKEND_NETWORK_MODE=host`、`DATABASE_URL=postgresql+psycopg://app:app@127.0.0.1:5432/ai_tutor`、`CODEX_APP_SERVER_URL=ws://127.0.0.1:4500`、`FRONTEND_PORT=3000`、`POSTGRES_PORT=5432`である。host networkではbackendがホストの127.0.0.1上のPostgreSQLとapp-serverへ接続する。bridgeネットワークへ変更する場合は、backendからホストへ接続する設定（通常`host.docker.internal`）とDB接続先を合わせて上書きする。通常実行のAI初期値は `AI_BACKEND=codex_app_server` で、Mockは `AI_BACKEND=mock` を明示したテスト・切り分け用途に限定する。

AI教材生成はapp-serverの応答に数十秒かかる場合があるため、frontendのNext.js rewrite proxyには`experimental.proxyTimeout=300000`（5分）を設定している。Next.jsのproxy既定値30秒のままでは、backendで教材生成と保存が成功していても、画面側だけが`socket hang up`になる。

通常のRAG参照先は`RAG_BASE_DIR=/rag_agent_knowledge_base`である。ここに`chunks.jsonl`がない場合だけ、retrieverは互換用のlegacyディレクトリ`rag_ready_教材`へフォールバックする。Composeでは両方をread-only mountする。

## Codex app-server

### 推奨: ホスト起動

```bash
# 1. Codex CLI install
curl -fsSL https://chatgpt.com/codex/install.sh | sh

# 2. login
codex

# 3. app-server起動
./scripts/start-codex-app-server.sh
```

Windows PowerShellでは`.\scripts\start-codex-app-server.ps1`を使う。

### Capability tokenを使う場合

```bash
mkdir -p .local
openssl rand -hex 32 > .local/codex-ws-token

codex app-server \
  --listen ws://127.0.0.1:4500 \
  --ws-auth capability-token \
  --ws-token-file "$(pwd)/.local/codex-ws-token"
```

backendからCodex app-serverへの接続先はルート`.env`の`CODEX_APP_SERVER_URL`で設定する。現行Composeの既定はhost networkのため`ws://127.0.0.1:4500`を使う。bridgeネットワークへ変更する場合は`ws://host.docker.internal:4500`へ上書きする。ホスト側の待受先は`CODEX_APP_SERVER_LISTEN_URL`で設定し、起動スクリプトが読み込む。

## .env.example

```env
APP_ENV=development
BACKEND_NETWORK_MODE=host
DATABASE_URL=postgresql+psycopg://app:app@127.0.0.1:5432/ai_tutor
AI_BACKEND=codex_app_server
CODEX_APP_SERVER_URL=ws://127.0.0.1:4500
CODEX_APP_SERVER_LISTEN_URL=ws://127.0.0.1:4500
CODEX_WS_TOKEN_FILE=
CODEX_MODEL=gpt-5.6-luna
CODEX_APP_SERVER_CWD=/tmp
CODEX_TURN_TIMEOUT_SEC=120
CODEX_REASONING_EFFORT=low
RAG_BASE_DIR=/rag_agent_knowledge_base
FRONTEND_INTERNAL_API_BASE_URL=http://host.docker.internal:8000
NEXT_PUBLIC_API_BASE_URL=
MAX_LEARNING_TARGETS=3
MAX_TURNS_PER_TERM=3
EXPORT_DIR=/app/exports
FRONTEND_ORIGIN=http://localhost:3000
FRONTEND_PORT=3000
POSTGRES_USER=app
POSTGRES_PASSWORD=app
POSTGRES_DB=ai_tutor
POSTGRES_PORT=5432
```

`CODEX_WS_TOKEN_FILE` は認証方式を明示的に有効化する場合だけ設定する任意項目であり、通常のローカル構成では空欄のままにする。
標準Composeにはtokenファイルのvolume mountがないため、Dockerでtoken認証を使う場合はCompose overrideで同じファイルをbackendへread-only mountするか、backendをローカル直接起動する。

## Makefile

現行Makefileに存在するターゲットは次のとおりである。

```makefile
dev:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

seed:
	docker compose exec backend python -m app.seed.seed_questions

test:
	docker compose exec backend pytest
	docker compose exec frontend npm test

frontend-build:
	cd frontend && npm run build

backend-dev:
	cd backend && uvicorn app.main:app --reload --port 8000

frontend-dev:
	cd frontend && npm run dev
```

`migrate` や `export` のMakefileターゲット、Alembicによる起動時マイグレーションは現行実装にない。DB初期化とseedはbackend起動時に行われ、CSVは管理APIから出力する。

## 開発起動順

1. ホストで `codex app-server --listen ws://127.0.0.1:4500` を起動する
2. `docker compose up --build`
3. `http://localhost:3000/admin` でAI statusがログイン済みか確認する（backend APIは `/api/admin/ai/status`）
4. `http://localhost:3000` を開く
5. `http://localhost:8000/api/health` を確認

## app-server接続確認

1. ホストで `codex app-server --listen ws://127.0.0.1:4500`
2. `.env` またはcomposeで `AI_BACKEND=codex_app_server`
3. backend再起動
4. `/admin` のAI statusで接続確認

## 注意

- Apple Silicon対応のため、古いx86専用イメージを使わない
- Node/Pythonとも公式multi-arch imageを使う
- app-serverをコンテナ内で動かすのは後回しでよい
- MockAIBackendは通常実験データへ混ぜない
- Docker内にChatGPT認証情報をコピーしない
- `.local/` と `exports/` はgitignore対象にする
