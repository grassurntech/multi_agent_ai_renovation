"""Adversarial re-check of 53ec64d (fix pass for f461005 Mediums).

Every test asserts the *expected safe* behaviour. Ported to the record-based ``qa_outcome``
(approved_costs from the approved scope, verdicts from the model): attacks that relied on the
model supplying the line list now have to get past the id reconciliation instead.
"""

import decimal
from datetime import date
from decimal import Decimal

import pytest

from reno_agents.calc import alerts, qa_metrics
from reno_agents.domain.enums import LineVerdict, QaResult

QaLine = qa_metrics.QaLine
Z = Decimal(0)


def _outcome(
    lines: list[QaLine], photo_results: list[bool | None] | None = None
) -> qa_metrics.QaOutcome:
    return qa_metrics.qa_outcome(
        approved_costs={ln.line_id: ln.approved_cost for ln in lines},
        verdicts={ln.line_id: ln.verdict for ln in lines},
        photo_results=[True] if photo_results is None else photo_results,
        budget=Z,
        timeline=Z,
    )


# --- 1. Scope dilution bypasses -------------------------------------------------------------
class TestScopeDilution:
    @pytest.mark.parametrize("variant", ["bath ", " bath", "BATH", "bath​", "ｂath"])
    def test_near_duplicate_line_ids_rejected(self, variant: str) -> None:
        # 1 missing of 100 vs 1 done of 100 = 50%. Re-judging "bath" under a cosmetic variant id
        # 10x dilutes scope to 9.10% -> PASS.
        lines = [QaLine("kitchen", Decimal(100), LineVerdict.MISSING)]
        lines += [QaLine("bath", Decimal(100), LineVerdict.DONE_AS_SPECIFIED)]
        lines += [
            QaLine(variant * (i + 1), Decimal(100), LineVerdict.DONE_AS_SPECIFIED) for i in range(9)
        ]
        with pytest.raises(ValueError):
            qa_metrics.scope_deviation(lines)

    def test_fabricated_unique_lines_cannot_dilute(self) -> None:
        # Invented verdict ids that are not in the approved scope must be refused.
        verdicts = {"kitchen": LineVerdict.MISSING}
        verdicts |= {f"fake-{i}": LineVerdict.DONE_AS_SPECIFIED for i in range(10)}
        with pytest.raises(ValueError):
            qa_metrics.qa_outcome(
                approved_costs={"kitchen": Decimal(100)},
                verdicts=verdicts,
                photo_results=[True],
                budget=Z,
                timeline=Z,
            )

    def test_empty_verdict_list_is_not_pass(self) -> None:
        # Model returns no verdicts (tool failure / truncated JSON): refused, never PASS.
        with pytest.raises(ValueError):
            qa_metrics.qa_outcome(
                approved_costs={"kitchen": Decimal(100)},
                verdicts={},
                photo_results=[True],
                budget=Z,
                timeline=Z,
            )
        with pytest.raises(ValueError):
            _outcome([])

    def test_all_zero_cost_missing_lines_is_not_pass(self) -> None:
        lines = [QaLine(f"l{i}", Z, LineVerdict.MISSING) for i in range(5)]
        assert _outcome(lines).result is not QaResult.PASS_

    def test_unhashable_line_id_is_valueerror(self) -> None:
        # Refused when the line is built, so it can never reach scope_deviation.
        with pytest.raises(ValueError):
            lines = [QaLine(["a"], Decimal(1), LineVerdict.MISSING)]  # type: ignore[arg-type]
            qa_metrics.scope_deviation(lines)


# --- 2/3. Photo not-verifiable has no path to Needs evidence --------------------------------
class TestPhotoNotVerifiable:
    def test_all_photo_issues_unverifiable_is_not_pass(self) -> None:
        # Assessor marks every failing issue None instead of False: photo=0% and, since
        # qa_outcome no longer accepts a not-verifiable count, the unit PASSES.
        lines = [QaLine("a", Decimal(100), LineVerdict.DONE_AS_SPECIFIED)]
        assert _outcome(lines, photo_results=[None, None, None]).result is not QaResult.PASS_

    def test_negative_photo_figure_refused(self) -> None:
        # The photo figure is derived from photo_results; a caller cannot pass one in.
        with pytest.raises(TypeError):
            qa_metrics.qa_outcome(  # type: ignore[call-arg]
                approved_costs={"a": Decimal(100)},
                verdicts={"a": LineVerdict.DONE_AS_SPECIFIED},
                photo_results=[True],
                photo=Decimal("-50"),
                budget=Z,
                timeline=Z,
            )

    @pytest.mark.parametrize("v", [1, 0, "true", b"", 1.0])
    def test_non_bool_photo_values_refused(self, v: object) -> None:
        with pytest.raises((TypeError, ValueError)):
            qa_metrics.photo_deviation([v])  # type: ignore[list-item]


# --- 4. Remaining overflow paths -------------------------------------------------------------
class TestOverflow:
    def test_budget_deviation_subtraction_overflow_is_valueerror(self) -> None:
        # actual - approved is evaluated before _pct's try block.
        with pytest.raises(ValueError):
            qa_metrics.budget_deviation(Decimal("-9E+999999"), Decimal("9E+999999"))

    def test_scope_cost_sum_overflow_is_valueerror(self) -> None:
        lines = [
            QaLine("a", Decimal("9E+999999"), LineVerdict.MISSING),
            QaLine("b", Decimal("9E+999999"), LineVerdict.DONE_AS_SPECIFIED),
        ]
        with pytest.raises(ValueError):
            qa_metrics.scope_deviation(lines)
        with pytest.raises(ValueError):
            _outcome(lines)

    def test_nan_approved_budget_is_valueerror(self) -> None:
        # `approved_budget > 0` runs outside the try block.
        try:
            alerts.evaluate_unit(
                "u1",
                today=date(2026, 1, 1),
                planned_finish=date(2026, 1, 1),
                projected_finish=date(2026, 1, 1),
                approved_budget=Decimal("NaN"),
                projected_spend=Decimal(100),
                blocked_since={},
            )
        except decimal.InvalidOperation:
            pytest.fail("decimal.InvalidOperation leaked")
        except ValueError:
            pass
