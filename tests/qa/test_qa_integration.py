"""QA (functional) integration and boundary tests. Expected to pass on 2e51d15."""

import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from reno_agents.calc.alerts import evaluate_unit, filter_new
from reno_agents.calc.costing import (
    change_request_needs_asset_manager,
    line_cost,
    purchase_quantity,
    tier_totals,
)
from reno_agents.calc.money import parse_money, to_money
from reno_agents.calc.qa_metrics import (
    QaLine,
    budget_deviation,
    photo_deviation,
    qa_outcome,
    timeline_deviation,
)
from reno_agents.calc.schedule import (
    TRADE_ORDER,
    ScheduleTask,
    WorkCalendar,
    build_schedule,
    project_finish,
)
from reno_agents.config import Settings
from reno_agents.domain.enums import (
    EscalationKind,
    Event,
    Grade,
    LineVerdict,
    QaResult,
    Severity,
    Stage,
    Tier,
)
from reno_agents.domain.lifecycle import TransitionContext, transition
from reno_agents.domain.tiers import apply_floor, load_tier_rules
from reno_agents.inventory.catalog import Catalog
from reno_agents.inventory.loader import load_inventory, load_labor_rates

ROOT = Path(__file__).resolve().parents[2]
TODAY = date(2026, 11, 27)
SETTINGS = Settings()


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    r = load_inventory((ROOT / "data/sample/inventory.csv").read_text(), currency="USD")
    assert r.ok
    return Catalog(r.items)


@pytest.fixture(scope="module")
def labor() -> dict[str, object]:
    r = load_labor_rates((ROOT / "data/sample/labor_rates.csv").read_text(), currency="USD")
    assert r.ok
    return {x.task_code: x for x in r.items}


# --- Integration: CSV -> pick -> cost -> tiers -> lifecycle ---------------------------------


def _scope(catalog, labor):
    rules = load_tier_rules(ROOT / "config/tier_rules.toml")
    spec = [
        # (group, labor code, measured qty, proposed tier, severity)
        ("PAINT-INT-WALL", "L-PNT-WALL", Decimal("420"), Tier.HIGH, Severity.MODERATE),
        ("ELEC-PANEL", "L-ELEC-PANEL", Decimal("1"), Tier.LOW, Severity.SYSTEM_LEVEL),
        ("APPL-DISHWASHER", "L-APPL-INSTALL", Decimal("1"), Tier.MEDIUM, Severity.MAJOR),
        ("ELEC-SWITCH", "L-ELEC-DEVICE", Decimal("1"), Tier.LOW, Severity.MINOR),
    ]
    lines = []
    for group, code, qty, proposed, sev in spec:
        pick = catalog.pick(group, SETTINGS.preferred_grade, TODAY)
        assert pick is not None and pick.primary.grade is Grade.BETTER
        assert pick.fallback_shortfall == 0
        tier = apply_floor(proposed, sev, rules)
        lines.append((tier, line_cost(qty, pick.primary, labor[code])))
    return lines


def test_sample_scope_end_to_end(catalog, labor):
    lines = _scope(catalog, labor)
    # Paint: PNT-002 38.00 x ceil(420/350*1.1)=2 -> 76.00 + 420*1.25=525.00
    assert lines[0][1].total == Decimal("601.00")
    # System-level panel is floored to High even though proposed Low.
    assert lines[1][0] is Tier.HIGH
    totals = tier_totals(lines)
    assert set(totals) == {Tier.HIGH, Tier.MEDIUM, Tier.LOW}
    grand = sum(totals.values(), Decimal(0))
    assert grand == sum((c.total for _, c in lines), Decimal(0))
    stage = transition(
        Stage.PLANNED,
        Event.SCOPE_SUBMITTED,
        TransitionContext(grand, SETTINGS.approval_threshold),
    )
    assert stage is (Stage.APPROVED if grand <= Decimal("15000") else Stage.AWAITING_AM_APPROVAL)


def test_procurement_line_estimate_pushes_scope_over_threshold(catalog, labor):
    lines = _scope(catalog, labor)
    base = sum(tier_totals(lines).values(), Decimal(0))
    gap = Decimal("15000.00") - base
    at = lines + [(Tier.HIGH, line_cost(Decimal("1"), None, None, estimate=gap))]
    over = lines + [
        (Tier.HIGH, line_cost(Decimal("1"), None, None, estimate=gap + Decimal("0.01")))
    ]
    t = SETTINGS.approval_threshold
    s_at = sum(tier_totals(at).values(), Decimal(0))
    s_over = sum(tier_totals(over).values(), Decimal(0))
    assert s_at == Decimal("15000.00")
    ctx_at = TransitionContext(s_at, t)
    ctx_over = TransitionContext(s_over, t)
    assert transition(Stage.PLANNED, Event.SCOPE_SUBMITTED, ctx_at) is Stage.APPROVED
    assert transition(Stage.PLANNED, Event.SCOPE_SUBMITTED, ctx_over) is Stage.AWAITING_AM_APPROVAL


def test_pick_is_deterministic_regardless_of_input_order(catalog):
    items = list(catalog.active(TODAY))
    rnd = random.Random(1)
    first = None
    for _ in range(5):
        rnd.shuffle(items)
        p = Catalog(items).pick("APPL-DISHWASHER", Grade.BETTER, TODAY)
        sig = (p.primary.sku, tuple(f.sku for f in p.fallbacks))
        first = first or sig
        assert sig == first


def test_expiry_day_after_drops_item(catalog):
    # Every sample item expires 2027-12-31 or earlier; the day after, nothing is pickable.
    assert catalog.pick("PAINT-INT-WALL", Grade.BETTER, date(2028, 1, 1)) is None
    assert catalog.pick("PAINT-INT-WALL", Grade.BETTER, date(2027, 12, 31)) is not None


def test_schedule_from_sample_labor_then_escalation(labor):
    cal = WorkCalendar(holidays=frozenset({date(2026, 12, 25)}))
    tasks = [
        ScheduleTask("paint", "paint", labor["L-PNT-WALL"].typical_hours_per_unit * 420),
        ScheduleTask("panel", "rough_in", Decimal("10"), materials_ready=date(2026, 12, 2)),
        ScheduleTask("clean", "clean", Decimal("2")),
    ]
    approval = date(2026, 11, 28)  # Saturday
    plan = build_schedule(tasks, approval, cal)
    assert plan.tasks["panel"] == (date(2026, 12, 2), date(2026, 12, 3))  # 10h -> 2 days
    assert plan.tasks["paint"] == (date(2026, 12, 4), date(2026, 12, 7))  # 8.4h -> 2 days
    assert plan.tasks["clean"] == (date(2026, 12, 8), date(2026, 12, 8))
    # Later: panel delivery slips to 12-23; projection from today.
    late = [
        ScheduleTask("panel", "rough_in", Decimal("10"), materials_ready=date(2026, 12, 23)),
        *tasks[::2],
    ]
    proj = project_finish(late, date(2026, 12, 1), approval, None, cal)
    # panel 12-23..12-24, paint 12-28 (25th holiday, weekend)..12-29, clean 12-30
    assert proj == date(2026, 12, 30)
    es = evaluate_unit(
        "u1",
        today=date(2026, 12, 1),
        planned_finish=plan.finish,
        projected_finish=proj,
        approved_budget=Decimal("10000"),
        projected_spend=Decimal("10000"),
        blocked_since={},
    )
    assert [(e.kind, e.magnitude) for e in es] == [(EscalationKind.SLIP, Decimal("22"))]
    assert filter_new(es, {("u1", EscalationKind.SLIP, "unit"): Decimal("22")}) == []


def test_qa_pipeline_needs_evidence_then_flagged():
    cal = WorkCalendar()
    lines = [
        QaLine("a", Decimal("900"), LineVerdict.DONE_AS_SPECIFIED),
        QaLine("b", Decimal("100"), LineVerdict.PARTIAL),
        QaLine("c", Decimal("50"), LineVerdict.NOT_VERIFIABLE),
    ]
    o = qa_outcome(
        lines=lines,
        photo=photo_deviation([True, True, None]),
        budget=budget_deviation(Decimal("10500"), Decimal("10000")),
        timeline=timeline_deviation(
            date(2026, 11, 30), date(2026, 12, 11), date(2026, 12, 11), cal
        ),
    )
    assert o.result is QaResult.NEEDS_EVIDENCE and o.flags == () and o.not_verifiable == 1
    o2 = qa_outcome(
        lines=lines,
        photo=photo_deviation([False, True, True, True, True, True, True, True, True]),  # 11.11
        budget=Decimal("0"),
        timeline=timeline_deviation(
            date(2026, 11, 30), date(2026, 12, 11), date(2026, 12, 14), cal
        ),
    )
    assert o2.result is QaResult.FLAGGED and o2.flags == ("photo",)  # timeline exactly 10.00


# --- Unit boundaries ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "x,expected",
    [("0.005", "0.01"), ("0.004999", "0.00"), ("-0.005", "-0.01"), ("2.675", "2.68")],
)
def test_to_money_half_up(x, expected):
    assert to_money(Decimal(x)) == Decimal(expected)


@pytest.mark.parametrize(
    "bad", ["", " ", "$", "1,23", "12,3456", "1e3", "NaN", "inf", "--1", "$$1"]
)
def test_parse_money_rejects(bad):
    with pytest.raises(ValueError):
        parse_money(bad)


def test_purchase_quantity_boundaries():
    assert purchase_quantity(Decimal("1"), Decimal("1"), Decimal("0")) == 1
    assert purchase_quantity(Decimal("0.0001"), Decimal("350"), Decimal("0")) == 1
    assert purchase_quantity(Decimal("318.18"), Decimal("350"), Decimal("10")) == 1  # 0.99998
    assert purchase_quantity(Decimal("318.19"), Decimal("350"), Decimal("10")) == 2
    assert purchase_quantity(Decimal("1"), Decimal("1"), Decimal("100")) == 2
    with pytest.raises(ValueError):
        purchase_quantity(Decimal("1"), Decimal("0"), Decimal("0"))
    with pytest.raises(ValueError):
        purchase_quantity(Decimal("1"), Decimal("1"), Decimal("-1"))


@pytest.mark.parametrize(
    "orig,new,expected",
    [
        ("14000", "15000", False),  # at threshold, +7.1%
        ("0", "0.01", True),  # any increase over a zero baseline
        ("10000.01", "11000.01", False),  # +9.99999%
        ("10000", "9000", False),
    ],
)
def test_change_request_more_boundaries(orig, new, expected):
    got = change_request_needs_asset_manager(
        Decimal(orig), Decimal(new), Decimal("15000"), Decimal("10")
    )
    assert got is expected


def test_blocked_exactly_two_days_not_escalated_three_is():
    d = date(2026, 12, 10)
    es = evaluate_unit(
        "u",
        today=d,
        planned_finish=d,
        projected_finish=d,
        approved_budget=Decimal("1"),
        projected_spend=Decimal("1"),
        blocked_since={"a": d - timedelta(days=2), "b": d - timedelta(days=3), "c": d},
    )
    # Blocked keys carry the episode start (task id @ blocked-since date).
    assert [e.key for e in es] == [f"b@{(d - timedelta(days=3)).isoformat()}"]


def test_settings_workdays_and_holidays_flow_into_calendar(monkeypatch):
    monkeypatch.setenv("RENO_WORKDAYS", "0, 1,2,3,4,5")
    monkeypatch.setenv("RENO_HOLIDAYS", " 2026-11-28 ")
    s = Settings()
    cal = WorkCalendar(s.workdays, s.holidays)
    assert cal.next_workday(date(2026, 11, 28)) == date(2026, 11, 30)
    assert cal.is_workday(date(2026, 12, 5))


def test_trade_order_matches_spec():
    assert TRADE_ORDER == (
        "demo",
        "rough_in",
        "repairs",
        "paint",
        "flooring",
        "fixtures_appliances",
        "hardware",
        "clean",
    )


# --- Property tests for the calendar vs a naive reference -----------------------------------


def _naive_between(cal, a, b):
    if b < a:
        return -_naive_between(cal, b, a)
    return sum(cal.is_workday(a + timedelta(n)) for n in range(1, (b - a).days + 1))


def _naive_add(cal, start, days):
    d = start
    while not cal.is_workday(d):
        d += timedelta(1)
    left = days - 1
    while left:
        d += timedelta(1)
        if cal.is_workday(d):
            left -= 1
    return d


@pytest.mark.parametrize("seed", range(20))
def test_calendar_matches_naive(seed):
    rnd = random.Random(seed)
    wd = frozenset(rnd.sample(range(7), rnd.randint(1, 7)))
    base = date(2026, 1, 1)
    hol = frozenset(base + timedelta(rnd.randint(0, 400)) for _ in range(rnd.randint(0, 30)))
    cal = WorkCalendar(wd, hol)
    for _ in range(50):
        a = base + timedelta(rnd.randint(0, 365))
        b = base + timedelta(rnd.randint(0, 365))
        assert cal.working_days_between(a, b) == _naive_between(cal, a, b)
        n = rnd.randint(1, 40)
        assert cal.add_working_days(a, n) == _naive_add(cal, a, n)
