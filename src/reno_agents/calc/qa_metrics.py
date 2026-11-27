"""The four QA deviation checks and the overall QA result (design §5.4).

Verdicts are judged against the PM-recorded *installed* item. An approved swap may arrive as
``done_as_specified`` or ``done_different_item``; neither is a deviation. ``installed_mismatch``
(what is visible is not the recorded item), ``partial`` and ``missing`` are. "Not verifiable"
lines are left out of the percentages and force "Needs evidence" unless a metric is already over
the threshold.

Percentages are rounded *up* to the next hundredth, so a value just over the threshold (10.004%)
is never rounded down onto it and passed.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal

from reno_agents.calc.schedule import WorkCalendar
from reno_agents.domain.enums import LineVerdict, QaResult

_HUNDRED = Decimal("100")
_PCT = Decimal("0.01")
_DEVIATING = frozenset({LineVerdict.PARTIAL, LineVerdict.MISSING, LineVerdict.INSTALLED_MISMATCH})
_ONE_DAY = timedelta(days=1)


def _pct(part: Decimal, whole: Decimal) -> Decimal:
    return (part / whole * _HUNDRED).quantize(_PCT, rounding=ROUND_CEILING)


def _finite(name: str, value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal")
    return value


@dataclass(frozen=True)
class QaLine:
    line_id: str
    approved_cost: Decimal
    verdict: LineVerdict

    def __post_init__(self) -> None:
        # Model output may arrive as plain strings; coerce or refuse rather than miscount.
        object.__setattr__(self, "verdict", LineVerdict(self.verdict))
        cost = _finite("approved_cost", self.approved_cost)
        if cost < 0:
            raise ValueError("approved_cost cannot be negative")


@dataclass(frozen=True)
class QaOutcome:
    result: QaResult
    flags: tuple[str, ...]  # metrics over the threshold: "scope", "photo", "budget", "timeline"
    not_verifiable: int


def scope_deviation(lines: Sequence[QaLine]) -> Decimal:
    """Cost of lines not done as specified / cost of all verifiable lines, as a percent."""
    verifiable = [ln for ln in lines if ln.verdict is not LineVerdict.NOT_VERIFIABLE]
    whole = sum((ln.approved_cost for ln in verifiable), Decimal(0))
    if whole == 0:
        return Decimal("0")
    part = sum((ln.approved_cost for ln in verifiable if ln.verdict in _DEVIATING), Decimal(0))
    return _pct(part, whole)


def photo_deviation(resolved_as_planned: Sequence[bool | None]) -> Decimal:
    """Percent of verifiable issues not resolved as planned; ``None`` = not verifiable."""
    verifiable = [r for r in resolved_as_planned if r is not None]
    if not verifiable:
        return Decimal("0")
    return _pct(Decimal(sum(1 for r in verifiable if not r)), Decimal(len(verifiable)))


def budget_deviation(actual: Decimal, approved: Decimal) -> Decimal:
    """(actual - approved) / approved, as a percent. Negative means under budget."""
    _finite("actual", actual)
    if _finite("approved", approved) <= 0:
        raise ValueError("approved budget must be greater than 0")
    return _pct(actual - approved, approved)


def timeline_deviation(
    planned_start: date, planned_finish: date, actual_finish: date, calendar: WorkCalendar
) -> Decimal:
    """Working days late / planned duration in working days (start and finish inclusive)."""
    if planned_finish < planned_start:
        raise ValueError("planned finish is before planned start")
    late = calendar.working_days_between(planned_finish, actual_finish)
    # Workdays in [planned_start, planned_finish]; a weekend start date does not count.
    duration = max(1, calendar.working_days_between(planned_start - _ONE_DAY, planned_finish))
    return _pct(Decimal(late), Decimal(duration))


def qa_outcome(
    *,
    scope: Decimal,
    photo: Decimal,
    budget: Decimal,
    timeline: Decimal,
    not_verifiable: int,
    threshold: Decimal = Decimal("10"),
) -> QaOutcome:
    """Flagged if any metric is over the threshold; else Needs evidence if any line could not be
    verified; else Pass. The QA reviewer still makes the final call."""
    if not_verifiable < 0:
        raise ValueError("not_verifiable cannot be negative")
    metrics = (("scope", scope), ("photo", photo), ("budget", budget), ("timeline", timeline))
    for name, value in (*metrics, ("threshold", threshold)):
        _finite(name, value)
    flags = tuple(name for name, value in metrics if value > threshold)
    if flags:
        result = QaResult.FLAGGED
    elif not_verifiable:
        result = QaResult.NEEDS_EVIDENCE
    else:
        result = QaResult.PASS_
    return QaOutcome(result, flags, not_verifiable)
