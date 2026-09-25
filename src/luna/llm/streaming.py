"""Shared SSE (Server-Sent Events) formatting.

SSE is a plain text protocol: each event is one or more `field: value`
lines followed by a blank line. We use two fields — `event` (a type tag
the browser's JS can dispatch on: "token" / "error" / "done") and `data`
(a JSON payload) — terminated by the required trailing blank line.
"""

import json
from typing import Any


def sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
