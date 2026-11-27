"""Regression tests pinning QA (functional) findings on 2e51d15.

Every test here FAILS on the current code; each documents the expected behaviour.
"""

from datetime import date
from decimal import Decimal

import pytest

from reno_agents.calc.alerts import evaluate_unit
from reno_agents.calc.costing import line_cost
from reno_agents.calc.qa_metrics import (
    QaLine,
    QaOutcome,
    budget_deviation,
    qa_outcome,
    scope_deviation,
    timeline_deviation,
)
from reno_agents.calc.schedule import WorkCalendar
from reno_agents.config import Settings
from reno_agents.domain.enums import EscalationKind, Event, LineVerdict, QaResult, Stage
from reno_agents.domain.lifecycle import InvalidTransition, allowed_events, transition
from reno_agents.inventory.catalog import Catalog
from reno_agents.inventory.loader import load_inventory
from reno_agents.inventory.schema import InventoryItem, LaborRate

HEADER = (
    "sku,category,subcategory,item_name,brand,model,spec,unit,unit_cost,currency,supplier,"
    "lead_time_days,grade,substitution_group,coverage_per_unit,coverage_unit,waste_pct,approved,"
    "approved_until"
)
PAINT = (
    "PNT-001,Paint,Interior wall,Eggshell wall paint,Northfield,NF-200,Eggshell white,gallon,"
    "38.00,USD,Acme Supply,2,better,PAINT-INT-WALL,350,sq_ft,10,Y,2027-12-31"
)
Z = Decimal("0")


def run_qa(
    lines: "list[QaLine]",
    *,
    photo_results: "tuple[bool | None, ...] | list[bool | None]" = (True,),
    budget: Decimal = Decimal(0),
    timeline: Decimal = Decimal(0),
    threshold: Decimal = Decimal("10"),
) -> "QaOutcome":
    """Split test lines into approved-scope records (costs) and model verdicts."""
    return qa_outcome(
        approved_costs={ln.line_id: ln.approved_cost for ln in lines},
        verdicts={ln.line_id: ln.verdict for ln in lines},
        recorded_issues=[f"issue-{n}" for n in range(len(photo_results))],
        photo_results={f"issue-{n}": r for n, r in enumerate(photo_results)},
        budget=budget,
        timeline=timeline,
        threshold=threshold,
    )


DONE = [QaLine("done", Decimal("100"), LineVerdict.DONE_AS_SPECIFIED)]


# M1: strict ">" threshold is applied after rounding to 2 dp, so 10.004% is not "over 10%".
def test_qa_budget_over_ten_percent_by_fraction_is_flagged():
    actual, approved = Decimal("11000.40"), Decimal("10000")  # +10.004%
    o = run_qa(DONE, budget=budget_deviation(actual, approved))
    assert o.result is QaResult.FLAGGED  # actual: PASS (budget_deviation -> 10.00)


def test_qa_budget_and_overspend_alert_agree_on_same_numbers():
    actual, approved = Decimal("11000.40"), Decimal("10000")
    d = date(2026, 12, 1)
    alerted = evaluate_unit(
        "u",
        today=d,
        planned_finish=d,
        projected_finish=d,
        approved_budget=approved,
        projected_spend=actual,
        blocked_since={},
    )
    assert [e.kind for e in alerted] == [EscalationKind.OVERSPEND]  # alert fires (unrounded)
    qa = run_qa(DONE, budget=budget_deviation(actual, approved))
    assert "budget" in qa.flags  # actual: () -- QA says within 10%


def test_qa_scope_over_ten_percent_by_fraction_is_flagged():
    lines = [
        QaLine("a", Decimal("10004"), LineVerdict.MISSING),
        QaLine("b", Decimal("89996"), LineVerdict.DONE_AS_SPECIFIED),
    ]  # 10.004%
    o = run_qa(lines)
    assert o.result is QaResult.FLAGGED  # actual: PASS


# M2: planned duration counts the start day even when it is not a workday.
def test_timeline_duration_ignores_non_working_start_day():
    cal = WorkCalendar()
    sat, mon = date(2026, 11, 28), date(2026, 11, 30)
    # Approved Saturday, planned 1 working day (Mon), finished 1 working day late (Tue).
    assert timeline_deviation(sat, mon, date(2026, 12, 1), cal) == timeline_deviation(
        mon, mon, date(2026, 12, 1), cal
    )  # actual: 50.00 vs 100.00


# M3: procurement-needed line accepts a negative measured quantity -> negative labor.
def test_procurement_line_rejects_negative_quantity():
    lab = LaborRate.model_validate(
        dict(
            task_code="L",
            category="Paint",
            task_name="p",
            unit="sq_ft",
            rate="1.25",
            currency="USD",
            typical_hours_per_unit="0.02",
            trade="paint",
        )
    )
    with pytest.raises(ValueError):
        line_cost(Decimal("-5"), None, lab, estimate=Decimal("100"))  # actual: total 93.75


# L1: non-enum verdicts silently miscount (not_verifiable string counted as verifiable).
def test_scope_deviation_with_string_verdicts_matches_enum():
    as_enum = [
        QaLine("a", Decimal("100"), LineVerdict.MISSING),
        QaLine("b", Decimal("900"), LineVerdict.NOT_VERIFIABLE),
    ]
    as_str = [QaLine("a", Decimal("100"), "missing"), QaLine("b", Decimal("900"), "not_verifiable")]  # type: ignore[arg-type]
    assert scope_deviation(as_str) == scope_deviation(as_enum)  # actual: 10.00 vs 100.00


# L2: lifecycle accepts str stage/event for valid moves but crashes / disagrees otherwise.
def test_allowed_events_agrees_with_transition_for_str_stage():
    assert transition("draft", "assessor_run") is Stage.ASSESSED  # type: ignore[arg-type]
    assert Event.ASSESSOR_RUN in allowed_events("draft")  # type: ignore[arg-type]  # actual: empty


def test_invalid_transition_with_str_raises_invalid_transition():
    with pytest.raises(InvalidTransition):  # actual: AttributeError 'str' has no 'value'
        transition("draft", "qa_run")  # type: ignore[arg-type]


# L3: settings accept values that make the rules meaningless.
@pytest.mark.parametrize(
    "key,value",
    [
        ("RENO_APPROVAL_THRESHOLD", "-1"),
        ("RENO_HOURS_PER_DAY", "0"),
        ("RENO_SLIP_ALERT_DAYS", "-3"),
        ("RENO_LOW_CONFIDENCE_THRESHOLD", "5"),
    ],
)
def test_settings_reject_out_of_range(monkeypatch, key, value):
    from pydantic import ValidationError

    monkeypatch.setenv(key, value)
    with pytest.raises(ValidationError):
        Settings()


# L4: Catalog.groups() is case-sensitive while pick()/search() are not.
def test_groups_and_pick_agree_on_group_membership():
    def mk(sku: str, group: str) -> InventoryItem:
        row = PAINT.replace("PNT-001", sku).replace("PAINT-INT-WALL", group)
        return load_inventory(f"{HEADER}\n{row}\n", currency="USD").items[0]

    cat = Catalog([mk("A", "G1"), mk("B", "g1"), mk("C", "G1")])
    today = date(2026, 11, 27)
    p = cat.pick("G1", "better", today)  # type: ignore[arg-type]
    assert p is not None
    picked = 1 + len(p.fallbacks)
    assert max(len(v) for v in cat.groups(today).values()) == picked  # actual: 2 vs 3


# L5: "anything else malformed is a row error, never a silent guess" (plan Decisions).
@pytest.mark.parametrize(
    "old,new,field",
    [
        ("2027-12-31", "20271231", "approved_until"),
        ("2027-12-31", "2027-W52-5", "approved_until"),
        (",2,better", ",1_0,better", "lead_time_days"),
    ],
)
def test_non_spec_formats_are_row_errors(old, new, field):
    r = load_inventory(f"{HEADER}\n{PAINT.replace(old, new)}\n", currency="USD")
    assert r.items == [] and r.errors[0].field == field  # actual: loads silently


# L6: a valid row is refused as a "duplicate" of an earlier row that was itself rejected.
def test_valid_row_not_rejected_as_duplicate_of_invalid_row():
    bad = PAINT.replace("38.00", "bad")
    r = load_inventory(f"{HEADER}\n{bad}\n{PAINT}\n", currency="USD")
    assert [i.sku for i in r.items] == ["PNT-001"]  # actual: [] (row 3 flagged duplicate)


# L7: Decimal NaN leaks decimal.InvalidOperation instead of the module's own errors.
def test_nan_estimate_is_value_error():
    with pytest.raises(ValueError):
        line_cost(Decimal("1"), None, None, estimate=Decimal("NaN"))
