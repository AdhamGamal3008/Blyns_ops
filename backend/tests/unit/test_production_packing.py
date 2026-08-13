"""Production Phase 4 unit guards (docs/PRODUCTION_MODULE_PLAN.md §Phase 4):
the protection spec derives from the WO's material, and the dispatch vehicle from
the staged load. Pure functions — no DB.
"""

from __future__ import annotations

from app.modules.production.service import _protection_for, _suggest_vehicle


def test_protection_spec_by_material():
    # case-insensitive, substring match against the seeded material specs
    panel = _protection_for("Panel")
    assert panel["type"] == "pallet"
    assert panel["moisture_barrier"] is True

    glass = _protection_for("glass")
    assert glass["moisture_barrier"] is False
    assert "fragile" in glass["handling"]


def test_protection_spec_defaults_when_unknown():
    for category in (None, "", "unobtanium"):
        spec = _protection_for(category)
        assert spec["type"] == "carton"
        assert spec["moisture_barrier"] is False


def test_vehicle_scales_with_load():
    assert _suggest_vehicle(10) == "van"
    assert _suggest_vehicle(20) == "van"            # band ceiling is inclusive
    assert _suggest_vehicle(50) == "3.5t truck"
    assert _suggest_vehicle(150) == "7.5t truck"
    assert _suggest_vehicle(500) == "articulated lorry"
