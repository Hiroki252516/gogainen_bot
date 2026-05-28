dev:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

seed:
	docker compose exec backend python -m app.seed.seed_questions

test:
	cd backend && pytest
	cd frontend && npm test

frontend-build:
	cd frontend && npm run build

backend-dev:
	cd backend && uvicorn app.main:app --reload --port 8000

frontend-dev:
	cd frontend && npm run dev
