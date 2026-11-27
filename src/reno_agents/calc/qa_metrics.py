"""The four QA deviation checks and the overall QA result (design §5.4).

Verdicts are judged against the PM-recorded *installed* item. An approved swap may arrive as
``done_as_specified`` or ``done_different_item``; neither is a deviation. ``installed_mismatch``
(what is visible is not the recorded item), ``partial`` and ``missing`` are. "Not verifiable"
lines and photo comparisons are left out of the percentages and force "Needs evidence" unless a
metric is already over the threshold.

The QA agent supplies only judgements. ``qa_outcome`` takes line costs from the approved-scope
records and requires exactly one verdict per approved line, and exactly one photo result per
recorded issue, so a model cannot add, drop, repeat or re-price lines or issues.
Percentages are compared unrounded and shown rounded *up* to the next hundredth, so a value just
over the threshold is never shown as exactly on it.
"""

import unicodedata
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal

from reno_agents.calc.schedule import WorkCalendar
from reno_agents.domain.enums import LineVerdict, QaResult

_HUNDRED = Decimal("100")
_PCT = Decimal("0.01")
_ZERO = Decimal("0")
_DEVIATING = frozenset({LineVerdict.PARTIAL, LineVerdict.MISSING, LineVerdict.INSTALLED_MISMATCH})
_ONE_DAY = timedelta(days=1)


def _raw_pct(part: Decimal, whole: Decimal) -> Decimal:
    try:
        return part / whole * _HUNDRED
    except ArithmeticError as exc:
        raise ValueError(f"percentage cannot be computed: {exc!r}") from None


def _round_pct(value: Decimal) -> Decimal:
    if value == 0:
        return _ZERO
    try:
        return value.quantize(_PCT, rounding=ROUND_CEILING)
    except ArithmeticError as exc:  # too large to hold at 2 decimal places
        raise ValueError(f"percentage is out of range: {exc!r}") from None


def _finite(name: str, value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal")
    return value


def _sum(values: Sequence[Decimal]) -> Decimal:
    try:
        return sum(values, _ZERO)
    except ArithmeticError as exc:
        raise ValueError(f"costs are too large to add up: {exc!r}") from None


def _id_key(line_id: str) -> str:
    """Comparison key for ids: ignores case, surrounding spaces, width and invisible characters."""
    text = unicodedata.normalize("NFKC", line_id)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return text.strip().casefold()


@dataclass(frozen=True)
class QaLine:
    line_id: str
    approved_cost: Decimal
    verdict: LineVerdict

    def __post_init__(self) -> None:
        if not isinstance(self.line_id, str) or not _id_key(self.line_id):
            raise ValueError("line_id must be non-empty text")
        # Model output may arrive as plain strings; coerce or refuse rather than miscount.
        object.__setattr__(self, "verdict", LineVerdict(self.verdict))
        if _finite("approved_cost", self.approved_cost) < 0:
            raise ValueError("approved_cost cannot be negative")


@dataclass(frozen=True)
class QaOutcome:
    result: QaResult
    flags: tuple[str, ...]  # metrics over the threshold: "scope", "photo", "budget", "timeline"
    not_verifiable: int  # approved lines judged "not verifiable from media"
    scope: Decimal  # scope deviation percent, as shown
    photo: Decimal  # photo deviation percent, as shown
    photos_not_verifiable: int  # before/after comparisons that could not be judged


def judge_lines(
    approved_costs: Mapping[str, Decimal], verdicts: Mapping[str, LineVerdict | str]
) -> list[QaLine]:
    """Pair each approved line (cost from the records) with its single QA verdict.

    Raises ``ValueError`` if there are no approved lines, or the verdict ids are not exactly the
    approved ids (a line left out, an unknown line, or a near-copy of an id).
    """
    if not approved_costs:
        raise ValueError("there are no approved lines to judge")
    missing = sorted(set(approved_costs) - set(verdicts))
    unknown = sorted(set(verdicts) - set(approved_costs))
    if missing or unknown:
        problems = []
        if missing:
            problems.append(f"no verdict for approved lines: {', '.join(missing)}")
        if unknown:
            problems.append(f"verdicts for lines not in the approved scope: {unknown!r}")
        raise ValueError("; ".join(problems))
    lines = [QaLine(i, approved_costs[i], LineVerdict(verdicts[i])) for i in approved_costs]
    _check_unique(lines)
    return lines


def _check_unique(lines: Sequence[QaLine]) -> None:
    _check_unique_ids([ln.line_id for ln in lines], "approved line")


def _check_unique_ids(ids: Sequence[str], what: str) -> None:
    keys = [_id_key(i) for i in ids]
    if len(set(keys)) != len(keys):
        raise ValueError(f"each {what} may be judged only once (duplicate id)")


def judge_photos(
    recorded_issues: Collection[str], photo_results: Mapping[str, bool | None]
) -> list[bool | None]:
    """One photo result per recorded issue, in recorded order.

    Raises ``TypeError`` if ``photo_results`` is not a mapping, and ``ValueError`` if there are
    no recorded issues or the result ids are not exactly the recorded issue ids.
    """
    if not isinstance(photo_results, Mapping):
        raise TypeError("photo_results must map each recorded issue id to True, False or None")
    issues = list(recorded_issues)
    if not issues:
        raise ValueError("there are no recorded issues to compare before and after")
    if any(not isinstance(i, str) or not _id_key(i) for i in issues):
        raise ValueError("issue ids must be non-empty text")
    _check_unique_ids(issues, "recorded issue")
    missing = sorted(set(issues) - set(photo_results))
    unknown = sorted(set(photo_results) - set(issues), key=repr)
    if missing or unknown:
        problems = []
        if missing:
            problems.append(f"no photo result for recorded issues: {', '.join(missing)}")
        if unknown:
            problems.append(f"photo results for issues that were not recorded: {unknown!r}")
        raise ValueError("; ".join(problems))
    return [photo_results[i] for i in issues]


def _scope_raw(lines: Sequence[QaLine]) -> Decimal:
    _check_unique(lines)
    verifiable = [ln for ln in lines if ln.verdict is not LineVerdict.NOT_VERIFIABLE]
    deviating = [ln for ln in verifiable if ln.verdict in _DEVIATING]
    whole = _sum([ln.approved_cost for ln in verifiable])
    if whole == 0:
        # Zero-cost lines: fall back to counting lines so missing work is still seen.
        return _raw_pct(Decimal(len(deviating)), Decimal(len(verifiable))) if verifiable else _ZERO
    return _raw_pct(_sum([ln.approved_cost for ln in deviating]), whole)


def scope_deviation(lines: Sequence[QaLine]) -> Decimal:
    """Cost of deviating lines / cost of all verifiable lines, as a percent (rounded up).

    Each approved line must appear once; repeating a line would dilute the figure.
    """
    return _round_pct(_scope_raw(lines))


def _photo_raw(resolved_as_planned: Sequence[bool | None]) -> Decimal:
    for r in resolved_as_planned:
        if r is not None and not isinstance(r, bool):
            raise TypeError(f"photo results must be True, False or None, got {r!r}")
    verifiable = [r for r in resolved_as_planned if r is not None]
    if not verifiable:
        return _ZERO
    return _raw_pct(Decimal(sum(1 for r in verifiable if not r)), Decimal(len(verifiable)))


def photo_deviation(resolved_as_planned: Sequence[bool | None]) -> Decimal:
    """Percent of verifiable issues not resolved as planned; ``None`` = not verifiable."""
    return _round_pct(_photo_raw(resolved_as_planned))


def budget_deviation(actual: Decimal, approved: Decimal) -> Decimal:
    """(actual - approved) / approved, as a percent. Negative means under budget."""
    if _finite("actual", actual) < 0:
        raise ValueError("actual spend cannot be negative")
    if _finite("approved", approved) <= 0:
        raise ValueError("approved budget must be greater than 0")
    try:
        over = actual - approved
    except ArithmeticError as exc:
        raise ValueError(f"budget deviation cannot be computed: {exc!r}") from None
    return _round_pct(_raw_pct(over, approved))


def timeline_deviation(
    planned_start: date, planned_finish: date, actual_finish: date, calendar: WorkCalendar
) -> Decimal:
    """Working days late / planned duration in working days (start and finish inclusive)."""
    if planned_finish < planned_start:
        raise ValueError("planned finish is before planned start")
    late = calendar.working_days_between(planned_finish, actual_finish)
    # Workdays in [planned_start, planned_finish]; a weekend start date does not count.
    duration = max(1, calendar.working_days_between(planned_start - _ONE_DAY, planned_finish))
    return _round_pct(_raw_pct(Decimal(late), Decimal(duration)))


def qa_outcome(
    *,
    approved_costs: Mapping[str, Decimal],
    verdicts: Mapping[str, LineVerdict | str],
    recorded_issues: Collection[str],
    photo_results: Mapping[str, bool | None],
    budget: Decimal,
    timeline: Decimal,
    threshold: Decimal = Decimal("10"),
) -> QaOutcome:
    """Flagged if any metric is over the threshold; else Needs evidence if any line or photo
    comparison could not be verified; else Pass. The QA reviewer still makes the final call.

    From the records: ``approved_costs`` (line id -> approved cost) and ``recorded_issues`` (the
    issue ids behind the approved scope). From the QA agent: ``verdicts`` (line id -> verdict)
    and ``photo_results`` (issue id -> resolved as planned, or None if not verifiable).
    ``budget`` and ``timeline`` are ``budget_deviation`` / ``timeline_deviation`` over the actuals.
    """
    lines = judge_lines(approved_costs, verdicts)
    photos = judge_photos(recorded_issues, photo_results)
    scope_raw = _scope_raw(lines)
    photo_raw = _photo_raw(photos)
    for name, value in (("budget", budget), ("timeline", timeline), ("threshold", threshold)):
        _finite(name, value)
    metrics = (
        ("scope", scope_raw),
        ("photo", photo_raw),
        ("budget", budget),
        ("timeline", timeline),
    )
    flags = tuple(name for name, value in metrics if value > threshold)
    not_verifiable = sum(1 for ln in lines if ln.verdict is LineVerdict.NOT_VERIFIABLE)
    photos_not_verifiable = sum(1 for r in photos if r is None)
    if flags:
        result = QaResult.FLAGGED
    elif not_verifiable or photos_not_verifiable:
        result = QaResult.NEEDS_EVIDENCE
    else:
        result = QaResult.PASS_
    return QaOutcome(
        result,
        flags,
        not_verifiable,
        _round_pct(scope_raw),
        _round_pct(photo_raw),
        photos_not_verifiable,
    )
