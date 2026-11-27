import itertools
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


_ids = itertools.count(1)


def L(cost: str, v: LineVerdict) -> QaLine:
    return QaLine(f"line-{next(_ids)}", Decimal(cost), v)


def test_scope_deviation_excludes_unverifiable_from_both_sides() -> None:
    lines = [L("900", V.DONE_AS_SPECIFIED), L("100", V.MISSING), L("5000", V.NOT_VERIFIABLE)]
    assert scope_deviation(lines) == Decimal("10.00")


def test_installed_mismatch_counts_as_deviation() -> None:
    lines = [L("500", V.INSTALLED_MISMATCH), L("500", V.DONE_AS_SPECIFIED)]
    assert scope_deviation(lines) == Decimal("50.00")


def test_partial_counts_as_deviation_and_result_rounds_up_to_two_decimals() -> None:
    lines = [L("1", V.PARTIAL), L("2", V.DONE_AS_SPECIFIED)]
    assert scope_deviation(lines) == Decimal("33.34")


def test_all_unverifiable_gives_zero_and_needs_evidence() -> None:
    lines = [L("100", V.NOT_VERIFIABLE)]
    assert scope_deviation(lines) == Decimal("0")
    o = qa_outcome(lines=lines, photo=photo_deviation([None]), budget=Z, timeline=Z)
    assert o.result is QaResult.NEEDS_EVIDENCE and o.not_verifiable == 1 and o.scope == Z


def test_scope_deviation_of_no_lines_is_zero() -> None:
    assert scope_deviation([]) == Decimal("0")


def test_photo_deviation_counts_unresolved_among_verifiable() -> None:
    assert photo_deviation([True, False, None, True]) == Decimal("33.34")
    assert photo_deviation([]) == Decimal("0")


def test_exactly_ten_percent_passes_just_over_flags() -> None:
    at = [L("10", V.MISSING), L("90", V.DONE_AS_SPECIFIED)]
    assert qa_outcome(lines=at, photo=Z, budget=Z, timeline=Z).result is QaResult.PASS_
    over = [L("1001", V.MISSING), L("8999", V.DONE_AS_SPECIFIED), L("5", V.NOT_VERIFIABLE)]
    o = qa_outcome(lines=over, photo=Z, budget=Z, timeline=Z)
    assert o.result is QaResult.FLAGGED and o.flags == ("scope",) and o.scope == Decimal("10.01")


def test_flags_listed_in_fixed_order() -> None:
    eleven = Decimal("11")
    lines = [L("11", V.MISSING), L("89", V.DONE_AS_SPECIFIED)]
    o = qa_outcome(lines=lines, photo=eleven, budget=eleven, timeline=eleven)
    assert o.flags == ("scope", "photo", "budget", "timeline")


def test_threshold_is_a_setting() -> None:
    lines = [L("6", V.MISSING), L("94", V.DONE_AS_SPECIFIED)]
    o = qa_outcome(lines=lines, photo=Z, budget=Z, timeline=Z, threshold=Decimal("5"))
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
    o = qa_outcome(lines=[], photo=Z, budget=Decimal("-20"), timeline=Z)
    assert o.result is QaResult.PASS_


def test_duplicate_line_ids_refused() -> None:
    with pytest.raises(ValueError):
        scope_deviation(
            [QaLine("a", Decimal("1"), V.MISSING), QaLine("a", Decimal("1"), V.MISSING)]
        )


def test_photo_results_must_be_bool_or_none() -> None:
    with pytest.raises(TypeError):
        photo_deviation(["false"])  # type: ignore[list-item]
