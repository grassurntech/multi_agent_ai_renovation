"""Adversarial re-check of 3405585 (record-based qa_outcome).

Every test asserts the *expected safe* behaviour, so a failing test is a finding. Photo tests
are ported to the keyed API (photo results by recorded issue id); deferred Lows are strict xfail.
"""

from decimal import Decimal

import pytest

from reno_agents.calc import qa_metrics
from reno_agents.domain.enums import LineVerdict, QaResult

Z = Decimal(0)
APPROVED = {"kitchen": Decimal(100)}
DONE = {"kitchen": LineVerdict.DONE_AS_SPECIFIED}


LOW = pytest.mark.xfail(
    strict=True, reason="Deferred Low from adversarial re-check of 3405585; see tech-debt tracker"
)


def _photo_outcome(recorded: list[str], photo_results: object) -> qa_metrics.QaOutcome:
    return qa_metrics.qa_outcome(
        approved_costs=APPROVED,
        verdicts=DONE,
        recorded_issues=recorded,
        photo_results=photo_results,  # type: ignore[arg-type]
        budget=Z,
        timeline=Z,
    )


# --- Medium: photo results are an anonymous list, not reconciled with the recorded issues ----
class TestPhotoDilution:
    def test_padding_with_invented_resolved_issues_does_not_pass(self) -> None:
        # The unit has ONE recorded issue and it was not resolved (100% photo deviation).
        # The model pads the list with 9 invented "resolved" comparisons -> 10.00% -> PASS.
        # Expected: photo results keyed by recorded issue id and reconciled like verdicts.
        padded = {"issue-1": False} | {f"invented-{i}": True for i in range(9)}
        with pytest.raises(ValueError):
            _photo_outcome(["issue-1"], padded)

    def test_dropping_failed_issues_does_not_pass(self) -> None:
        # The unit has 3 recorded issues, 2 failed. The model reports just one True -> PASS.
        # qa_outcome cannot tell, because it never sees the recorded issue list.
        with pytest.raises(ValueError):
            _photo_outcome(["issue-1", "issue-2", "issue-3"], {"issue-1": True})


# --- Low: single-pass iterables are consumed by validation, so their results vanish --------
class TestPhotoIterable:
    def test_generator_of_unverifiable_is_refused(self) -> None:
        # Photo results must be a mapping keyed by issue id; a one-shot iterable is refused.
        with pytest.raises(TypeError):
            _photo_outcome(["a", "b"], (r for r in [None, None]))

    def test_generator_of_failures_is_refused(self) -> None:
        with pytest.raises(TypeError):
            _photo_outcome(["a", "b"], (r for r in [False, False]))


# --- Low: a zero-cost deviating line is invisible once any priced line exists ---------------
@LOW
def test_zero_cost_missing_line_is_seen_alongside_priced_lines() -> None:
    # Comment at qa_metrics._scope_raw says the zero-cost fallback exists "so missing work is
    # still seen", but it only applies when *every* verifiable line is zero-cost.
    out = qa_metrics.qa_outcome(
        approved_costs={"paint": Decimal(100), "smoke-detector": Z},
        verdicts={"paint": "done_as_specified", "smoke-detector": "missing"},
        recorded_issues=["issue-1"],
        photo_results={"issue-1": True},
        budget=Z,
        timeline=Z,
    )
    assert out.result is not QaResult.PASS_


# --- Low: precision loss at default 28-digit context turns >10% into exactly 10% -----------
def test_scope_just_over_threshold_with_wide_costs_is_flagged() -> None:
    out = qa_metrics.qa_outcome(
        approved_costs={
            "a": Decimal("100000000000000000000000000001"),
            "b": Decimal("900000000000000000000000000000"),
        },
        verdicts={"a": "missing", "b": "done_as_specified"},
        recorded_issues=["issue-1"],
        photo_results={"issue-1": True},
        budget=Z,
        timeline=Z,
    )
    assert out.result is QaResult.FLAGGED  # true value is 10.0000...0001%


# --- Low: negative actual spend is accepted ---------------------------------------------------
def test_negative_actual_spend_refused() -> None:
    with pytest.raises(ValueError):
        qa_metrics.budget_deviation(Decimal(-5000), Decimal(1000))
