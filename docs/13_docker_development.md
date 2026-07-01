# 13. Docker Development

## Target Environment

- MacBook Air M4
- Apple Silicon / ARM64
- Docker Desktop for Mac
- Docker Compose V2

## 推奨サービス構成

```yaml
services:
  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      NEXT_PUBLIC_API_BASE_URL: http://localhost:8000
    depends_on:
      backend:
        condition: service_healthy

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+psycopg://app:app@db:5432/ai_tutor
      AI_BACKEND: codex_app_server
      CODEX_APP_SERVER_URL: ws://host.docker.internal:4500
      CODEX_WS_TOKEN_FILE: /run/secrets/codex_ws_token
      CODEX_APP_SERVER_CWD: /tmp
      CODEX_TURN_TIMEOUT_SEC: "120"
      CODEX_REASONING_EFFORT: low
      MAX_LEARNING_TARGETS: "5"
      MAX_TURNS_PER_TERM: "3"
      RANDOM_SEED: "20260525"
    volumes:
      - ./exports:/app/exports
      - ./rag_ready_教材:/rag_ready_教材:ro
      - ./experiment_content:/app/experiment_content:ro
      - ./.local/codex-ws-token:/run/secrets/codex_ws_token:ro
    depends_on:
      db:
        condition: service_healthy

  db:
    image: postgres:16
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
      POSTGRES_DB: ai_tutor
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

通常実行の初期値は `AI_BACKEND=codex_app_server` にする。Mockは `AI_BACKEND=mock` を明示したテスト・切り分け用途に限定する。

## Codex app-server

### 推奨: ホスト起動

```bash
# 1. Codex CLI install
curl -fsSL https://chatgpt.com/codex/install.sh | sh

# 2. login
codex

# 3. 認証付きapp-server listener起動
./scripts/start_codex_app_server.sh
```

### Capability tokenを使う場合

```bash
mkdir -p .local
openssl rand -hex 32 > .local/codex-ws-token

codex app-server \
  --listen ws://127.0.0.1:4500 \
  --ws-auth capability-token \
  --ws-token-file "$(pwd)/.local/codex-ws-token"
```

backendからは `host.docker.internal:4500` へ接続する。

## .env.example

```env
APP_ENV=development
DATABASE_URL=postgresql+psycopg://app:app@db:5432/ai_tutor
AI_BACKEND=codex_app_server
CODEX_APP_SERVER_URL=ws://host.docker.internal:4500
CODEX_WS_TOKEN_FILE=/run/secrets/codex_ws_token
CODEX_MODEL=
CODEX_APP_SERVER_CWD=/tmp
CODEX_TURN_TIMEOUT_SEC=120
CODEX_REASONING_EFFORT=low
MAX_LEARNING_TARGETS=5
MAX_TURNS_PER_TERM=3
RANDOM_SEED=20260525
EXPORT_DIR=/app/exports
```

## Makefile

以下のターゲットを用意する。

```makefile
dev:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	docker compose exec backend alembic upgrade head

seed:
	docker compose exec backend python -m app.seed.seed_questions

test:
	docker compose exec backend pytest
	docker compose exec frontend npm test

export:
	docker compose exec backend python -m app.exports.export_all
```

## 開発起動順

1. ホストで `./scripts/start_codex_app_server.sh` を実行する
2. `docker compose up --build`
3. backend起動ログで `experiment_content_v1` の検証・同期成功を確認する
4. `http://localhost:3000/admin` でAI statusがログイン済みか確認する
5. `http://localhost:3000` を開く
6. `http://localhost:8000/api/health` を確認

## app-server接続確認

1. ホストで `./scripts/start_codex_app_server.sh`
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
