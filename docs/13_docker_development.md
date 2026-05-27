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
      - backend

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+psycopg://app:app@db:5432/ai_tutor
      AI_BACKEND: mock
      CODEX_APP_SERVER_URL: ws://host.docker.internal:4500
      CODEX_WS_TOKEN_FILE: /run/secrets/codex_ws_token
      MAX_LEARNING_TARGETS: "4"
      MAX_TURNS_PER_TERM: "3"
      RANDOM_SEED: "20260525"
    volumes:
      - ./exports:/app/exports
      - ./.local/codex-ws-token:/run/secrets/codex_ws_token:ro
    depends_on:
      - db

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

MVPの初期値は `AI_BACKEND=mock` にする。Codex app-server接続確認後に `codex_app_server` へ切り替える。

## Codex app-server

### 推奨: ホスト起動

```bash
# 1. Codex CLI install
curl -fsSL https://chatgpt.com/codex/install.sh | sh

# 2. login
codex

# 3. app-server起動
codex app-server --listen ws://127.0.0.1:4500
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
AI_BACKEND=mock
CODEX_APP_SERVER_URL=ws://host.docker.internal:4500
CODEX_WS_TOKEN_FILE=/run/secrets/codex_ws_token
CODEX_MODEL=
MAX_LEARNING_TARGETS=4
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

1. `docker compose up --build`
2. `docker compose exec backend alembic upgrade head`
3. `docker compose exec backend python -m app.seed.seed_questions`
4. `http://localhost:3000` を開く
5. `http://localhost:8000/api/health` を確認

## app-server接続確認

1. ホストで `codex app-server --listen ws://127.0.0.1:4500`
2. `.env` の `AI_BACKEND=codex_app_server`
3. backend再起動
4. `/admin` のAI statusで接続確認

## 注意

- Apple Silicon対応のため、古いx86専用イメージを使わない
- Node/Pythonとも公式multi-arch imageを使う
- app-serverをコンテナ内で動かすのは後回しでよい
- まずはMockAIBackendで研究フローを完成させる
- Docker内にChatGPT認証情報をコピーしない
- `.local/` と `exports/` はgitignore対象にする
