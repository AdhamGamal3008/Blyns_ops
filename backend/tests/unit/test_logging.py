"""Environment-driven logging (docs/ENVIRONMENTS.md §1/§4): production emits
structured JSON at INFO; local/test use pretty text at DEBUG/WARNING."""

from __future__ import annotations

import json
import logging

from app.core.config import Settings
from app.core.logging import JsonFormatter, configure_logging


def _cfg(env: str) -> Settings:
    return Settings(_env_file=None, env=env, jwt_secret="x" * 48)


def test_json_formatter_emits_one_object_with_extra_fields():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="erp.access", level=logging.INFO, pathname=__file__, lineno=1,
        msg="request", args=(), exc_info=None,
    )
    record.method = "POST"
    record.path = "/api/v1/projects"
    record.status = 201

    line = formatter.format(record)
    payload = json.loads(line)  # a single valid JSON object per line
    assert payload["level"] == "INFO"
    assert payload["logger"] == "erp.access"
    assert payload["message"] == "request"
    assert payload["method"] == "POST"
    assert payload["path"] == "/api/v1/projects"
    assert payload["status"] == 201
    assert "ts" in payload


def test_json_formatter_includes_exception_text():
    formatter = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        record = logging.LogRecord(
            name="erp", level=logging.ERROR, pathname=__file__, lineno=1,
            msg="failed", args=(), exc_info=sys.exc_info(),
        )
    payload = json.loads(formatter.format(record))
    assert "ValueError: boom" in payload["exc"]


def test_production_uses_json_at_info():
    configure_logging(_cfg("production"))
    root = logging.getLogger()
    assert root.level == logging.INFO
    handler = next(h for h in root.handlers if getattr(h, "_erp_handler", False))
    assert isinstance(handler.formatter, JsonFormatter)


def test_local_uses_pretty_text_at_debug():
    configure_logging(_cfg("local"))
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    handler = next(h for h in root.handlers if getattr(h, "_erp_handler", False))
    assert not isinstance(handler.formatter, JsonFormatter)


def test_configure_is_idempotent():
    configure_logging(_cfg("production"))
    configure_logging(_cfg("production"))
    root = logging.getLogger()
    erp_handlers = [h for h in root.handlers if getattr(h, "_erp_handler", False)]
    assert len(erp_handlers) == 1  # no handler stacking across calls


def test_test_env_is_quiet():
    configure_logging(_cfg("test"))
    assert logging.getLogger().level == logging.WARNING
