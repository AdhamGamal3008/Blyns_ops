# Build/run targets (docs/ENVIRONMENTS.md §5)
.PHONY: dev seed demo test test-fast lint build-prod

dev:            ## docker mongo + backend reload + frontend dev
	docker compose up -d mongo
	cd backend && uvicorn app.main:app --reload --port 8000 &
	cd frontend && npm run dev

seed:           ## seed control plane (first super admin + admin roles) — Phase 3
	cd backend && python ../scripts/seed_control_plane.py

demo:           ## provision the "acme" demo tenant end-to-end — Phase 2/4
	cd backend && python ../scripts/provision_demo_tenant.py

test:           ## full test suite (docs/TESTING.md)
	cd backend && python -m pytest
	@if [ -f frontend/package.json ]; then cd frontend && npm test; fi

test-fast:      ## unit + integration, no e2e
	cd backend && python -m pytest -m "not e2e"

lint:           ## ruff + mypy (+ eslint once frontend lands)
	cd backend && python -m ruff check app tests && python -m mypy app
	@if [ -f frontend/package.json ]; then cd frontend && npm run lint; fi

build-prod:     ## frontend build + backend image
	@if [ -f frontend/package.json ]; then cd frontend && npm run build; fi
	cd backend && docker build -t erp-backend:$(shell cd backend && python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])") -t erp-backend:latest .
