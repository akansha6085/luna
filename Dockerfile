# Slim base + uv's own image for fast, reproducible installs.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Copy dependency files first so Docker's layer cache is reused whenever
# only application code changes (the common case) — the slow "install every
# dependency from scratch" step only reruns when pyproject.toml/uv.lock
# actually change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
COPY web ./web
# alembic.ini + migrations/ are needed at RUNTIME, not build time — the
# migration Job (k8s/jobs/migrate.yaml) runs `alembic upgrade head`
# inside this exact image. Forgetting these is a silent-until-you-run-it
# gap: the app itself never touches them, only this Job does.
COPY alembic.ini ./
COPY migrations ./migrations
RUN uv sync --frozen --no-dev

# Don't run the app as root inside the container — if something did manage
# to break out of the app process, root-in-container is a meaningfully
# worse position to be in than a dedicated unprivileged user.
RUN useradd --create-home --uid 1000 luna && chown -R luna:luna /app
USER luna

EXPOSE 8000

# --frozen --no-dev: without these, `uv run` re-checks pyproject.toml/
# uv.lock against the venv on EVERY container start and, finding no
# active "skip dev deps" preference recorded anywhere, re-syncs
# including the dev dependency group — undoing the build-time --no-dev,
# adding real startup latency, needing network access to PyPI that a
# production container shouldn't depend on, and (observed directly,
# hitting this in the migration Job below) can leave a project script's
# entry point missing afterward. --frozen also refuses to touch the
# lockfile at all — exactly right for an image that should be immutable
# once built.
CMD ["uv", "run", "--frozen", "--no-dev", "uvicorn", "luna.main:app", "--host", "0.0.0.0", "--port", "8000"]
