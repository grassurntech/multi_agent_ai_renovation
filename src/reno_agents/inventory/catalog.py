"""Approved-inventory catalog: search and primary + 2 fallback picks (design §5.2).

Only items with ``approved = Y`` and ``approved_until >= today`` are ever returned. The Planner
uses this as its only source of items, so it can never recommend an unapproved one.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from reno_agents.domain.enums import Grade, grade_rank
from reno_agents.inventory.schema import InventoryItem

FALLBACKS_WANTED = 2


@dataclass(frozen=True)
class Pick:
    """Primary item for a line plus up to two fallbacks from the same substitution group."""

    primary: InventoryItem
    fallbacks: tuple[InventoryItem, ...]
    fallback_shortfall: int  # how many of the 2 wanted fallbacks are missing; the UI must show it


def _same(a: str, b: str) -> bool:
    return a.casefold() == b.casefold()


class Catalog:
    """Read-only view over a loaded inventory."""

    def __init__(self, items: Iterable[InventoryItem]) -> None:
        self._items = tuple(items)

    def active(self, today: date) -> list[InventoryItem]:
        """Items that are approved and not past ``approved_until`` (that day still counts)."""
        return [i for i in self._items if i.approved and i.approved_until >= today]

    def search(
        self,
        today: date,
        *,
        category: str | None = None,
        subcategory: str | None = None,
        substitution_group: str | None = None,
        grade: Grade | None = None,
    ) -> list[InventoryItem]:
        """Active items matching every given filter (strings compared case-insensitively)."""
        return [
            i
            for i in self.active(today)
            if (category is None or _same(i.category, category))
            and (subcategory is None or _same(i.subcategory, subcategory))
            and (substitution_group is None or _same(i.substitution_group, substitution_group))
            and (grade is None or i.grade is grade)
        ]

    def groups(self, today: date) -> dict[str, list[InventoryItem]]:
        """Active items keyed by substitution group."""
        out: dict[str, list[InventoryItem]] = {}
        for item in self.active(today):
            out.setdefault(item.substitution_group, []).append(item)
        return out

    def pick(self, substitution_group: str, preferred_grade: Grade, today: date) -> Pick | None:
        """Primary + 2 fallbacks ordered by grade closeness, lead time, cost, then SKU.

        Returns ``None`` when the group has no active item: the line is "procurement needed".
        """
        candidates = self.search(today, substitution_group=substitution_group)
        if not candidates:
            return None
        want = grade_rank(preferred_grade)

        def order(item: InventoryItem) -> tuple[int, int, Decimal, str]:
            return (
                abs(grade_rank(item.grade) - want),
                item.lead_time_days,
                item.unit_cost,
                item.sku,
            )

        ranked = sorted(candidates, key=order)
        fallbacks = tuple(ranked[1 : 1 + FALLBACKS_WANTED])
        return Pick(ranked[0], fallbacks, FALLBACKS_WANTED - len(fallbacks))
