"""Pure engine logic (docs/modules/PROJECT_MANAGEMENT.md §4-§6, §8): gate
scoring against seeded thresholds and the stage-state decision — no DB."""

from __future__ import annotations

from app.modules.projects.engines import (
    evaluate_gate_result,
    evaluate_inspection,
    evaluate_measurement,
    next_status,
)

# --- measurement gates (§8) ---------------------------------------------------

# Thresholds mirror stage_definitions.json so the unit tests exercise the same
# shapes the seed ships.
MC_RULE = {"threshold": {"min": 6, "max": 9, "unit": "%"}}
DEVIATION_RULE = {
    "threshold": {"max_deviation_mm": 3.0},
    "severe_threshold": {"max_deviation_mm": 6.0},
}
RH_RULE = {"threshold": {"max_rh_pct": 75}}
REVEAL_RULE = {"threshold": {"target_mm": 3, "tolerance_mm": 1}}
SITE_RULE = {"threshold": {"site_defined": True}}


def _readings(*values: float) -> list[dict]:
    return [{"location": f"p{i}", "value": v} for i, v in enumerate(values)]


def test_moisture_window_passes_inside_and_fails_outside():
    passed, severe, _ = evaluate_measurement(MC_RULE, _readings(6.5, 7.2, 8.9))
    assert passed and not severe

    # acceptance #4: installation cannot pass while MC is outside 6-9%
    for bad in (_readings(5.9), _readings(9.1), _readings(7.0, 10.2)):
        passed, severe, _ = evaluate_measurement(MC_RULE, bad)
        assert not passed and not severe


def test_deviation_upper_bound_and_severe_tier():
    passed, severe, _ = evaluate_measurement(DEVIATION_RULE, _readings(1.0, 2.9))
    assert passed and not severe

    # fail but recoverable: over 3mm, under the severe 6mm
    passed, severe, _ = evaluate_measurement(DEVIATION_RULE, _readings(4.5))
    assert not passed and not severe

    # acceptance #3: beyond severe drives on_hold
    passed, severe, _ = evaluate_measurement(DEVIATION_RULE, _readings(2.0, 7.1))
    assert not passed and severe


def test_concrete_rh_single_limit():
    assert evaluate_measurement(RH_RULE, _readings(70))[0] is True
    passed, severe, _ = evaluate_measurement(RH_RULE, _readings(80))
    assert not passed
    assert not severe  # no severe_threshold configured on this rule


def test_reveal_target_with_tolerance():
    assert evaluate_measurement(REVEAL_RULE, _readings(2.5, 3.0, 3.9))[0] is True
    # every reading must sit inside target±tolerance
    assert evaluate_measurement(REVEAL_RULE, _readings(3.0, 4.5))[0] is False


def test_site_defined_window_passes_on_logged_evidence():
    # §8 ambient_rh_temp_log: the window is per-site, so the log itself is the gate
    assert evaluate_measurement(SITE_RULE, _readings(55))[0] is True


def test_no_readings_never_passes():
    for rule in (MC_RULE, DEVIATION_RULE, RH_RULE, REVEAL_RULE, SITE_RULE):
        passed, severe, explanation = evaluate_measurement(rule, [])
        assert not passed and not severe
        assert "No readings" in explanation


# --- inspection gates (§8 checklists) ----------------------------------------

CHECKLIST_RULE = {
    "type": "inspection",
    "checklist": ["level", "plumb", "spacing", "anchorage"],
}


def _checked(**items: bool) -> list[dict]:
    return [{"item": k, "passed": v} for k, v in items.items()]


def test_inspection_needs_every_item_answered_and_passed():
    passed, _, _ = evaluate_inspection(
        CHECKLIST_RULE, _checked(level=True, plumb=True, spacing=True, anchorage=True)
    )
    assert passed

    # one failing item fails the gate
    passed, _, explanation = evaluate_inspection(
        CHECKLIST_RULE, _checked(level=True, plumb=False, spacing=True, anchorage=True)
    )
    assert not passed and "plumb" in explanation

    # an unanswered item is not a pass
    passed, _, explanation = evaluate_inspection(
        CHECKLIST_RULE, _checked(level=True, plumb=True)
    )
    assert not passed and "unanswered" in explanation

    # a result row with no item name answers nothing
    passed, _, _ = evaluate_inspection(CHECKLIST_RULE, [{"passed": True}])
    assert not passed


def test_evaluate_gate_result_dispatches_on_rule_type():
    ok_inspection = {"checklist_results": _checked(
        level=True, plumb=True, spacing=True, anchorage=True)}
    assert evaluate_gate_result(CHECKLIST_RULE, ok_inspection)[0] is True

    measurement_rule = {"type": "measurement", **MC_RULE}
    assert evaluate_gate_result(measurement_rule, {"readings": _readings(7)})[0] is True


# --- stage-state decision (§4) ------------------------------------------------

def _evaluation(waiting=(), blocked=(), failures=(), severe=False) -> dict:
    return {
        "waiting_on": list(waiting),
        "blocked_by": list(blocked),
        "gate_failures": [{"gate_key": g, "reason": "…"} for g in failures],
        "severe": severe,
    }


def test_next_status_ladder():
    # clean evaluation → workable
    assert next_status(_evaluation(), "pending") == "in_progress"
    # missing docs → waiting; incomplete predecessor outranks it (§4)
    assert next_status(_evaluation(waiting=["doc:loi_or_po"]), "pending") == "waiting"
    assert next_status(
        _evaluation(waiting=["doc:x"], blocked=["stage:3"]), "in_progress"
    ) == "blocked"
    # failed quality gates alone keep the stage workable — they block approval,
    # not work (§5.2 catches them at submit)
    assert next_status(_evaluation(failures=["reveal_gap_3mm"]), "in_progress") == "in_progress"


def test_severe_breach_forces_on_hold_and_hold_is_sticky():
    assert next_status(_evaluation(severe=True), "in_progress") == "on_hold"
    # §4: on_hold clears only through report resolution, not re-evaluation
    assert next_status(_evaluation(), "on_hold") == "on_hold"
