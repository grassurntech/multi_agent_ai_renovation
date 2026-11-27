"""Adversarial re-check of 1032ba3 (fixes for the 8f21e46 findings).

Every test asserts the expected *safe* behaviour, so a failing test is a finding.
"""

import decimal
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from reno_agents.calc import alerts, qa_metrics
from reno_agents.domain.enums import LineVerdict, QaResult, Severity, Tier
from reno_agents.domain.tiers import apply_floor, load_tier_rules

LOW = pytest.mark.xfail(
    strict=True, reason="Deferred Low from QA re-check of 1032ba3; see tech-debt tracker"
)

Z = Decimal(0)
ROOT = Path(__file__).resolve().parents[2]
RULES = load_tier_rules(ROOT / "config" / "tier_rules.toml")


def _outcome(**kw: object) -> qa_metrics.QaOutcome:
    base: dict[str, object] = dict(
        approved_costs={"kitchen": Decimal(100)},
        verdicts={"kitchen": "done_as_specified"},
        recorded_issues=["issue-1"],
        photo_results={"issue-1": True},
        budget=Z,
        timeline=Z,
    )
    base.update(kw)
    return qa_metrics.qa_outcome(**base)  # type: ignore[arg-type]


# --- 1. severity floor: any spelling must either raise or land at HIGH ------------------------
SAFETY_LIKE = [
    "SAFETY",
    "Safety",
    " safety",
    "safety ",
    "\tsafety\n",
    " safety",
    "　safety",
    "safety​",
    "​safety",
    "s­afety",
    "﻿safety",
    "ＳＡＦＥＴＹ",
    "ſafety",
    "safety.",
    "safety!",
    "'safety'",
    '"safety"',
    "life_safety",
    "life-safety",
    "safety_issue",
    "SAFETY_CRITICAL",
    "System-Level",
    "SYSTEM LEVEL",
    "system  level",
    "system--level",
    "system\tlevel",
    "systemlevel",
    "system.level",
    "system_level\x00",
    "Severity.SAFETY",
    "severity.system_level",
    "‮safety",
    "ѕafety",  # Cyrillic dze
    "safetý",
    "systém_level",
]
NON_STR = [
    None,
    0,
    4,
    5,
    1.0,
    b"safety",
    ["safety"],
    ("safety",),
    {"safety": 1},
    True,
    Tier.HIGH,
    LineVerdict.MISSING,
    QaResult.FLAGGED,
]


@pytest.mark.parametrize("sev", SAFETY_LIKE + NON_STR, ids=repr)
@pytest.mark.parametrize("proposed", [Tier.LOW, Tier.MEDIUM, "low", "medium"])
def test_floor_never_below_high(sev: object, proposed: object) -> None:
    try:
        tier = apply_floor(proposed, sev, RULES)  # type: ignore[arg-type]
    except ValueError:
        return
    assert tier is Tier.HIGH, f"{sev!r} -> {tier!r}"


@pytest.mark.parametrize("sev", ["minor", "moderate", "major", "MINOR", "Major "])
def test_non_floor_severity_keeps_tier(sev: str) -> None:
    assert apply_floor(Tier.LOW, sev, RULES) is Tier.LOW  # type: ignore[arg-type]


@LOW
def test_str_subclass_severity_cannot_spoof() -> None:
    class Sneaky(str):
        def __str__(self) -> str:
            return "minor"

    s = Sneaky("safety")
    try:
        tier = apply_floor(Tier.LOW, s, RULES)  # type: ignore[arg-type]
    except ValueError:
        return
    assert tier is Tier.HIGH, "a str equal to 'safety' was floored as 'minor'"


# --- floor table: the floors that guard safety/system_level must not be droppable ------------
def _rules_text(floor: str) -> str:
    body = (ROOT / "config" / "tier_rules.toml").read_text(encoding="utf-8")
    head = body.split("[severity_floor]")[0]
    return head + floor


@LOW
@pytest.mark.parametrize(
    "floor",
    [
        "",
        "[severity_floor]\n",
        '[severity_floor]\nsafety = "high"\n',
        '[severity_floor]\nsafety = "low"\nsystem_level = "low"\n',
    ],
    ids=["missing", "empty", "no-system-level", "lowered"],
)
def test_floor_table_must_keep_safety_and_system_level_at_high(tmp_path: Path, floor: str) -> None:
    p = tmp_path / "tier_rules.toml"
    p.write_text(_rules_text(floor), encoding="utf-8")
    try:
        rules = load_tier_rules(p)
    except ValueError:
        return
    assert apply_floor(Tier.LOW, Severity.SAFETY, rules) is Tier.HIGH
    assert apply_floor(Tier.LOW, Severity.SYSTEM_LEVEL, rules) is Tier.HIGH


@LOW
def test_floor_table_is_not_mutable_after_load() -> None:
    rules = load_tier_rules(ROOT / "config" / "tier_rules.toml")
    try:
        rules.severity_floor.pop(Severity.SAFETY)  # shared, "frozen" dataclass
    except (TypeError, AttributeError):
        return
    assert apply_floor(Tier.LOW, Severity.SAFETY, rules) is Tier.HIGH


@LOW
def test_floor_with_str_keyed_table() -> None:
    rules = replace(RULES, severity_floor={"SAFETY": Tier.HIGH})  # type: ignore[dict-item]
    try:
        tier = apply_floor(Tier.LOW, "safety", rules)  # type: ignore[arg-type]
    except ValueError:
        return
    assert tier is Tier.HIGH


# --- 2. recorded_swaps bypasses ---------------------------------------------------------------
@pytest.mark.parametrize(
    "swaps",
    [
        {"VANITY"},
        {"vanity "},
        {"ｖａｎｉｔｙ"},
        {"van​ity"},
        {"﻿vanity"},
        {"other-line"},
        "vanity",
        ["vanity", "ghost"],
        {"vanity": 1, "ghost": 2},
        {"faucet"},
    ],
    ids=repr,
)
def test_swap_lookalikes_never_excuse_the_line(swaps: object) -> None:
    try:
        out = _outcome(
            approved_costs={"vanity": Decimal(900), "faucet": Decimal(100)},
            verdicts={"vanity": "done_different_item", "faucet": "done_as_specified"},
            recorded_swaps=swaps,
        )
    except (ValueError, TypeError):
        return
    assert out.result is not QaResult.PASS_, f"{swaps!r} excused an unrecorded swap"


@LOW
def test_swap_generator_genuine_swap() -> None:
    # A one-shot iterable is consumed by the subset check; then the real swap is not seen.
    out = _outcome(
        approved_costs={"vanity": Decimal(900), "faucet": Decimal(100)},
        verdicts={"vanity": "done_different_item", "faucet": "done_as_specified"},
        recorded_swaps=(x for x in ["vanity"]),
    )
    assert out.result is QaResult.PASS_


def test_unhashable_verdict_value_is_valueerror() -> None:
    with pytest.raises(ValueError):
        _outcome(verdicts={"kitchen": ["missing"]})


@LOW
def test_none_recorded_swaps_is_valueerror() -> None:
    with pytest.raises(ValueError):
        _outcome(recorded_swaps=None)


# --- 3. precision independence on the alert path (fixed for qa_metrics only) ------------------
@LOW
def test_overspend_alert_independent_of_caller_precision() -> None:
    d = date(2026, 1, 5)
    ctx = decimal.getcontext().copy()
    ctx.prec = 3
    with decimal.localcontext(ctx):
        esc = alerts.evaluate_unit(
            "u1",
            today=d,
            planned_finish=d,
            projected_finish=d,
            approved_budget=Decimal("1000.00"),
            projected_spend=Decimal("1100.10"),
            blocked_since={},
        )
    assert any(e.kind == "overspend" for e in esc), "10.01% over budget not alerted at prec=3"


@LOW
def test_overspend_alert_huge_budget_digits() -> None:
    d = date(2026, 1, 5)
    budget = Decimal("1" + "0" * 29)
    spend = budget + budget / 10 + Decimal("0.01")
    esc = alerts.evaluate_unit(
        "u1",
        today=d,
        planned_finish=d,
        projected_finish=d,
        approved_budget=budget,
        projected_spend=spend,
        blocked_since={},
    )
    assert any(e.kind == "overspend" for e in esc)


@LOW
def test_qa_scope_beyond_fixed_precision() -> None:
    # Costs with > 60 significant digits: 10% + 1e-70 of scope is deviating.
    a = Decimal("10." + "0" * 69 + "1")
    b = Decimal(100) - a
    out = _outcome(
        approved_costs={"a": a, "b": b},
        verdicts={"a": "missing", "b": "done_as_specified"},
    )
    assert out.result is QaResult.FLAGGED
