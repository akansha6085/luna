"""Single source of truth for app configuration.

Why this exists as a typed class instead of scattering `os.environ.get(...)`
calls through the codebase:

1. Fails fast at startup if config is missing/invalid, instead of failing
   deep inside a request handler the first time that code path runs.
2. One place to see everything the app depends on from its environment.
3. Trivially fakeable in tests (`Settings(log_level="DEBUG")`) without
   mutating real process environment variables.

Deliberately minimal right now (Phase 0). Fields get added phase-by-phase as
the app actually needs them (GROQ_API_KEY in Phase 1, DATABASE_URL in
Phase 3, ...) rather than speculatively — config should track real need.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LUNA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # What environment this process thinks it's running in. Not security-
    # sensitive itself, but downstream code (e.g. log formatting, debug
    # endpoints) can branch on it.
    env: str = "local"

    log_level: str = "INFO"

    service_name: str = "luna"


@lru_cache
def get_settings() -> Settings:
    """Cached so we parse the environment once per process, not per request.

    FastAPI route handlers depend on this via `Depends(get_settings)`
    (see api/deps.py once it exists) rather than importing a module-level
    singleton directly — that's the seam that lets tests override config.
    """
    return Settings()
