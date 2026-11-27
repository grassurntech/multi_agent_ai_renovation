from datetime import date, timedelta
from decimal import Decimal

import pytest

from reno_agents.calc.schedule import ScheduleTask, WorkCalendar, build_schedule, project_finish

CAL = WorkCalendar(holidays=frozenset({date(2026, 12, 25)}))
MON = date(2026, 11, 30)


def test_add_working_days_skips_weekend() -> None:
    assert CAL.add_working_days(date(2026, 11, 26), 3) == MON  # Thu, Fri, Mon


def test_next_workday_and_is_workday() -> None:
    assert CAL.next_workday(date(2026, 11, 28)) == MON
    assert CAL.next_workday(MON) == MON
    assert not CAL.is_workday(date(2026, 12, 25)) and CAL.is_workday(date(2026, 12, 24))


def test_add_working_days_needs_at_least_one_day() -> None:
    with pytest.raises(ValueError):
        CAL.add_working_days(MON, 0)


def test_approval_on_saturday_starts_monday() -> None:
    s = build_schedule([ScheduleTask("t1", "paint", Decimal("8"))], date(2026, 11, 28), CAL)
    assert s.tasks["t1"] == (MON, MON)


def test_trades_are_sequential_same_trade_parallel() -> None:
    s = build_schedule(
        [
            ScheduleTask("a", "repairs", Decimal("16")),
            ScheduleTask("b", "repairs", Decimal("8")),
            ScheduleTask("c", "paint", Decimal("8")),
        ],
        MON,
        CAL,
    )
    assert s.tasks["a"] == (MON, date(2026, 12, 1)) and s.tasks["b"][0] == MON
    assert s.tasks["c"] == (date(2026, 12, 2), date(2026, 12, 2)) and s.finish == date(2026, 12, 2)


def test_trade_order_wins_over_input_order() -> None:
    s = build_schedule(
        [ScheduleTask("p", "paint", Decimal("8")), ScheduleTask("d", "demo", Decimal("8"))],
        MON,
        CAL,
    )
    assert s.tasks["d"] == (MON, MON) and s.tasks["p"][0] == date(2026, 12, 1)


def test_materials_gate_start_but_past_dates_do_not_pull_earlier() -> None:
    late = build_schedule(
        [ScheduleTask("t", "paint", Decimal("8"), materials_ready=date(2026, 12, 3))], MON, CAL
    )
    past = build_schedule(
        [ScheduleTask("t", "paint", Decimal("8"), materials_ready=date(2026, 11, 1))], MON, CAL
    )
    assert late.tasks["t"][0] == date(2026, 12, 3) and past.tasks["t"][0] == MON


def test_materials_ready_on_weekend_starts_next_workday() -> None:
    s = build_schedule(
        [ScheduleTask("t", "paint", Decimal("8"), materials_ready=date(2026, 12, 5))], MON, CAL
    )
    assert s.tasks["t"][0] == date(2026, 12, 7)


def test_holiday_skipped() -> None:
    s = build_schedule([ScheduleTask("t", "paint", Decimal("16"))], date(2026, 12, 24), CAL)
    assert s.tasks["t"] == (date(2026, 12, 24), date(2026, 12, 28))


def test_zero_hour_task_still_takes_a_day() -> None:
    s = build_schedule([ScheduleTask("t", "clean", Decimal("0"))], MON, CAL)
    assert s.tasks["t"] == (MON, MON)


def test_unknown_trade_rejected() -> None:
    with pytest.raises(ValueError):
        build_schedule([ScheduleTask("t", "magic", Decimal("1"))], MON, CAL)


@pytest.mark.parametrize(
    "tasks",
    [
        [],
        [ScheduleTask("t", "paint", Decimal("-1"))],
        [ScheduleTask("t", "paint", Decimal("8")), ScheduleTask("t", "clean", Decimal("8"))],
    ],
)
def test_bad_task_lists_rejected(tasks: list[ScheduleTask]) -> None:
    with pytest.raises(ValueError):
        build_schedule(tasks, MON, CAL)


def test_bad_hours_per_day_rejected() -> None:
    with pytest.raises(ValueError):
        build_schedule([ScheduleTask("t", "paint", Decimal("8"))], MON, CAL, Decimal("0"))


def test_projection_with_nothing_remaining() -> None:
    assert project_finish([], date(2026, 12, 10), MON, date(2026, 12, 9), CAL) == date(2026, 12, 9)
    assert project_finish([], date(2026, 12, 10), MON, None, CAL) == date(2026, 12, 10)


def test_projection_runs_from_today_when_after_approval() -> None:
    remaining = [ScheduleTask("t", "paint", Decimal("16"))]
    assert project_finish(remaining, date(2026, 12, 10), MON, None, CAL) == date(2026, 12, 11)
    assert project_finish(remaining, date(2026, 11, 1), MON, None, CAL) == date(2026, 12, 1)


def test_working_days_between() -> None:
    assert CAL.working_days_between(date(2026, 11, 27), MON) == 1
    assert CAL.working_days_between(MON, date(2026, 11, 27)) == -1
    assert CAL.working_days_between(MON, MON) == 0
    # Dec 21 (Mon) .. Dec 28 (Mon): 22, 23, 24, 28 — the 25th is a holiday.
    assert CAL.working_days_between(date(2026, 12, 21), date(2026, 12, 28)) == 4


def test_working_days_between_matches_day_by_day_count_over_a_long_span() -> None:
    a, b = date(2026, 1, 1), date(2031, 6, 30)
    slow = sum(CAL.is_workday(a + timedelta(n)) for n in range(1, (b - a).days + 1))
    assert CAL.working_days_between(a, b) == slow


def test_calendar_rejects_bad_workdays() -> None:
    with pytest.raises(ValueError):
        WorkCalendar(workdays=frozenset())
    with pytest.raises(ValueError):
        WorkCalendar(workdays=frozenset({7}))


def test_absurd_duration_rejected_instead_of_looping() -> None:
    with pytest.raises(ValueError):
        build_schedule([ScheduleTask("t", "paint", Decimal("1e12"))], MON, CAL)


def test_next_workday_skips_several_holiday_weeks_on_a_one_day_week() -> None:
    mondays = frozenset({date(2026, 11, 30), date(2026, 12, 7), date(2026, 12, 14)})
    cal = WorkCalendar(workdays=frozenset({0}), holidays=mondays)
    assert cal.next_workday(date(2026, 11, 28)) == date(2026, 12, 21)
