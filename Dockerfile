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
RUN uv sync --frozen --no-dev

# Don't run the app as root inside the container — if something did manage
# to break out of the app process, root-in-container is a meaningfully
# worse position to be in than a dedicated unprivileged user.
RUN useradd --create-home --uid 1000 luna && chown -R luna:luna /app
USER luna

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "luna.main:app", "--host", "0.0.0.0", "--port", "8000"]
