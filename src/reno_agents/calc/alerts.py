"""Escalation rules and dedup (design §5.3).

A unit is escalated to its PM when its projected finish slips more than ``slip_alert_days``
calendar days past plan, projected spend exceeds the approved budget by more than
``overspend_alert_pct``, or a task has been blocked more than ``blocked_alert_days`` days.
The same escalation is re-sent only when it gets worse, so PMs do not learn to ignore alerts.
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
    key: str  # "unit" for slip / overspend; the task id for blocked
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
        over_pct = (projected_spend - approved_budget) / approved_budget * 100
        if over_pct > overspend_alert_pct:
            shown = over_pct.quantize(_TENTH, rounding=ROUND_HALF_UP)
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
                    task_id,
                    Decimal(days),
                    f"Task {task_id} has been blocked for {days} days.",
                )
            )
    return out


def filter_new(
    candidates: Iterable[Escalation],
    last_sent: Mapping[tuple[str, EscalationKind, str], Decimal],
) -> list[Escalation]:
    """Keep escalations never sent before, or worse than the last one sent."""
    out = []
    for e in candidates:
        previous = last_sent.get((e.unit_id, e.kind, e.key))
        if previous is None or e.magnitude > previous:
            out.append(e)
    return out
