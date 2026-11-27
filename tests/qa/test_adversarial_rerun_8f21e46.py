"""Adversarial re-check of 8f21e46 (photo results keyed by recorded issue id).

Every test asserts the *expected safe* behaviour, so a failing test is a finding.
"""

import decimal
from decimal import Decimal
from pathlib import Path

import pytest

from reno_agents.calc import alerts, costing, qa_metrics
from reno_agents.domain.enums import LineVerdict, QaResult, Severity, Tier
from reno_agents.domain.tiers import apply_floor, load_tier_rules

Z = Decimal(0)
RULES = load_tier_rules(Path(__file__).resolve().parents[2] / "config" / "tier_rules.toml")


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


# --- Medium: "done_different_item" is a model claim never reconciled with recorded swaps -----
def test_unrecorded_swap_claim_does_not_pass() -> None:
    # Records: no swap was recorded for either line (installed item == planned primary).
    # The model labels BOTH lines "done_different_item" (e.g. persuaded by a "approved
    # substitute" sticker in the after photo). Design: only an *approved/recorded* swap is not a
    # deviation. qa_outcome has no input for recorded swaps, so it returns PASS.
    out = _outcome(
        approved_costs={"vanity": Decimal(900), "faucet": Decimal(100)},
        verdicts={"vanity": "done_different_item", "faucet": "done_different_item"},
    )
    assert out.result is not QaResult.PASS_


# --- Medium: severity floor silently skipped for a non-canonical model severity -------------
@pytest.mark.parametrize("sev", ["SAFETY", "Safety", " safety", "life_safety", "System-Level"])
def test_floor_refuses_or_applies_for_model_severity(sev: str) -> None:
    # Assessor (LLM) supplies severity. A spelling the enum does not know returns the proposed
    # LOW tier unchanged instead of raising: a safety issue lands in the low tier.
    try:
        tier = apply_floor(Tier.LOW, sev, RULES)  # type: ignore[arg-type]
    except ValueError:
        return
    assert tier is Tier.HIGH, f"severity {sev!r} -> {tier!r}"


def test_floor_unknown_tier_is_valueerror() -> None:
    with pytest.raises(ValueError):
        apply_floor("urgent", Severity.SAFETY, RULES)  # type: ignore[arg-type]


def test_tier_totals_unknown_tier_is_valueerror() -> None:
    cost = costing.LineCost(None, Decimal(1), Z, Decimal(1))
    with pytest.raises(ValueError):
        costing.tier_totals([("HIGH", cost)])  # type: ignore[list-item]


# --- Low: raw TypeError from verdict reconciliation (photo path was fixed with key=repr) -----
def test_mixed_type_verdict_keys_is_valueerror() -> None:
    with pytest.raises(ValueError):
        _outcome(verdicts={"kitchen": "done_as_specified", 1: "missing", "x": "missing"})


def test_verdicts_not_a_mapping_is_refused_cleanly() -> None:
    with pytest.raises((ValueError, TypeError)) as exc:
        _outcome(verdicts=["kitchen"])
    assert "list indices" not in str(exc.value)


# --- Low: threshold not validated; >= 100 makes scope/photo unflaggable -----------------------
def test_everything_missing_and_failed_is_not_pass_at_threshold_100() -> None:
    # Resolved by contract: a threshold of 100 or more would make scope/photo unflaggable, so
    # it is refused (Settings caps qa_deviation_pct below 100 too).
    with pytest.raises(ValueError):
        _outcome(
            verdicts={"kitchen": "missing"},
            photo_results={"issue-1": False},
            threshold=Decimal(100),
        )


# --- Low: result depends on the caller's thread decimal context ------------------------------
def test_reduced_global_precision_does_not_turn_flag_into_pass() -> None:
    ctx = decimal.getcontext().copy()
    ctx.prec = 4
    with decimal.localcontext(ctx):
        out = _outcome(
            approved_costs={"a": Decimal("10.0004"), "b": Decimal("89.9996")},
            verdicts={"a": "missing", "b": "done_as_specified"},
        )
    assert out.result is QaResult.FLAGGED  # 10.0004% > 10%


def test_budget_just_over_with_sub_cent_receipt_is_flagged() -> None:
    # Same class as the deferred scope precision Low, but on the budget path (actual spend from
    # receipts is not quantised to cents before the subtraction).
    pct = qa_metrics.budget_deviation(Decimal("1100.000000000000000000000000001"), Decimal(1000))
    assert _outcome(budget=pct).result is QaResult.FLAGGED


# --- Low: model-controlled ids are echoed into error text without a size bound ---------------
def test_error_message_size_is_bounded() -> None:
    junk = {f"<img src=x onerror=alert(1)>{'A' * 1000}{i}": True for i in range(2000)}
    with pytest.raises(ValueError) as exc:
        _outcome(photo_results={"issue-1": True} | junk)
    assert len(str(exc.value)) < 10_000, len(str(exc.value))


# --- Low: overspend alerts accept negative spend/budget that budget_deviation now refuses ----
def test_overspend_alert_refuses_negative_spend() -> None:
    from datetime import date

    d = date(2026, 1, 5)
    with pytest.raises(ValueError):
        alerts.evaluate_unit(
            "u1",
            today=d,
            planned_finish=d,
            projected_finish=d,
            approved_budget=Decimal(1000),
            projected_spend=Decimal(-5000),
            blocked_since={},
        )


def test_line_verdict_enum_sanity() -> None:
    # Guard against the above tests passing for the wrong reason.
    assert LineVerdict("done_different_item") is LineVerdict.DONE_DIFFERENT_ITEM
