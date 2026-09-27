.PHONY: sync run test test-integration lint compose-up compose-down migrate \
	kind-up kind-down build load create-secret create-db-secret \
	deploy-db migrate-k8s deploy-app deploy status logs port-forward

sync:
	uv sync

# Host-run dev server on 8001 — deliberately NOT 8000, so a
# `make port-forward` tunnel to the in-cluster pod can stay up on 8000
# at the same time without the two fighting over the port.
run:
	uv run uvicorn luna.main:app --reload --port 8001

test:
	uv run pytest

# Requires a real Postgres — `make compose-up` first. Separate from
# `make test` (which stays zero-external-services) on purpose.
test-integration:
	uv run pytest tests/integration

lint:
	uv run ruff check src tests
	uv run mypy src

# Local dev Postgres (docker-compose.dev.yml) — the FAST inner loop's
# backing service. NOT the deploy target; see k8s/base/ for that.
compose-up:
	docker compose -f docker-compose.dev.yml up -d

compose-down:
	docker compose -f docker-compose.dev.yml down

# Applies migrations against whatever DATABASE_URL is active — .env's
# value for host dev. For the cluster, see migrate-k8s below, which runs
# this same command inside a K8s Job against the cluster's DATABASE_URL.
migrate:
	uv run alembic upgrade head

kind-up:
	kind create cluster --name luna

kind-down:
	kind delete cluster --name luna

build:
	docker build -t luna:dev .

load: build
	kind load docker-image luna:dev --name luna

# Creates/updates the luna-secrets K8s Secret with ONLY the actually-secret
# values (GROQ_API_KEY) from the local, gitignored .env file. Deliberately
# not a committed YAML manifest with a real value in it — that's how
# secrets end up permanently in git history. Non-secret config (LUNA_ENV,
# LUNA_LOG_LEVEL, LUNA_ROUTING_CONFIDENCE_THRESHOLD) lives in the committed
# k8s/base/configmap.yaml instead — Secrets and ConfigMaps are for
# different things, not just "env vars in two files." The dry-run|apply
# pattern makes this idempotent: safe to rerun after rotating a key in .env.
create-secret:
	kubectl create namespace luna --dry-run=client -o yaml | kubectl apply -f -
	@grep '^GROQ_API_KEY=' .env | kubectl create secret generic luna-secrets -n luna \
		--from-env-file=/dev/stdin \
		--dry-run=client -o yaml | kubectl apply -f -

# Same idea, for the DB credentials — but the two keys can't just be
# grepped verbatim out of .env like GROQ_API_KEY: the in-cluster
# DATABASE_URL needs the Service hostname "postgres", not "localhost".
# Built into a temp file (never a bare CLI arg, never printed) rather
# than a committed manifest with a real password in it.
create-db-secret:
	kubectl create namespace luna --dry-run=client -o yaml | kubectl apply -f -
	@umask 077 && \
		pw=$$(grep '^LUNA_DB_PASSWORD=' .env | cut -d= -f2-) && \
		printf 'POSTGRES_PASSWORD=%s\nDATABASE_URL=postgresql+asyncpg://luna:%s@postgres:5432/luna\n' "$$pw" "$$pw" > /tmp/luna-db-secret.env && \
		kubectl create secret generic luna-db-credentials -n luna \
			--from-env-file=/tmp/luna-db-secret.env \
			--dry-run=client -o yaml | kubectl apply -f - && \
		rm -f /tmp/luna-db-secret.env

# Postgres StatefulSet+PVC+Service, brought up and waited on BEFORE
# anything tries to migrate or connect to it. Ordering matters here —
# see migrate-k8s and deploy below.
deploy-db: create-db-secret
	kubectl create namespace luna --dry-run=client -o yaml | kubectl apply -f -
	kubectl apply -f k8s/base/postgres-statefulset.yaml
	kubectl apply -f k8s/base/postgres-service.yaml
	kubectl rollout status statefulset/postgres -n luna --timeout=120s

# The Alembic migration as a real K8s Job — run to completion BEFORE the
# app Deployment rolls out new code that expects the new schema. Each
# run creates a fresh Job (old one deleted first: Jobs are immutable
# once created, so re-applying the same name errors without this).
migrate-k8s:
	kubectl delete job luna-migrate -n luna --ignore-not-found
	kubectl apply -f k8s/jobs/migrate.yaml
	kubectl wait --for=condition=complete job/luna-migrate -n luna --timeout=120s

deploy-app: load create-secret
	kubectl apply -k k8s/base
	# `kind load` refreshes the image content, but the Deployment's spec
	# text (image: luna:dev) hasn't changed — so `kubectl apply` alone
	# sees no diff and won't restart the pod, silently leaving the OLD
	# image running. A static dev tag always needs an explicit rollout
	# restart to actually pick up the freshly loaded image.
	kubectl rollout restart deployment/luna-app -n luna
	kubectl rollout status deployment/luna-app -n luna --timeout=60s

# The full sequence, in the order that actually matters: DB up and ready,
# THEN migrate, THEN the app (which now finds the schema it expects).
deploy: deploy-db migrate-k8s deploy-app

status:
	kubectl get pods -n luna -o wide

logs:
	kubectl logs -n luna -l app=luna --tail=100 -f

port-forward:
	kubectl port-forward -n luna svc/luna-app 8000:8000
