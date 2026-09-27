# Luna

A personal learning project: a scaled-down, production-disciplined clone of
an internal AI agent-orchestration platform — multi-agent routing, streaming
chat (SSE), multi-turn conversations persisted in Postgres, with LLM cost
governance and RAG still ahead. Built to learn backend/system design
hands-on and to get real Kubernetes reps.

**Not built at, or affiliated with, any employer** — a personal project
inspired by exposure to real internal tooling of this shape. Everything runs
locally on a laptop via `kind` (Kubernetes-in-Docker): total infra cost $0.

---

## 1. The big picture

```
        YOUR LAPTOP (macOS)
┌──────────────────────────────────────────────────────────────────────┐
│  Browser (web/index.html)                                            │
│  http://localhost:8000                                               │
│      │  POST /chat (SSE stream over fetch)                           │
│      │  GET /conversations · DELETE /conversations/{id}              │
│      ▼                                                               │
│  ┌─────────────── kubectl port-forward (tunnel) ─────────────────┐   │
│  │  localhost:8000 ──────────────────►  svc/luna-app:8000        │   │
│  └────────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  kind cluster  ─────────────────────  context: kind-luna             │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  namespace: luna                                               │  │
│  │                                                                │  │
│  │  ┌─────────────────────┐   SQL (asyncpg)  ┌─────────────────┐  │  │
│  │  │ Pod: luna-app-xxx   │ ───────────────► │ Pod: postgres-0 │  │  │
│  │  │ Deployment, 1 repl  │  svc/postgres    │ StatefulSet     │  │  │
│  │  │  FastAPI/uvicorn    │   (headless)     │  + 1Gi PVC      │  │  │
│  │  │  :8000              │                  │ data survives   │  │  │
│  │  │                     │                  │ pod deletion    │  │  │
│  │  └──────────┬──────────┘                  └─────────────────┘  │  │
│  │             │ env at startup                                   │  │
│  │  ┌──────────┴───────────────────────────────────────────────┐  │  │
│  │  │ ConfigMap luna-config      LUNA_ENV, LOG_LEVEL,          │  │  │
│  │  │                            ROUTING_CONFIDENCE_THRESHOLD  │  │  │
│  │  │ Secret luna-secrets        GROQ_API_KEY                  │  │  │
│  │  │ Secret luna-db-credentials POSTGRES_PASSWORD,            │  │  │
│  │  │                            DATABASE_URL (→ postgres:5432)│  │  │
│  │  └──────────────────────────────────────────────────────────┘  │  │
│  │                                                                │  │
│  │  Job luna-migrate — runs `alembic upgrade head`, then exits    │  │
│  │  (runs BETWEEN postgres coming up and the app rolling out)     │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                │ HTTPS (outbound)                                    │
│                ▼                                                     │
│  api.groq.com  (Groq LLM inference — the only external dependency)   │
└──────────────────────────────────────────────────────────────────────┘
```

**One paragraph version:** a single FastAPI service runs as a stateless pod
in a local `kind` Kubernetes cluster, with Postgres as a StatefulSet beside
it. Your browser reaches the app through a `kubectl port-forward` tunnel.
Each `/chat` request is routed by a keyword heuristic (with an LLM-classifier
fallback) to one of four agents; the user's message is persisted *before*
generation starts, the reply streamed back over SSE and persisted in
`finally` (even partial text on errors/disconnects), and prior turns of the
same conversation are loaded as context — real multi-turn memory. Because
the app pods hold no state, `kubectl delete pod` mid-conversation is
survivable: the replacement pod picks the thread up from Postgres. Schema
changes run as a Kubernetes Job (Alembic) between "database up" and "app
rolled out". The chat UI is one static HTML file served by the same process.

## 2. Repository layout — what lives where

```
~/luna/
├── src/luna/                  ← the application (Python)
│   ├── main.py                │  app factory: wires routers/middleware; the
│   │                          │  lifespan builds GroqClient, agent registry,
│   │                          │  router, AND the DB engine + sessionmaker,
│   │                          │  and registers the DB readiness check
│   ├── config.py              │  ALL env config in one typed Settings class
│   ├── core/
│   │   └── models.py          │  framework-agnostic domain types (Message) —
│   │                          │  what agents/routing/llm operate on
│   ├── api/                   │  HTTP layer (the only place that knows FastAPI)
│   │   ├── routes_chat.py     │    POST /chat (SSE, persisted, multi-turn),
│   │   │                      │    GET /route-debug
│   │   ├── routes_conversations.py │ GET/DELETE /conversations (sidebar API)
│   │   ├── routes_health.py   │    /health (liveness), /ready (readiness)
│   │   ├── schemas.py         │    Pydantic request/response models
│   │   └── deps.py            │    DI providers — the one test seam
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
│   ├── db/                    │  the persistence layer (Phase 3)
│   │   ├── base.py            │    async engine + sessionmaker + DB health check
│   │   ├── models.py          │    ORM models: conversations, messages,
│   │   │                      │    routing_decisions
│   │   └── repositories/      │    the ONLY code that touches the ORM:
│   │       ├── conversations.py │  one repo per aggregate
│   │       ├── messages.py    │
│   │       └── routing_decisions.py
│   └── observability/         │  code that EMITS telemetry
│       ├── logging.py         │    structlog JSON config
│       └── middleware.py      │    request-id + timing on every request
├── migrations/                ← Alembic (schema versioning)
│   ├── env.py                 │  async variant (run_sync bridge, not the
│   │                          │  sync template alembic init gives you)
│   └── versions/              │  generated migration scripts (in git)
├── web/
│   └── index.html             ← single-file chat UI (sidebar + typewriter +
│                              │   themes + server-backed history)
├── k8s/                       ← deployment manifests (what the cluster runs)
│   ├── base/
│   │   ├── kustomization.yaml │  `kubectl apply -k` entrypoint (app objects)
│   │   ├── namespace.yaml     │  the `luna` namespace
│   │   ├── deployment.yaml    │  the app: probes, env wiring, secrets
│   │   ├── service.yaml       │  stable in-cluster name `luna-app:8000`
│   │   ├── configmap.yaml     │  non-secret config (committed — safe)
│   │   ├── postgres-statefulset.yaml │ DB as a StatefulSet + PVC — applied
│   │   │                      │    DIRECTLY, not via kustomize (ordering)
│   │   └── postgres-service.yaml │  headless Service for the StatefulSet
│   └── jobs/
│       └── migrate.yaml       │  Alembic migration as a K8s Job
├── tests/
│   ├── unit/                  │  zero external services (default test run)
│   └── integration/           │  real Postgres (separate luna_test database)
├── alembic.ini                ← alembic config (URL comes from Settings)
├── docker-compose.dev.yml     ← local Postgres for the HOST dev loop only —
│                              │  not the deploy target
├── Dockerfile                 ← how the app becomes an image (also what the
│                              │  migration Job runs from)
├── Makefile                   ← every command you need, one word each
├── pyproject.toml / uv.lock   ← deps (uv), tool config (ruff/mypy/pytest)
├── .env                       ← real secrets, GITIGNORED (host dev only)
└── .env.example               ← committed template showing what's needed
```

### Layering rules (the part that makes it "production-grade in design")

Import discipline enforces clean boundaries — this is what "service
boundaries" means for a single deployable service:

- `routing/` never imports `api/` or `db/` — routing is pure decision logic
- `agents/` never imports `db/` or `api/` — agents operate on `core` types
  only; `db/repositories/messages.py` is where ORM rows convert INTO
  `core.models.Message` (the conversion boundary)
- only `llm/groq_client.py` imports the `groq` SDK — swap providers by
  changing one file
- only `db/repositories/` touch ORM objects — route handlers never write
  raw queries, which is what makes them testable against fake repos
- `api/` is the only place that converts HTTP/Pydantic ↔ `core` types

There are deliberately **three type systems** that never blur:
`core.models.Message` (domain), `db.models` (Postgres rows), and
`api.schemas` (the wire contract). Conversions happen only at boundaries.

## 3. The request flow, end to end

What actually happens when you send "my k8s pod is crash looping" and hit Send:

1. **Browser** POSTs `{"message": "...", "conversation_id": ...}` to `/chat`
   and reads the response as a stream (fetch + ReadableStream, because
   EventSource can't POST). `conversation_id` is absent on a brand-new
   conversation.
2. **Middleware** tags the request with a request-id; every log line from
   here on carries it.
3. **Conversation resolution**: no id → a row is created in Postgres and its
   id streams back as the FIRST SSE event (`conversation`); existing id →
   prior turns are loaded from Postgres as context (the multi-turn memory).
4. **Routing**: the keyword heuristic scores "k8s" and "pod" → `infra`,
   confidence 1.0 → above threshold → no LLM call needed (the
   cost-governance fast path). Low confidence falls back to a cheap LLM
   classifier call.
5. **Persist-then-generate**: the user's message is written to Postgres
   BEFORE the Groq call starts — a crash mid-generation still leaves the
   user's words saved. The routing decision is also recorded (audit trail).
6. **SSE stream**: `conversation` → `routed` (so the UI can badge "answered
   by: infra") → `token` chunks → `done` (or `error`).
7. **Persist-in-finally**: the assistant's reply is saved in a `finally`
   block — normal completion, caught errors, AND client disconnects (a
   closed browser tab raises `CancelledError`, a `BaseException`, which
   skips both `except` clauses and still lands in `finally`). A partial
   answer you can see on reload beats silently losing one.

## 4. Kubernetes — what's running where

View it all:

```bash
kubectl get all -n luna          # every object in the namespace
kubectl get pods -n luna -o wide # pod status + which node
```

| Object | Name | What it is / why it exists |
|---|---|---|
| Namespace | `luna` | Isolates all Luna objects from cluster system stuff |
| Deployment | `luna-app` | Runs the stateless app pod; rolling updates, self-healing |
| Pod | `luna-app-<rs>-<rand>` | The running container (FastAPI + uvicorn) |
| Service | `luna-app` | Stable in-cluster name + load balancing over app pods |
| **StatefulSet** | `postgres` | The database. A StatefulSet (not a Deployment) because its PVC is bound to the pod identity and survives restarts/rescheduling — the property state actually needs |
| **Service (headless)** | `postgres` | `clusterIP: None` — DNS resolves straight to the pod; the canonical StatefulSet pattern |
| **PVC** | `postgres-data-postgres-0` | The 1Gi volume holding the actual data |
| **Job** | `luna-migrate` | Runs `alembic upgrade head` once, to completion, then exits |
| ConfigMap | `luna-config` | Non-secret env config (committed to git — safe) |
| Secret | `luna-secrets` | `GROQ_API_KEY` — created imperatively, never committed |
| Secret | `luna-db-credentials` | `POSTGRES_PASSWORD` + in-cluster `DATABASE_URL` |

Probe wiring (liveness vs readiness, in practice):

- `livenessProbe` → `GET /health` — failure means kubelet **kills and
  restarts** the container. Checks nothing external.
- `readinessProbe` → `GET /ready` — failure just pulls the pod out of the
  Service rotation (no restart). Now genuinely checks **Postgres**
  (`SELECT 1`); Phase 5 adds Qdrant to the same list.

### Deploy ordering — why `make deploy` is three steps

```
make deploy  =  deploy-db  →  migrate-k8s  →  deploy-app
                (postgres    (alembic Job     (build → kind load →
                StatefulSet   must complete    apply → rollout restart)
                up + Ready)   BEFORE app)
```

The Postgres manifests live in `k8s/base/` but are deliberately NOT in
`kustomization.yaml`: `kubectl apply -k` applies everything at once with no
ordering guarantee, and "app pod starts before its database exists / before
its schema is migrated" is exactly the failure mode this ordering exists to
prevent. The migration runs as a **Job** (one-off work, not a long-running
process); Jobs are immutable, so the old one is deleted before each apply.

### Image flow (why deploy-app does four things)

```
docker build → kind load docker-image → kubectl apply -k k8s/base
             → kubectl rollout restart (needed: static luna:dev tag means
               `apply` alone can't see that the image CONTENT changed)
```

Tunnel caveat worth knowing: `kubectl port-forward` pins to ONE pod at
start. After any rollout the old pod is gone, so the tunnel dies —
`pkill -f port-forward` and rerun `make port-forward`.

## 5. Every command you need

All from `~/luna`. `make <target>` runs them; the raw commands are listed
so you know what each actually does.

### Daily driving

| Do this | make | Raw command |
|---|---|---|
| Install/sync deps | `make sync` | `uv sync` |
| Run app on host (dev, :8001) | `make run` | `uv run uvicorn luna.main:app --reload --port 8001` |
| Run unit tests (no services needed) | `make test` | `uv run pytest` |
| Run integration tests (needs Postgres) | `make test-integration` | `uv run pytest tests/integration` |
| Lint + type-check | `make lint` | `uv run ruff check src tests && uv run mypy src` |
| Apply DB migrations (host dev) | `make migrate` | `uv run alembic upgrade head` |

### Local backing services

| Do this | make | Raw command |
|---|---|---|
| Start dev Postgres (Docker) | `make compose-up` | `docker compose -f docker-compose.dev.yml up -d` |
| Stop it | `make compose-down` | `docker compose -f docker-compose.dev.yml down` |

(Host-run dev loop = `make compose-up` + `make migrate` + `make run`;
the app talks to Postgres on `localhost:5432` via `DATABASE_URL` in `.env`.)

### Cluster lifecycle

| Do this | make | Raw command |
|---|---|---|
| Create the cluster (once) | `make kind-up` | `kind create cluster --name luna` |
| Delete the cluster | `make kind-down` | `kind delete cluster --name luna` |
| See cluster info | — | `kubectl cluster-info --context kind-luna` |

### Build & deploy (ordered)

| Do this | make | What it does |
|---|---|---|
| **Full deploy, correct order** | `make deploy` | deploy-db → migrate-k8s → deploy-app |
| DB + credentials only | `make deploy-db` | create-db-secret, apply StatefulSet+Service, wait Ready |
| Run migration in-cluster | `make migrate-k8s` | delete+apply the Job, wait for completion |
| App only (image already built) | `make deploy-app` | build → kind load → apply → rollout restart → wait |
| Build image only | `make build` | `docker build -t luna:dev .` |
| Load image into kind | `make load` | `kind load docker-image luna:dev --name luna` |
| Apply app manifests only | — | `kubectl apply -k k8s/base` |
| Restart pods (pick up new image) | — | `kubectl rollout restart deployment/luna-app -n luna` |

### Secrets (imperative, never committed)

| Do this | make | Notes |
|---|---|---|
| Groq key from `.env` | `make create-secret` | idempotent (dry-run\|apply pattern) |
| DB credentials for the cluster | `make create-db-secret` | same password as `.env`, hostname swapped `localhost` → `postgres` |

### Observing the running system

| Do this | make | Raw command |
|---|---|---|
| Pod status | `make status` | `kubectl get pods -n luna -o wide` |
| Follow logs | `make logs` | `kubectl logs -n luna -l app=luna --tail=100 -f` |
| Tunnel to localhost:8000 | `make port-forward` | `kubectl port-forward -n luna svc/luna-app 8000:8000` |
| Shell into the app pod | — | `kubectl exec -it -n luna deploy/luna-app -- bash` |
| PSQL inside the cluster DB | — | `kubectl exec -it -n luna postgres-0 -- psql -U luna -d luna` |
| Everything in the namespace | — | `kubectl get all -n luna` |
| Delete the pod (statelessness demo) | — | `kubectl delete pod -n luna -l app=luna` |

## 6. HTTP API

| Endpoint | Method | What it does |
|---|---|---|
| `/health` | GET | Liveness — process alive? (k8s kill/restart signal) |
| `/ready` | GET | Readiness — checks Postgres; 200 or 503 |
| `/chat` | POST | `{message, conversation_id?}` → SSE: `conversation`, `routed`, `token`…, `done`/`error`. No id → creates a conversation and returns its id in the first event |
| `/conversations` | GET | Sidebar list, most-recently-active first |
| `/conversations/{id}/messages` | GET | Full message history (404 if unknown id) |
| `/conversations/{id}` | DELETE | Idempotent delete (cascades to messages) |
| `/route-debug?message=...` | GET | Routing decision without generating a response |
| `/` | GET | The chat UI |

Examples:

```bash
# routing decision only (cheap)
curl -G "http://localhost:8000/route-debug" --data-urlencode "message=k8s pod crash looping"

# full streamed chat (multi-turn: reuse the id from the `conversation` event)
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "k8s pod crash looping"}'
```

## 7. The multi-turn + statelessness demo (the point of Phase 3)

```bash
# 1. start a conversation, tell it something
curl -N -X POST localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"message": "Remember the codeword PINEAPPLE."}'
# → note the conversation_id from the first SSE event

# 2. kill the app pod outright
kubectl delete pod -n luna -l app=luna
# the Deployment reschedules a brand-new pod in seconds

# 3. re-establish the tunnel (port-forward was pinned to the old pod)
pkill -f port-forward && kubectl port-forward -n luna svc/luna-app 8000:8000

# 4. ask the BRAND-NEW pod, same conversation_id
curl -N -X POST localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"message": "What was the codeword?", "conversation_id": "<id>"}'
# → "You mentioned the code word PINEAPPLE" — read from Postgres by a
#    process that never saw the original message
```

This is the statelessness property that makes horizontal scaling possible:
app pods carry no state, so any pod can serve any request, and pods are
cattle — killable, reschedulable, replaceable — while the StatefulSet's PVC
is the pet that holds the data.

## 8. Where the project is going (the phased plan)

| Phase | Scope | Status |
|---|---|---|
| 0 | Scaffolding + first k8s deploy (probes, logging, request-id) | ✅ done |
| 1 | Single-agent streaming chat (Groq + SSE) | ✅ done |
| 2 | Multi-agent routing + ChatGPT-style UI (sidebar, themes, typewriter) | ✅ done |
| 3 | Postgres persistence, Alembic-as-K8s-Job, multi-turn memory, server-backed history | ✅ done |
| 4 | Cost tracking (`cost_events` table) + Prometheus `/metrics` + resource requests/limits | next |
| 5 | RAG (Qdrant StatefulSet, local embeddings, /documents) | |
| 6 | Resilience (retries/cooldown) + full observability (kube-prometheus-stack, loki-stack via Helm) | |

## 9. Honest limitations (deliberate, documented)

- **Heuristic routing is deliberately simple** — weighted keywords, not
  embeddings. The LLM-classifier fallback covers its blind spots; both are
  swappable behind the `AgentRouter` interface.
- **One user, no auth** — conversations have no owner concept yet; anyone
  with the URL shares the sidebar. Auth/users is a deliberate non-goal for
  a local learning build (would be its own phase in a real system).
- **Single-replica everything** — the design is stateless and *could* scale
  out (no sticky sessions, no in-memory state), but kind + 1 replica is the
  honest size for a laptop demo.
- **`kind`, not a cloud** — the manifests are real k8s, but there's no
  Ingress/LB/TLS story (port-forward instead). That's a $0-cost trade, and
  the objects used (Deployments, StatefulSets, Jobs, PVCs) are the same
  ones EKS/GKE would run.
- The Groq key in `.env` should be treated as exposed (it was pasted into a
  chat) — rotate at console.groq.com/keys when convenient; `make
  create-secret` makes rotating a one-command operation.
