.PHONY: sync run test lint kind-up kind-down build load deploy status logs port-forward create-secret

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
	# `kind load` refreshes the image content, but the Deployment's spec
	# text (image: luna:dev) hasn't changed — so `kubectl apply` alone
	# sees no diff and won't restart the pod, silently leaving the OLD
	# image running. A static dev tag always needs an explicit rollout
	# restart to actually pick up the freshly loaded image.
	kubectl rollout restart deployment/luna-app -n luna
	kubectl rollout status deployment/luna-app -n luna --timeout=60s

# Creates/updates the luna-secrets K8s Secret with ONLY the actually-secret
# values (GROQ_API_KEY) from the local, gitignored .env file. Deliberately
# not a committed YAML manifest with a real value in it — that's how
# secrets end up permanently in git history. Non-secret config (LUNA_ENV,
# LUNA_LOG_LEVEL) lives in the committed k8s/base/configmap.yaml instead —
# Secrets and ConfigMaps are for different things, not just "env vars in
# two files." The dry-run|apply pattern makes this idempotent: safe to
# rerun after rotating a key in .env.
create-secret:
	kubectl create namespace luna --dry-run=client -o yaml | kubectl apply -f -
	@grep '^GROQ_API_KEY=' .env | kubectl create secret generic luna-secrets -n luna \
		--from-env-file=/dev/stdin \
		--dry-run=client -o yaml | kubectl apply -f -

status:
	kubectl get pods -n luna -o wide

logs:
	kubectl logs -n luna -l app=luna --tail=100 -f

port-forward:
	kubectl port-forward -n luna svc/luna-app 8000:8000
