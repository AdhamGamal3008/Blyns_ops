"""Environment-driven logging (docs/ENVIRONMENTS.md §1/§4).

    local      → DEBUG, pretty single-line text
    test       → WARNING, pretty (quiet under pytest)
    production → INFO, structured JSON (one object per line)

Fully custom — the JSON formatter is stdlib `logging` only, no external deps.
`configure_logging` is idempotent so repeated `create_app` calls (tests) don't
stack handlers.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import UTC, datetime

from app.core.config import Settings

_LEVEL_BY_ENV = {"local": logging.DEBUG, "test": logging.WARNING, "production": logging.INFO}

# stdlib LogRecord attributes we never want to duplicate into the JSON `extra`.
_RESERVED = set(
    logging.makeLogRecord({}).__dict__
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Render a record as a single-line JSON object. Any structured fields passed
    via `logger.info(msg, extra={...})` are merged in at the top level."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(cfg: Settings) -> None:
    level = _LEVEL_BY_ENV.get(cfg.env, logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    if cfg.env == "production":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )

    root = logging.getLogger()
    root.setLevel(level)
    # Replace our own handler(s) only, so re-running is idempotent.
    for existing in list(root.handlers):
        if getattr(existing, "_erp_handler", False):
            root.removeHandler(existing)
    handler._erp_handler = True  # type: ignore[attr-defined]
    root.addHandler(handler)


class AccessLogMiddleware:
    """One structured line per request: method, path, status, duration. Failures
    in logging never affect the response."""

    def __init__(self, app, cfg: Settings | None = None) -> None:
        self.app = app
        self._log = logging.getLogger("erp.access")

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.monotonic()
        status_holder = {"code": 500}

        async def _send(message):
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            try:
                client = scope.get("client")
                self._log.info(
                    "request",
                    extra={
                        "method": scope.get("method"),
                        "path": scope.get("path"),
                        "status": status_holder["code"],
                        "duration_ms": round((time.monotonic() - started) * 1000, 1),
                        "client": client[0] if client else None,
                    },
                )
            except Exception:
                pass
