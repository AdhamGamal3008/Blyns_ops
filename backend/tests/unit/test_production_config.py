"""Production hardening guard (docs/ENVIRONMENTS.md §4/§6): a production process
must refuse to start with a dev secret, open docs, or localhost origins."""

from __future__ import annotations

import pytest

from app.core.config import Settings, validate_for_production

STRONG_SECRET = "a" * 48  # >= 32 chars, not a known dev value


def _prod(**overrides) -> Settings:
    base = dict(
        env="production",
        jwt_secret=STRONG_SECRET,
        mongo_uri="mongodb://mongo-primary.internal:27017,mongo-2.internal:27017/?replicaSet=rs0",
        cors_origins=["https://app.acme.com"],
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_a_valid_production_config_passes():
    cfg = _prod()
    assert cfg.production_problems() == []
    assert cfg.docs_enabled is False
    validate_for_production(cfg)  # does not raise


@pytest.mark.parametrize("secret", ["", "change-me-dev-only", "dev", "short"])
def test_weak_or_dev_secret_is_rejected(secret):
    problems = _prod(jwt_secret=secret).production_problems()
    assert any("ERP_JWT_SECRET" in p for p in problems)


def test_localhost_cors_and_mongo_are_rejected():
    problems = _prod(
        cors_origins=["http://localhost:5173"],
        mongo_uri="mongodb://localhost:27017",
    ).production_problems()
    assert any("CORS origins point at localhost" in p for p in problems)
    assert any("ERP_MONGO_URI points at localhost" in p for p in problems)


def test_empty_cors_is_rejected():
    assert any("ERP_CORS_ORIGINS" in p for p in _prod(cors_origins=[]).production_problems())


def test_validate_raises_listing_every_violation():
    cfg = _prod(jwt_secret="dev", cors_origins=[], mongo_uri="mongodb://localhost:27017")
    with pytest.raises(RuntimeError) as exc:
        validate_for_production(cfg)
    message = str(exc.value)
    # all three violations surface at once, not one redeploy at a time
    assert "ERP_JWT_SECRET" in message
    assert "ERP_CORS_ORIGINS" in message
    assert "ERP_MONGO_URI" in message


def test_guard_is_a_noop_outside_production():
    # local/test may run with the dev secret and localhost freely
    cfg = Settings(_env_file=None, env="local", jwt_secret="change-me-dev-only")
    assert cfg.production_problems()  # would be unsafe IN production …
    validate_for_production(cfg)  # … but the guard only fires when env=production


def test_non_production_still_serves_docs():
    assert Settings(_env_file=None, env="local", jwt_secret="x").docs_enabled is True
    assert Settings(_env_file=None, env="test", jwt_secret="x").docs_enabled is True
