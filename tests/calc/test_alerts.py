from datetime import date
from decimal import Decimal
from typing import Any

from reno_agents.calc.alerts import Escalation, evaluate_unit, filter_new
from reno_agents.domain.enums import EscalationKind

D = date(2026, 12, 10)
base: dict[str, Any] = dict(
    today=D,
    planned_finish=date(2026, 12, 1),
    projected_finish=date(2026, 12, 1),
    approved_budget=Decimal("10000"),
    projected_spend=Decimal("10000"),
    blocked_since={},
)


def run(**changes: Any) -> list[Escalation]:
    return evaluate_unit("u1", **{**base, **changes})


def test_on_plan_unit_has_no_escalations() -> None:
    assert run() == []


def test_slip_of_exactly_seven_days_is_not_escalated() -> None:
    assert run(projected_finish=date(2026, 12, 8)) == []


def test_slip_of_eight_days_escalates() -> None:
    [e] = run(projected_finish=date(2026, 12, 9))
    assert e.kind is EscalationKind.SLIP and e.magnitude == Decimal("8") and e.key == "unit"
    assert e.unit_id == "u1" and e.message


def test_overspend_boundary() -> None:
    at = run(projected_spend=Decimal("11000"))
    over = run(projected_spend=Decimal("11000.01"))
    assert at == [] and over[0].kind is EscalationKind.OVERSPEND
    assert over[0].magnitude == Decimal("10.0")


def test_overspend_magnitude_rounded_to_one_decimal() -> None:
    [e] = run(projected_spend=Decimal("11255"))
    assert e.magnitude == Decimal("12.6")


def test_zero_budget_does_not_crash() -> None:
    assert run(approved_budget=Decimal("0")) == []


def test_blocked_more_than_two_days() -> None:
    es = run(blocked_since={"t1": date(2026, 12, 8), "t2": date(2026, 12, 7)})
    assert [(e.kind, e.key, e.magnitude) for e in es] == [
        (EscalationKind.BLOCKED, "t2@2026-12-07", 3)
    ]


def test_blocked_tasks_reported_in_stable_order() -> None:
    es = run(blocked_since={"t9": date(2026, 12, 1), "t1": date(2026, 12, 1)})
    assert [e.key for e in es] == ["t1@2026-12-01", "t9@2026-12-01"]


def test_thresholds_are_settings() -> None:
    assert run(projected_finish=date(2026, 12, 4), slip_alert_days=2)[0].kind is EscalationKind.SLIP


def test_dedup_only_resends_when_worse() -> None:
    e = Escalation("u1", EscalationKind.SLIP, "unit", Decimal("8"), "")
    assert filter_new([e], {("u1", EscalationKind.SLIP, "unit"): Decimal("8")}) == []
    assert filter_new([e], {("u1", EscalationKind.SLIP, "unit"): Decimal("7")}) == [e]
    assert filter_new([e], {}) == [e]
