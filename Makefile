.PHONY: setup dev backend frontend validate-curriculum generate-llm-schemas demo-tutor-engine demo-llm-mock smoke-llm-live test test-backend test-frontend lint build

setup:
	uv sync --extra dev
	npm install --prefix frontend

dev:
	./scripts/dev.sh

backend:
	.venv/bin/python -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	npm --prefix frontend run dev

validate-curriculum:
	.venv/bin/python -m backend.app.curriculum.cli

generate-llm-schemas:
	.venv/bin/python -m backend.app.llm.schema_cli

demo-tutor-engine:
	.venv/bin/python -m backend.app.tutor.demo

demo-llm-mock:
	.venv/bin/python -m backend.app.llm.demo

smoke-llm-live:
	.venv/bin/python -m backend.app.llm.live_smoke

test: test-backend test-frontend

test-backend:
	.venv/bin/pytest

test-frontend:
	npm --prefix frontend test

lint:
	.venv/bin/ruff check backend
	.venv/bin/ruff format --check backend
	npm --prefix frontend run lint

build:
	npm --prefix frontend run build
