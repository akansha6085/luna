# Luna

A personal learning project: a scaled-down, production-disciplined clone of
an internal AI agent-orchestration platform (multi-agent routing, streaming
chat, session history, LLM cost governance). Built to learn backend/system
design concepts hands-on, and to get real Kubernetes reps — deployed to a
local `kind` cluster rather than a cloud provider, so the whole thing costs
$0 to build and run.

Not affiliated with, and not built at, any employer — a personal project
inspired by exposure to real internal tooling of this shape.

## Stack

- Python 3.12 + FastAPI (async), `uv` for deps/venv
- Groq for LLM chat completions, local `sentence-transformers` for embeddings
- Postgres (session/cost data) + Qdrant (vector search), both in-cluster
- Deployed to a local Kubernetes cluster (`kind`) via plain manifests +
  Kustomize; observability via community Helm charts (kube-prometheus-stack,
  loki-stack)

## Status

Phase 0 — scaffolding + first Kubernetes deploy. See
`/Users/akumari/.claude/plans/cosmic-scribbling-mochi.md` for the full
phased build plan.

## Local development

```bash
uv sync                 # install deps into .venv
make run                 # uv run uvicorn --reload, for fast local iteration
make test                # uv run pytest
```

## Deploy to local Kubernetes

```bash
make kind-up              # create the kind cluster (once)
make deploy                # build image, load into kind, kubectl apply -k k8s/base
make status                # kubectl get pods -n luna
make port-forward          # expose the in-cluster service on localhost:8000
```
