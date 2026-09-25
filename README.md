# Luna

A personal learning project: a scaled-down, production-disciplined clone of
an internal AI agent-orchestration platform — multi-agent routing, streaming
chat (SSE), conversation history, and (in later phases) LLM cost governance
and RAG. Built to learn backend/system design hands-on and to get real
Kubernetes reps.

**Not built at, or affiliated with, any employer** — a personal project
inspired by exposure to real internal tooling of this shape. Everything runs
locally on a laptop via `kind` (Kubernetes-in-Docker): total infra cost $0.

---

## 1. The big picture

```
        YOUR LAPTOP (macOS)
┌────────────────────────────────────────────────────────────────────┐
│                                                                    │
│  Browser (web/index.html)                                          │
│  http://localhost:8000                                             │
│      │  POST /chat (SSE stream over fetch)                         │
│      ▼                                                             │
│  ┌─────────────── kubectl port-forward (tunnel) ───────────────┐   │
│  │  localhost:8000 ──────────────────►  svc/luna-app:8000      │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  kind cluster  ──────────────────  context: kind-luna              │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  namespace: luna                                             │  │
│  │                                                              │  │
│  │  ┌─────────────────────┐         ┌──────────────────────┐    │  │
│  │  │ Pod: luna-app-xxx   │         │ Secret: luna-secrets │    │  │
│  │  │ (Deployment, 1 repl)│◄─env────│  GROQ_API_KEY        │    │  │
│  │  │  FastAPI/uvicorn    │         └──────────────────────┘    │  │
│  │  │  :8000              │         ┌──────────────────────┐    │  │
│  │  │                     │◄─env────│ ConfigMap: luna-config│   │  │
│  │  │  probes:            │         │  LUNA_ENV, LOG_LEVEL, │   │  │
│  │  │   /health (live)    │         │  ROUTING_THRESHOLD   │    │  │
│  │  │   /ready (ready)    │         └──────────────────────┘    │  │
│  │  └──────────┬──────────┘                                     │  │
│  │             │ HTTPS (outbound)                               │  │
│  └─────────────┼────────────────────────────────────────────────┘  │
│                ▼                                                   │
│  api.groq.com  (Groq LLM inference — the only external dependency) │
└────────────────────────────────────────────────────────────────────┘
```

**One paragraph version:** a single FastAPI service runs as a pod in a local
`kind` Kubernetes cluster. Your browser reaches it through a
`kubectl port-forward` tunnel. Inside the pod, each `/chat` request is
routed by a keyword heuristic (with an LLM-classifier fallback) to one of
four agents, which streams a response from Groq back over SSE. Non-secret
config comes from a ConfigMap, the Groq API key from a Secret. The chat UI
is one static HTML file served by the same process; conversation history
currently lives in the browser (localStorage) until Phase 3 moves it into
Postgres.

## 2. Repository layout — what lives where

```
~/luna/
├── src/luna/                  ← the application (Python)
│   ├── main.py                │  app factory: builds FastAPI app, wires
│   │                          │  middleware/routers, lifespan builds the
│   │                          │  GroqClient + agent registry + router
│   ├── config.py              │  ALL env config in one typed Settings class
│   ├── core/
│   │   └── models.py          │  framework-agnostic domain types (Message)
│   ├── api/                   │  HTTP layer (the only place that knows FastAPI)
│   │   ├── routes_health.py   │    GET /health (liveness), GET /ready
│   │   ├── routes_chat.py     │    POST /chat (SSE stream), GET /route-debug
│   │   ├── schemas.py         │    Pydantic request/response models
│   │   └── deps.py            │    DI providers (Depends) — the test seam
│   ├── agents/                │  the "who answers" layer (Strategy pattern)
│   │   ├── base.py            │    Agent Protocol + SimpleAgent base class
│   │   ├── assistant_agent.py │    general default agent
│   │   ├── coding_agent.py    │    code/debugging questions
│   │   ├── infra_agent.py     │    k8s/cloud/SRE questions
│   │   ├── product_agent.py   │    roadmap/features questions
│   │   └── registry.py        │    name → Agent dict, built once at startup
│   ├── routing/               │  the "which agent" layer
│   │   ├── heuristics.py      │    pure keyword scorer — NO network, no I/O
│   │   ├── llm_classifier.py  │    paid fallback for ambiguous messages
│   │   └── router.py          │    heuristic first, LLM only below threshold
│   ├── llm/
│   │   ├── groq_client.py     │  the ONLY module that imports the groq SDK
│   │   └── streaming.py       │    SSE text formatting helpers
│   ├── observability/         │  code that EMITS telemetry
│   │   ├── logging.py         │    structlog JSON config
│   │   └── middleware.py      │    request-id + timing on every request
│   └── (db/, rag/ arrive in Phases 3 and 5)
├── web/
│   └── index.html             ← single-file chat UI (sidebar + streaming)
├── k8s/                       ← deployment manifests (what the cluster runs)
│   ├── base/
│   │   ├── kustomization.yaml │  kustomize entrypoint: `kubectl apply -k`
│   │   ├── namespace.yaml     │  creates the `luna` namespace
│   │   ├── deployment.yaml    │  the app: 1 replica, probes, env wiring
│   │   ├── service.yaml       │  stable in-cluster name `luna-app:8000`
│   │   └── configmap.yaml     │  non-secret config (env, log level, thresholds)
│   └── jobs/                  │  (one-off Jobs, e.g. migrations — Phase 3)
├── tests/
│   ├── unit/                  │  zero-network tests (heuristics, SSE, router)
│   └── integration/           │  (real Postgres/Qdrant/Groq — later phases)
├── Dockerfile                 ← how the app becomes an image
├── Makefile                   ← every command you need, one word each
├── pyproject.toml / uv.lock   ← deps (uv), tool config (ruff/mypy/pytest)
├── .env                       ← real secrets, GITIGNORED (host dev only)
└── .env.example               ← committed template showing what's needed
```

### Layering rules (the part that makes it "production-grade in design")

Import discipline enforces clean boundaries — this is what "service
boundaries" means for a single deployable service:

- `routing/` never imports `api/` — routing is pure decision logic, testable
  without HTTP
- `agents/` never imports `db/` or `api/` — agents operate on `core` types
- only `llm/groq_client.py` imports the `groq` SDK — swap providers by
  changing one file
- `api/` is the only place that converts HTTP/Pydantic ↔ `core` types

## 3. The request flow, end to end

What actually happens when you send "my k8s pod is crash looping" and hit Send:

1. **Browser** POSTs `{"message": "..."}` to `/chat` and reads the response
   as a stream (fetch + ReadableStream, because EventSource can't POST).
2. **Middleware** tags the request with a request-id; every log line from
   here on carries it.
3. **Route handler** asks the `AgentRouter` to decide: the keyword heuristic
   scores "k8s" and "pod" → `infra`, confidence 1.0 → above threshold →
   no LLM call needed (this is the cost-governance fast path).
4. **Registry lookup**: `registry["infra"]` → the InfraAgent instance built
   at startup.
5. **SSE stream starts**: first event is `event: routed` (so the UI can show
   "answered by: infra"), then `event: token` chunks as Groq generates them,
   ending with `event: done` (or `event: error` on failure).
6. **Async machinery**: the handler is an async generator; if you close the
   browser tab mid-stream, Starlette raises `CancelledError` at the current
   `await`, cleanup still runs via `finally`, and the upstream Groq socket
   is released.

## 4. Kubernetes — what's running where

View it all:

```bash
kubectl get all -n luna          # every object in the namespace
kubectl get pods -n luna -o wide # pod status + which node
```

| Object | Name | What it is / why it exists |
|---|---|---|
| Namespace | `luna` | Isolates all Luna objects from cluster system stuff |
| Deployment | `luna-app` | Runs the app pod; handles rolling updates, self-healing |
| Pod | `luna-app-<hash>-<rand>` | The actual running container (FastAPI + uvicorn) |
| Service | `luna-app` | Stable internal DNS name + load balancing over pods |
| ConfigMap | `luna-config` | Non-secret env config (committed to git — safe) |
| Secret | `luna-secrets` | `GROQ_API_KEY` — created imperatively, never committed |

Probe wiring (this is the liveness-vs-readiness distinction, in practice):

- `livenessProbe` → `GET /health` — failure means kubelet **kills and
  restarts** the container. Deliberately checks nothing external.
- `readinessProbe` → `GET /ready` — failure just pulls the pod out of the
  Service rotation (no restart). Will check DB/Qdrant in later phases.

Image flow (why `make deploy` does four things):

```
docker build → kind load docker-image → kubectl apply -k k8s/base
             → kubectl rollout restart (needed: static luna:dev tag means
               `apply` alone can't see that the image CONTENT changed)
```

## 5. Every command you need

All from `~/luna`. `make <target>` runs them; the raw commands are listed
so you know what each actually does.

### Daily driving

| Do this | make | Raw command |
|---|---|---|
| Install/sync deps | `make sync` | `uv sync` |
| Run app on host (dev, :8001) | `make run` | `uv run uvicorn luna.main:app --reload --port 8001` |
| Run all tests | `make test` | `uv run pytest` |
| Lint + type-check | `make lint` | `uv run ruff check src tests && uv run mypy src` |

### Cluster lifecycle

| Do this | make | Raw command |
|---|---|---|
| Create the cluster (once) | `make kind-up` | `kind create cluster --name luna` |
| Delete the cluster | `make kind-down` | `kind delete cluster --name luna` |
| See cluster info | — | `kubectl cluster-info --context kind-luna` |

### Build & deploy

| Do this | make | Raw command |
|---|---|---|
| Full rebuild + redeploy | `make deploy` | build → load → apply → rollout restart → wait |
| Build image only | `make build` | `docker build -t luna:dev .` |
| Load image into kind | `make load` | `kind load docker-image luna:dev --name luna` |
| Apply manifests only | — | `kubectl apply -k k8s/base` |
| Restart pods (pick up new image) | — | `kubectl rollout restart deployment/luna-app -n luna` |
| Wait for rollout to finish | — | `kubectl rollout status deployment/luna-app -n luna` |

### Observing the running system

| Do this | make | Raw command |
|---|---|---|
| Pod status | `make status` | `kubectl get pods -n luna -o wide` |
| Follow logs | `make logs` | `kubectl logs -n luna -l app=luna --tail=100 -f` |
| Tunnel to localhost:8000 | `make port-forward` | `kubectl port-forward -n luna svc/luna-app 8000:8000` |
| Shell into the pod | — | `kubectl exec -it -n luna deploy/luna-app -- bash` |
| Everything in the namespace | — | `kubectl get all -n luna` |
| Pod details/events/probes | — | `kubectl describe pod -n luna -l app=luna` |
| Env vars inside the pod | — | `kubectl exec -n luna deploy/luna-app -- printenv` |
| Delete the pod (resilience demo) | — | `kubectl delete pod -n luna -l app=luna` |

### Secrets

| Do this | make | Raw command |
|---|---|---|
| Create/update the Groq Secret from `.env` | `make create-secret` | `kubectl create secret generic luna-secrets ... --dry-run=client -o yaml \| kubectl apply -f -` |

(Also see `make port-forward` above, then open http://localhost:8000 for
the browser UI.)

## 6. HTTP API

| Endpoint | Method | What it does |
|---|---|---|
| `/health` | GET | Liveness — process alive? (k8s kill/restart signal) |
| `/ready` | GET | Readiness — can serve traffic? 200 or 503 |
| `/chat` | POST | `{message}` → SSE stream: `routed`, `token`…, `done`/`error` |
| `/route-debug?message=...` | GET | Show routing decision without generating a response |
| `/` | GET | The chat UI |

Example:

```bash
# routing decision only (cheap)
curl -G "http://localhost:8000/route-debug" --data-urlencode "message=k8s pod crash looping"

# full streamed chat
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "k8s pod crash looping"}'
```

## 7. Where the project is going (the phased plan)

| Phase | Scope | Status |
|---|---|---|
| 0 | Scaffolding + first k8s deploy (probes, logging, request-id) | ✅ done |
| 1 | Single-agent streaming chat (Groq + SSE) | ✅ done |
| 2 | Multi-agent routing + ChatGPT-style UI with history | ✅ done |
| 3 | Postgres persistence (StatefulSet+PVC, Alembic, /conversations API, pod-delete-resume demo) | next |
| 4 | Cost tracking (cost_events table) + Prometheus /metrics | |
| 5 | RAG (Qdrant StatefulSet, local embeddings, /documents) | |
| 6 | Resilience (retries/cooldown) + full observability (kube-prometheus-stack, loki-stack via Helm) | |

## 8. Honest limitations (deliberate, documented)

- **History is browser-local.** The sidebar's conversation list is
  localStorage — per-browser, not synced. Phase 3 replaces this with real
  server-side persistence; the UI storage layer is isolated for exactly
  that swap.
- **Each message is answered independently** — no multi-turn memory yet
  (Phase 3).
- **Heuristic routing is deliberately simple** — weighted keywords, not
  embeddings. The LLM-classifier fallback covers its blind spots; both are
  swappable behind the `AgentRouter` interface.
- **`kind`, not a cloud** — the manifests are real k8s, but there's no
  Ingress/LB/TLS story (port-forward instead). That's a $0-cost trade, and
  the objects used (Deployments, StatefulSets, Jobs, Helm charts) are the
  same ones EKS/GKE would run.
- The Groq key in `.env` should be treated as exposed (it was pasted into a
  chat) — rotate at console.groq.com/keys when convenient; `make
  create-secret` makes rotating a one-command operation.
