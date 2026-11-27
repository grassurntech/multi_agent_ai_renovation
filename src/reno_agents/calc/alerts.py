"""Escalation rules and dedup (design §5.3).

A unit is escalated to its PM when its projected finish slips more than ``slip_alert_days``
calendar days past plan, projected spend exceeds the approved budget by more than
``overspend_alert_pct``, or a task has been blocked more than ``blocked_alert_days`` days.
The same escalation is re-sent only when it gets worse, so PMs do not learn to ignore alerts:

- slip / overspend are keyed per unit and re-sent when the magnitude grows. When an approved
  change request re-baselines the plan, the caller clears the unit's sent slip/overspend entries.
- blocked is keyed per blocking episode (task id + date it became blocked) and sent once per
  episode: a task blocked again later is a new escalation, a task still blocked is not re-sent.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from reno_agents.domain.enums import EscalationKind

UNIT_KEY = "unit"
_TENTH = Decimal("0.1")


@dataclass(frozen=True)
class Escalation:
    unit_id: str
    kind: EscalationKind
    key: str  # "unit" for slip / overspend; "<task id>@<blocked since>" for blocked
    magnitude: Decimal  # days for slip / blocked, percent over budget for overspend
    message: str


def evaluate_unit(
    unit_id: str,
    *,
    today: date,
    planned_finish: date,
    projected_finish: date,
    approved_budget: Decimal,
    projected_spend: Decimal,
    blocked_since: Mapping[str, date],
    slip_alert_days: int = 7,
    overspend_alert_pct: Decimal = Decimal("10"),
    blocked_alert_days: int = 2,
) -> list[Escalation]:
    """Every escalation that applies to one unit right now (before dedup)."""
    out: list[Escalation] = []

    slip = (projected_finish - planned_finish).days
    if slip > slip_alert_days:
        out.append(
            Escalation(
                unit_id,
                EscalationKind.SLIP,
                UNIT_KEY,
                Decimal(slip),
                f"Projected finish {projected_finish.isoformat()} is {slip} days past the "
                f"planned {planned_finish.isoformat()}.",
            )
        )

    if approved_budget > 0:
        try:
            over_pct = (projected_spend - approved_budget) / approved_budget * 100
            over = over_pct > overspend_alert_pct
            shown = over_pct.quantize(_TENTH, rounding=ROUND_HALF_UP) if over else over_pct
        except ArithmeticError as exc:  # absurd inputs (e.g. NaN, 1E+30 over 0.01)
            raise ValueError(f"overspend cannot be computed: {exc!r}") from None
        if over:
            out.append(
                Escalation(
                    unit_id,
                    EscalationKind.OVERSPEND,
                    UNIT_KEY,
                    shown,
                    f"Projected spend {projected_spend} is {shown}% over the approved budget "
                    f"{approved_budget}.",
                )
            )

    for task_id in sorted(blocked_since):
        days = (today - blocked_since[task_id]).days
        if days > blocked_alert_days:
            out.append(
                Escalation(
                    unit_id,
                    EscalationKind.BLOCKED,
                    f"{task_id}@{blocked_since[task_id].isoformat()}",
                    Decimal(days),
                    f"Task {task_id} has been blocked for {days} days.",
                )
            )
    return out


def filter_new(
    candidates: Iterable[Escalation],
    last_sent: Mapping[tuple[str, EscalationKind, str], Decimal],
) -> list[Escalation]:
    """Keep escalations never sent before; re-send slip / overspend only when worse."""
    out = []
    for e in candidates:
        previous = last_sent.get((e.unit_id, e.kind, e.key))
        if previous is None or (e.kind is not EscalationKind.BLOCKED and e.magnitude > previous):
            out.append(e)
    return out
