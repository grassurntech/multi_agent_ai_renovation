"""Working-day calendar and trade-ordered schedule (design §5.3).

The clock starts on the approval date. Trade steps run in sequence; tasks in the same step run
in parallel; a task cannot start before its materials arrive. Durations are in working days.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal

# Trade steps run in this order; tasks within one step run in parallel.
TRADE_ORDER: tuple[str, ...] = (
    "demo",
    "rough_in",
    "repairs",
    "paint",
    "flooring",
    "fixtures_appliances",
    "hardware",
    "clean",
)

# A single task longer than this many working days (about 14 years) is a data error, not a plan.
MAX_TASK_WORKING_DAYS = 3650
_ONE_DAY = timedelta(days=1)


class WorkCalendar:
    """Workdays are ``date.weekday()`` numbers (0 = Monday); holidays are never worked."""

    def __init__(
        self,
        workdays: frozenset[int] = frozenset({0, 1, 2, 3, 4}),
        holidays: frozenset[date] = frozenset(),
    ) -> None:
        if not workdays:
            raise ValueError("a calendar needs at least one workday")
        if any(not 0 <= d <= 6 for d in workdays):
            raise ValueError("workdays must be 0 (Mon) to 6 (Sun)")
        self.workdays = frozenset(workdays)
        self.holidays = frozenset(holidays)

    def is_workday(self, d: date) -> bool:
        return d.weekday() in self.workdays and d not in self.holidays

    def next_workday(self, d: date) -> date:
        """``d`` if it is a workday, else the next one."""
        # Bounded: each holiday can cost at most a week, plus one more week to reach a workday.
        for _ in range(7 * (len(self.holidays) + 1) + 1):
            if self.is_workday(d):
                return d
            d += _ONE_DAY
        raise ValueError("no workday found; check the workdays and holidays settings")

    def add_working_days(self, start: date, days: int) -> date:
        """Finish date of a ``days``-long task starting on ``start`` (which counts as day 1)."""
        if days < 1:
            raise ValueError("a task lasts at least 1 working day")
        if days > MAX_TASK_WORKING_DAYS:
            raise ValueError(f"a task cannot last more than {MAX_TASK_WORKING_DAYS} working days")
        d = self.next_workday(start)
        for _ in range(days - 1):
            d = self.next_workday(d + _ONE_DAY)
        return d

    def working_days_between(self, a: date, b: date) -> int:
        """Number of workdays in ``(a, b]``; negative (``-count in (b, a]``) if ``b < a``."""
        if b < a:
            return -self.working_days_between(b, a)
        span = (b - a).days
        weeks, extra = divmod(span, 7)
        count = weeks * len(self.workdays)
        count += sum((a + timedelta(n)).weekday() in self.workdays for n in range(1, extra + 1))
        count -= sum(1 for h in self.holidays if a < h <= b and h.weekday() in self.workdays)
        return count


@dataclass(frozen=True)
class ScheduleTask:
    task_id: str
    trade: str
    hours: Decimal
    materials_ready: date | None = None


@dataclass(frozen=True)
class Schedule:
    tasks: dict[str, tuple[date, date]]  # task_id -> (start, finish), both inclusive
    finish: date


def _duration_days(hours: Decimal, hours_per_day: Decimal) -> int:
    try:
        days = (hours / hours_per_day).to_integral_value(rounding=ROUND_CEILING)
    except ArithmeticError as exc:  # decimal Overflow / InvalidOperation
        raise ValueError(f"task duration cannot be computed: {exc!r}") from None
    if days > MAX_TASK_WORKING_DAYS:
        raise ValueError(f"a task cannot last more than {MAX_TASK_WORKING_DAYS} working days")
    return max(1, int(days))


def build_schedule(
    tasks: Sequence[ScheduleTask],
    start: date,
    calendar: WorkCalendar,
    hours_per_day: Decimal = Decimal("8"),
) -> Schedule:
    """Plan start/finish for every task, starting no earlier than ``start``."""
    if not tasks:
        raise ValueError("a schedule needs at least one task")
    if not hours_per_day.is_finite() or not Decimal("0.01") <= hours_per_day <= 24:
        raise ValueError("hours_per_day must be between 0.01 and 24")
    ids = [t.task_id for t in tasks]
    if len(set(ids)) != len(ids):
        raise ValueError("task ids must be unique")
    for t in tasks:
        if t.trade not in TRADE_ORDER:
            raise ValueError(f"unknown trade {t.trade!r}; expected one of {', '.join(TRADE_ORDER)}")
        if not t.hours.is_finite() or t.hours < 0:
            raise ValueError(f"task {t.task_id!r} has invalid hours {t.hours}")

    try:
        return _plan(tasks, start, calendar, hours_per_day)
    except OverflowError:
        raise ValueError("schedule runs past the last representable date") from None


def _plan(
    tasks: Sequence[ScheduleTask], start: date, calendar: WorkCalendar, hours_per_day: Decimal
) -> Schedule:
    planned: dict[str, tuple[date, date]] = {}
    cursor = calendar.next_workday(start)
    for trade in TRADE_ORDER:
        step = [t for t in tasks if t.trade == trade]
        if not step:
            continue
        step_finish = cursor
        for t in step:
            begin = cursor
            if t.materials_ready is not None:
                begin = max(cursor, calendar.next_workday(t.materials_ready))
            end = calendar.add_working_days(begin, _duration_days(t.hours, hours_per_day))
            planned[t.task_id] = (begin, end)
            step_finish = max(step_finish, end)
        cursor = calendar.next_workday(step_finish + _ONE_DAY)
    return Schedule(planned, max(end for _, end in planned.values()))


def project_finish(
    remaining: Sequence[ScheduleTask],
    today: date,
    approval_date: date,
    last_done: date | None,
    calendar: WorkCalendar,
    hours_per_day: Decimal = Decimal("8"),
) -> date:
    """Projected finish: re-run the schedule for unfinished work from today (never before
    approval). With nothing left, the finish is the last completed day (or today)."""
    if not remaining:
        return last_done or today
    return build_schedule(remaining, max(today, approval_date), calendar, hours_per_day).finish
