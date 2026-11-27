"""Regression tests for the final whole-branch review findings (Important 1-3)."""

from datetime import date
from decimal import Decimal

import pytest

from reno_agents.calc.alerts import evaluate_unit, filter_new
from reno_agents.calc.costing import line_cost
from reno_agents.calc.qa_metrics import QaLine, scope_deviation
from reno_agents.domain.enums import EscalationKind, LineVerdict


@pytest.mark.parametrize("qty", [Decimal("-5000"), Decimal("0"), Decimal("NaN"), Decimal("Inf")])
def test_procurement_line_rejects_bad_measured_quantity(qty: Decimal) -> None:
    with pytest.raises(ValueError):
        line_cost(qty, None, None, estimate=Decimal("100"))


def _blocked(today: date, since: date) -> list:  # type: ignore[type-arg]
    return evaluate_unit(
        "u1",
        today=today,
        planned_finish=today,
        projected_finish=today,
        approved_budget=Decimal("100"),
        projected_spend=Decimal("100"),
        blocked_since={"t1": since},
    )


def test_new_blocked_episode_is_escalated_even_if_shorter() -> None:
    first = _blocked(date(2026, 12, 11), date(2026, 12, 1))  # 10 days
    sent = {(e.unit_id, e.kind, e.key): e.magnitude for e in first}
    second = _blocked(date(2026, 12, 20), date(2026, 12, 16))  # unblocked, blocked again: 4 days
    assert [e.kind for e in filter_new(second, sent)] == [EscalationKind.BLOCKED]


def test_same_blocked_episode_is_not_resent_every_day() -> None:
    day3 = _blocked(date(2026, 12, 4), date(2026, 12, 1))
    sent = {(e.unit_id, e.kind, e.key): e.magnitude for e in day3}
    assert filter_new(_blocked(date(2026, 12, 5), date(2026, 12, 1)), sent) == []


def test_approved_swap_reported_as_different_item_is_not_a_deviation() -> None:
    # Spec §5.4: an approved swap is "done with a different item" and is not a deviation.
    lines = [
        QaLine("a", Decimal("500"), LineVerdict.DONE_DIFFERENT_ITEM),
        QaLine("b", Decimal("500"), LineVerdict.DONE_AS_SPECIFIED),
    ]
    assert scope_deviation(lines) == Decimal("0")


def test_installed_item_not_matching_what_is_visible_is_a_deviation() -> None:
    lines = [
        QaLine("a", Decimal("500"), LineVerdict.INSTALLED_MISMATCH),
        QaLine("b", Decimal("500"), LineVerdict.DONE_AS_SPECIFIED),
    ]
    assert scope_deviation(lines) == Decimal("50.00")
