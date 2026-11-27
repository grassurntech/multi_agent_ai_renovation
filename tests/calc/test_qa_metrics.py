from datetime import date
from decimal import Decimal

import pytest

from reno_agents.calc.qa_metrics import (
    QaLine,
    budget_deviation,
    photo_deviation,
    qa_outcome,
    scope_deviation,
    timeline_deviation,
)
from reno_agents.calc.schedule import WorkCalendar
from reno_agents.domain.enums import LineVerdict, QaResult

V = LineVerdict
Z = Decimal("0")


def L(cost: str, v: LineVerdict) -> QaLine:
    return QaLine("x", Decimal(cost), v)


def test_scope_deviation_excludes_unverifiable_from_both_sides() -> None:
    lines = [L("900", V.DONE_AS_SPECIFIED), L("100", V.MISSING), L("5000", V.NOT_VERIFIABLE)]
    assert scope_deviation(lines) == Decimal("10.00")


def test_different_item_counts_as_deviation() -> None:
    lines = [L("500", V.DONE_DIFFERENT_ITEM), L("500", V.DONE_AS_SPECIFIED)]
    assert scope_deviation(lines) == Decimal("50.00")


def test_partial_counts_as_deviation_and_result_is_two_decimals() -> None:
    lines = [L("1", V.PARTIAL), L("2", V.DONE_AS_SPECIFIED)]
    assert scope_deviation(lines) == Decimal("33.33")


def test_all_unverifiable_gives_zero_and_needs_evidence() -> None:
    lines = [L("100", V.NOT_VERIFIABLE)]
    assert scope_deviation(lines) == Decimal("0")
    o = qa_outcome(
        scope=Decimal("0"), photo=photo_deviation([None]), budget=Z, timeline=Z, not_verifiable=1
    )
    assert o.result is QaResult.NEEDS_EVIDENCE and o.not_verifiable == 1


def test_scope_deviation_of_no_lines_is_zero() -> None:
    assert scope_deviation([]) == Decimal("0")


def test_photo_deviation_counts_unresolved_among_verifiable() -> None:
    assert photo_deviation([True, False, None, True]) == Decimal("33.33")
    assert photo_deviation([]) == Decimal("0")


def test_exactly_ten_percent_passes_just_over_flags() -> None:
    o = qa_outcome(scope=Decimal("10"), photo=Z, budget=Z, timeline=Z, not_verifiable=0)
    assert o.result is QaResult.PASS_
    o = qa_outcome(scope=Decimal("10.01"), photo=Z, budget=Z, timeline=Z, not_verifiable=2)
    assert o.result is QaResult.FLAGGED and o.flags == ("scope",)


def test_flags_listed_in_fixed_order() -> None:
    eleven = Decimal("11")
    o = qa_outcome(scope=eleven, photo=eleven, budget=eleven, timeline=eleven, not_verifiable=0)
    assert o.flags == ("scope", "photo", "budget", "timeline")


def test_threshold_is_a_setting() -> None:
    o = qa_outcome(
        scope=Decimal("6"), photo=Z, budget=Z, timeline=Z, not_verifiable=0, threshold=Decimal("5")
    )
    assert o.result is QaResult.FLAGGED


def test_budget_deviation_and_zero_budget() -> None:
    assert budget_deviation(Decimal("11500"), Decimal("10000")) == Decimal("15.00")
    with pytest.raises(ValueError):
        budget_deviation(Decimal("1"), Decimal("0"))


def test_timeline_deviation_same_day_job() -> None:
    d = date(2026, 11, 30)
    assert timeline_deviation(d, d, date(2026, 12, 1), WorkCalendar()) == Decimal("100.00")


def test_timeline_deviation_counts_working_days() -> None:
    # Planned Mon 30 Nov - Fri 4 Dec (5 working days); finished Mon 7 Dec: 1 day late = 20%.
    got = timeline_deviation(
        date(2026, 11, 30), date(2026, 12, 4), date(2026, 12, 7), WorkCalendar()
    )
    assert got == Decimal("20.00")


def test_timeline_finish_before_start_rejected() -> None:
    with pytest.raises(ValueError):
        timeline_deviation(date(2026, 12, 4), date(2026, 11, 30), date(2026, 12, 7), WorkCalendar())


def test_under_budget_is_negative_not_flagged() -> None:
    o = qa_outcome(scope=Z, photo=Z, budget=Decimal("-20"), timeline=Z, not_verifiable=0)
    assert o.result is QaResult.PASS_
