"""Quantities, line costs, tier totals and approval rules (design §3, §5.2).

The Planner picks the item and the measured quantity; this module does every number after that.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from reno_agents.calc.money import to_money
from reno_agents.domain.enums import Tier
from reno_agents.inventory.schema import InventoryItem, LaborRate

_HUNDRED = Decimal("100")
_ZERO = Decimal("0")


class MissingEstimate(Exception):
    """A "procurement needed" line has no PM cost estimate, so it cannot be costed."""


@dataclass(frozen=True)
class LineCost:
    purchase_qty: int | None  # None for a "procurement needed" line
    materials: Decimal
    labor: Decimal
    total: Decimal


def purchase_quantity(measured: Decimal, coverage_per_unit: Decimal, waste_pct: Decimal) -> int:
    """Purchase units = ceil(measured / coverage * (1 + waste/100)).

    Computed as ``measured * (100 + waste) / (coverage * 100)`` so an exact whole number is not
    nudged over it by a repeating decimal.
    """
    if measured <= 0:
        raise ValueError("measured quantity must be greater than 0")
    if coverage_per_unit <= 0:
        raise ValueError("coverage_per_unit must be greater than 0")
    if waste_pct < 0:
        raise ValueError("waste_pct cannot be negative")
    units = measured * (_HUNDRED + waste_pct) / (coverage_per_unit * _HUNDRED)
    return int(units.to_integral_value(rounding=ROUND_CEILING))


def line_cost(
    measured_qty: Decimal,
    item: InventoryItem | None,
    labor: LaborRate | None,
    estimate: Decimal | None = None,
) -> LineCost:
    """Materials + labor for one scope line.

    With an item: materials = purchase units x unit cost. Without one ("procurement needed"),
    the PM's ``estimate`` stands in for materials and is required.
    Labor = rate x measured quantity (rate is per unit of work), or 0 with no labor rate.
    """
    labor_cost = to_money(labor.rate * measured_qty) if labor is not None else to_money(_ZERO)
    if item is None:
        if estimate is None:
            raise MissingEstimate("a procurement-needed line needs a PM cost estimate")
        if estimate < 0:
            raise ValueError("estimate cannot be negative")
        materials = to_money(estimate)
        return LineCost(None, materials, labor_cost, to_money(materials + labor_cost))
    qty = purchase_quantity(measured_qty, item.coverage_per_unit, item.waste_pct)
    materials = to_money(item.unit_cost * qty)
    return LineCost(qty, materials, labor_cost, to_money(materials + labor_cost))


def tier_totals(lines: Iterable[tuple[Tier, LineCost]]) -> dict[Tier, Decimal]:
    """Sum of line totals per tier; every tier is present, zero when it has no lines."""
    totals = {tier: _ZERO for tier in (Tier.HIGH, Tier.MEDIUM, Tier.LOW)}
    for tier, cost in lines:
        totals[tier] += cost.total
    return {tier: to_money(value) for tier, value in totals.items()}


def needs_asset_manager_approval(total: Decimal, threshold: Decimal) -> bool:
    """Above the threshold needs the asset manager; exactly at it does not."""
    return total > threshold


def change_request_needs_asset_manager(
    original_total: Decimal, new_total: Decimal, threshold: Decimal, pct: Decimal
) -> bool:
    """Re-approval if the new total is over the threshold, or the cumulative increase over the
    originally approved total is more than ``pct`` percent of it."""
    return new_total > threshold or (new_total - original_total) > original_total * pct / _HUNDRED
