"""Thin wrapper around the Groq SDK.

Everything that talks to Groq goes through this one class, for three
reasons:

1. Explicit timeouts. The raw SDK has no timeout by default — a hung
   upstream connection would hang our request (and, later, the SSE
   stream) indefinitely.
2. A single seam to add retries/backoff/circuit-breaking later (Phase 6)
   without touching agents/ at all.
3. Converts our own `Message` type to/from the SDK's plain dicts, so
   agents/ never has to import anything from the `groq` package.
"""

from collections.abc import AsyncIterator
from typing import cast

from groq import AsyncGroq, AsyncStream
from groq.types.chat import ChatCompletionChunk

from luna.core.models import Message

DEFAULT_TIMEOUT_SECONDS = 30.0


class GroqError(Exception):
    """Raised when an upstream Groq call fails, wrapping the original cause.

    Route handlers catch this specifically (not a bare `except Exception`
    for everything) so an upstream failure can be told apart from a bug
    in our own code — see api/routes_chat.py.
    """


class GroqClient:
    def __init__(self, api_key: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._client = AsyncGroq(api_key=api_key, timeout=timeout)

    async def stream_chat(self, messages: list[Message], model: str) -> AsyncIterator[str]:
        """Yield response text chunks as they arrive from Groq.

        Two separate try/except blocks on purpose: failing to even START
        the stream (bad model name, auth failure, connect timeout) is a
        different failure shape from failing PARTWAY THROUGH an
        already-started stream (read timeout, connection drop) — both are
        wrapped as GroqError either way, but keeping them as separate
        blocks makes it obvious neither path is accidentally uncaught.
        """
        payload = [{"role": m.role, "content": m.content} for m in messages]
        try:
            raw_stream = await self._client.chat.completions.create(
                model=model,
                messages=payload,  # type: ignore[arg-type]
                stream=True,
            )
        except Exception as exc:
            raise GroqError(f"failed to start Groq stream: {exc}") from exc

        # `stream=True` above guarantees an AsyncStream at runtime; mypy's
        # overload resolution doesn't narrow it (the SDK's overloads key
        # off a Literal[True]/[False] `stream` param, which our `messages=`
        # type-ignore above appears to interfere with) — this cast just
        # tells mypy what we already know to be true.
        stream = cast(AsyncStream[ChatCompletionChunk], raw_stream)

        try:
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as exc:
            raise GroqError(f"Groq stream failed mid-response: {exc}") from exc
