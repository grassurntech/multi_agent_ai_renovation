from datetime import date

from reno_agents.domain.enums import Grade
from reno_agents.inventory.catalog import Catalog
from reno_agents.inventory.schema import InventoryItem

TODAY = date(2026, 11, 27)


def make(
    sku: str,
    grade: str,
    lead: int,
    cost: str,
    approved: bool = True,
    until: date = date(2027, 12, 31),
    group: str = "G",
    category: str = "Paint",
) -> InventoryItem:
    return InventoryItem.model_validate(
        {
            "sku": sku,
            "category": category,
            "subcategory": "Interior wall",
            "item_name": f"Item {sku}",
            "brand": "Northfield",
            "model": f"M-{sku}",
            "spec": "test",
            "unit": "gallon",
            "unit_cost": cost,
            "currency": "USD",
            "supplier": "Acme Supply",
            "lead_time_days": lead,
            "grade": grade,
            "substitution_group": group,
            "coverage_per_unit": "350",
            "coverage_unit": "sq_ft",
            "waste_pct": "10",
            "approved": approved,
            "approved_until": until,
        }
    )


def test_primary_matches_preferred_grade_then_fallbacks_by_closeness() -> None:
    cat = Catalog(
        [
            make("A", "good", 3, "30"),
            make("B", "better", 2, "38"),
            make("C", "best", 4, "52"),
            make("D", "better", 5, "35"),
        ]
    )
    p = cat.pick("G", Grade.BETTER, TODAY)
    assert p is not None
    assert p.primary.sku == "B" and [f.sku for f in p.fallbacks] == ["D", "A"]
    assert p.fallback_shortfall == 0


def test_expired_and_unapproved_never_picked() -> None:
    cat = Catalog(
        [
            make("A", "better", 1, "10", until=date(2026, 11, 26)),
            make("B", "better", 1, "10", approved=False),
            make("C", "good", 9, "99"),
        ]
    )
    p = cat.pick("G", Grade.BETTER, TODAY)
    assert p is not None
    assert p.primary.sku == "C" and p.fallbacks == () and p.fallback_shortfall == 2


def test_approved_until_today_is_still_active() -> None:
    cat = Catalog([make("A", "better", 1, "10", until=TODAY)])
    assert cat.pick("G", Grade.BETTER, TODAY) is not None


def test_unknown_group_returns_none() -> None:
    assert Catalog([]).pick("NOPE", Grade.BETTER, TODAY) is None


def test_group_with_only_inactive_items_returns_none() -> None:
    cat = Catalog([make("A", "better", 1, "10", approved=False)])
    assert cat.pick("G", Grade.BETTER, TODAY) is None


def test_tie_broken_by_sku_for_determinism() -> None:
    cat = Catalog([make("Z", "better", 1, "10"), make("Y", "better", 1, "10")])
    p = cat.pick("G", Grade.BETTER, TODAY)
    assert p is not None and p.primary.sku == "Y"


def test_search_filters_active_case_insensitive() -> None:
    cat = Catalog(
        [
            make("A", "good", 1, "10", category="Paint"),
            make("B", "best", 1, "10", category="Flooring", group="F"),
            make("C", "good", 1, "10", approved=False),
        ]
    )
    assert [i.sku for i in cat.search(TODAY, category="paint")] == ["A"]
    assert [i.sku for i in cat.search(TODAY, substitution_group="f", grade=Grade.BEST)] == ["B"]
    assert {i.sku for i in cat.search(TODAY)} == {"A", "B"}


def test_groups_hold_only_active_items() -> None:
    cat = Catalog([make("A", "good", 1, "10"), make("B", "good", 1, "10", approved=False)])
    assert {k: [i.sku for i in v] for k, v in cat.groups(TODAY).items()} == {"G": ["A"]}
