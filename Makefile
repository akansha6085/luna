.PHONY: sync run test lint kind-up kind-down build load deploy status logs port-forward

sync:
	uv sync

run:
	uv run uvicorn luna.main:app --reload --port 8000

test:
	uv run pytest

lint:
	uv run ruff check src tests
	uv run mypy src

kind-up:
	kind create cluster --name luna

kind-down:
	kind delete cluster --name luna

build:
	docker build -t luna:dev .

load: build
	kind load docker-image luna:dev --name luna

deploy: load
	kubectl apply -k k8s/base

status:
	kubectl get pods -n luna -o wide

logs:
	kubectl logs -n luna -l app=luna --tail=100 -f

port-forward:
	kubectl port-forward -n luna svc/luna-app 8000:8000
