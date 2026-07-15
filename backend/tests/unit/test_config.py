"""Config loading + env precedence (docs/ENVIRONMENTS.md §1) and the RBAC Level enum."""

from __future__ import annotations

from app.core.config import Settings
from app.shared.enums import Level

# _env_file=None keeps these tests hermetic (no accidental .env pickup).


def _settings(**kwargs) -> Settings:
    kwargs.setdefault("jwt_secret", "test-secret")
    return Settings(_env_file=None, **kwargs)


def test_defaults(monkeypatch):
    for var in ("ERP_CONTROL_DB_NAME", "ERP_TENANT_DB_PREFIX", "ERP_ACCESS_TOKEN_TTL_MIN"):
        monkeypatch.delenv(var, raising=False)
    cfg = _settings()
    assert cfg.control_db_name == "erp_control"
    assert cfg.tenant_db_prefix == "erp_tenant_"
    assert cfg.access_token_ttl_min == 30
    assert cfg.admin_token_audience == "erp-admin"
    assert cfg.client_token_audience == "erp-client"


def test_env_vars_override_defaults(monkeypatch):
    monkeypatch.setenv("ERP_ACCESS_TOKEN_TTL_MIN", "7")
    monkeypatch.setenv("ERP_CONTROL_DB_NAME", "erp_control_other")
    cfg = _settings()
    assert cfg.access_token_ttl_min == 7
    assert cfg.control_db_name == "erp_control_other"


def test_docs_enabled_per_environment():
    assert _settings(env="local").docs_enabled is True
    assert _settings(env="test").docs_enabled is True
    assert _settings(env="production").docs_enabled is False


def test_level_ordering():
    assert Level.NONE < Level.VIEW < Level.READ < Level.WRITE
    # the RBAC guard is a `>=` check
    assert Level.WRITE >= Level.READ
    assert not (Level.VIEW >= Level.READ)
