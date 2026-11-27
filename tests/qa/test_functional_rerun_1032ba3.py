"""QA (functional) re-run on 1032ba3.

``TestClosed`` confirms the findings from 8f21e46 are closed and the new inputs work end to end
(expected to pass). ``TestFindings`` pins issues found on 1032ba3; each FAILS on the current code.
"""

from datetime import date
from decimal import Context, Decimal, localcontext
from pathlib import Path

import pytest

from reno_agents.calc.alerts import evaluate_unit, filter_new
from reno_agents.calc.qa_metrics import budget_deviation, judge_lines, judge_photos, qa_outcome
from reno_agents.config import Settings
from reno_agents.domain.enums import LineVerdict, QaResult, Severity, Tier
from reno_agents.domain.tiers import apply_floor, load_tier_rules

LOW = pytest.mark.xfail(
    strict=True, reason="Deferred Low from QA re-check of 1032ba3; see tech-debt tracker"
)

ROOT = Path(__file__).resolve().parents[2]
D = Decimal
DAY = date(2026, 11, 27)
COSTS = {"L1": D("100"), "L2": D("100")}
VERDICTS = {"L1": "done_different_item", "L2": "done_as_specified"}
BASE = dict(
    approved_costs=COSTS,
    verdicts=VERDICTS,
    recorded_issues=["I1"],
    photo_results={"I1": True},
    budget=D("0"),
    timeline=D("0"),
)


def _overspend(spend: str, budget: str = "100") -> list:
    return evaluate_unit(
        "u",
        today=DAY,
        planned_finish=DAY,
        projected_finish=DAY,
        approved_budget=D(budget),
        projected_spend=D(spend),
        blocked_since={},
    )


class TestClosed:
    def test_recorded_swap_is_not_a_deviation_end_to_end(self) -> None:
        out = qa_outcome(**BASE, recorded_swaps={"L1"})
        assert out.result is QaResult.PASS_ and out.scope == 0

    def test_unrecorded_swap_is_a_deviation_by_default(self) -> None:
        out = qa_outcome(**BASE)
        assert out.result is QaResult.FLAGGED and out.flags == ("scope",)

    @pytest.mark.parametrize("swaps", [["L1"], ("L1",), {"L1": 1}.keys(), frozenset({"L1"})])
    def test_recorded_swaps_accepts_any_collection(self, swaps: object) -> None:
        lines = judge_lines(COSTS, VERDICTS, swaps)  # type: ignore[arg-type]
        assert lines[0].verdict is LineVerdict.DONE_DIFFERENT_ITEM

    @pytest.mark.parametrize("sev", ["SAFETY", " Safety\n", "System-Level", "system level"])
    def test_severity_variants_hit_the_floor(self, sev: str) -> None:
        rules = load_tier_rules(ROOT / "config/tier_rules.toml")
        assert apply_floor(Tier.LOW, sev, rules) is Tier.HIGH  # type: ignore[arg-type]

    @pytest.mark.parametrize("sev", ["systemlevel", "​safety", "", None])
    def test_unknown_severity_fails_closed(self, sev: object) -> None:
        rules = load_tier_rules(ROOT / "config/tier_rules.toml")
        with pytest.raises(ValueError):
            apply_floor(Tier.LOW, sev, rules)  # type: ignore[arg-type]

    def test_every_canonical_severity_still_accepted(self) -> None:
        rules = load_tier_rules(ROOT / "config/tier_rules.toml")
        for sev in Severity:
            assert apply_floor(Tier.HIGH, sev, rules) is Tier.HIGH
            assert apply_floor(Tier.LOW, sev.value, rules) in Tier  # type: ignore[arg-type]

    def test_overspend_just_over_never_reads_on_threshold(self) -> None:
        (e,) = _overspend("110.0001")
        assert e.magnitude == D("10.1") and "10.1%" in e.message

    def test_overspend_dedup_resends_only_when_shown_figure_grows(self) -> None:
        sent: dict = {}
        resent = []
        for spend in ("110.01", "110.09", "110.10", "110.1000001", "110.11"):
            new = filter_new(_overspend(spend), sent)
            for e in new:
                sent[(e.unit_id, e.kind, e.key)] = e.magnitude
            resent.append([e.magnitude for e in new])
        assert resent == [[D("10.1")], [], [], [D("10.2")], []]

    def test_no_negative_zero_budget(self) -> None:
        assert not budget_deviation(D("99.9999"), D("100")).is_signed()

    def test_threshold_and_settings_agree(self) -> None:
        for ok in ("0", "10", "10.000", "1e1", "99.99"):
            qa_outcome(
                **BASE,
                recorded_swaps={"L1"},
                threshold=Settings(qa_deviation_pct=ok).qa_deviation_pct,
            )
        for bad in ("99.999", "100", "0.001", "-0.01"):
            with pytest.raises(ValueError):
                qa_outcome(**BASE, threshold=D(bad))
            with pytest.raises(ValueError):
                Settings(qa_deviation_pct=bad)

    @pytest.mark.parametrize("bad", [1, 0, "true"])
    def test_photo_results_must_be_bool_or_none(self, bad: object) -> None:
        with pytest.raises(TypeError):
            judge_photos(["I1"], {"I1": bad})  # type: ignore[dict-item]


class TestFindings:
    @LOW
    def test_threshold_check_ignores_caller_decimal_context(self) -> None:
        # Low: the "fixed 60-digit context" does not cover threshold.quantize (qa_metrics.py:273),
        # so a caller with a low-precision context gets a raw decimal.InvalidOperation.
        with localcontext(Context(prec=3)):
            assert qa_outcome(**BASE, recorded_swaps={"L1"}).result is QaResult.PASS_

    @LOW
    def test_recorded_swaps_iterator_is_not_silently_emptied(self) -> None:
        # Low: set(recorded_swaps) consumes a one-shot iterator (qa_metrics.py:139), then the
        # membership test at :144 sees nothing, so a recorded swap is counted as a mismatch.
        lines = judge_lines(COSTS, VERDICTS, (x for x in ["L1"]))  # type: ignore[arg-type]
        assert lines[0].verdict is LineVerdict.DONE_DIFFERENT_ITEM

    @LOW
    def test_recorded_swaps_none_raises_value_error(self) -> None:
        # Low: docstring promises ValueError; None gives a bare TypeError from set(None).
        with pytest.raises(ValueError):
            judge_lines(COSTS, VERDICTS, None)  # type: ignore[arg-type]

    @LOW
    def test_overspend_alert_ignores_caller_decimal_context(self) -> None:
        # Low (pre-existing, outside the fixed context): 10.001% over is missed at prec=3.
        with localcontext(Context(prec=3)):
            assert _overspend("110001", "100000")
