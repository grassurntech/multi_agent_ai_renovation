"""QA (functional) re-run on 8f21e46.

``TestEndToEnd`` and ``TestContracts`` are integration checks expected to pass.
``TestFindings`` pins bugs found on 8f21e46; each of those tests FAILS on the current code.
"""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from reno_agents.calc.alerts import evaluate_unit, filter_new
from reno_agents.calc.costing import line_cost, needs_asset_manager_approval, tier_totals
from reno_agents.calc.qa_metrics import (
    budget_deviation,
    judge_lines,
    judge_photos,
    qa_outcome,
    timeline_deviation,
)
from reno_agents.calc.schedule import ScheduleTask, WorkCalendar, build_schedule, project_finish
from reno_agents.config import Settings
from reno_agents.domain.enums import EscalationKind, Event, LineVerdict, QaResult, Stage, Tier
from reno_agents.domain.lifecycle import GuardFailed, TransitionContext, transition
from reno_agents.inventory.catalog import Catalog
from reno_agents.inventory.loader import load_inventory, load_labor_rates

ROOT = Path(__file__).resolve().parents[2]
TODAY = date(2026, 11, 27)  # a Friday
CAL = WorkCalendar(holidays=frozenset({date(2026, 12, 25)}))
Z = Decimal("0")


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    r = load_inventory((ROOT / "data/sample/inventory.csv").read_text(), currency="USD")
    assert r.ok, r.errors[:3]
    return Catalog(r.items)


@pytest.fixture(scope="module")
def labor() -> dict[str, object]:
    r = load_labor_rates((ROOT / "data/sample/labor_rates.csv").read_text(), currency="USD")
    assert r.ok, r.errors[:3]
    return {x.task_code: x for x in r.items}


def _send(sent: dict, escalations: list) -> list:
    """What the app does with filter_new: send the new ones and record them."""
    new = filter_new(escalations, sent)
    for e in new:
        sent[(e.unit_id, e.kind, e.key)] = e.magnitude
    return new


class TestEndToEnd:
    def test_excel_export_variants_load_like_the_sample(self) -> None:
        text = (ROOT / "data/sample/inventory.csv").read_text()
        variants = [
            "﻿" + text.replace("\n", "\r\n"),  # Excel "CSV UTF-8" on Windows
            "\n".join(line + ",," for line in text.splitlines()) + "\n\n\n",  # stray columns
        ]
        base = load_inventory(text, currency="USD").items
        for v in variants:
            r = load_inventory(v, currency="usd")
            assert r.ok and r.items == base

    def test_sample_scope_costs_then_lifecycle(self, catalog: Catalog, labor: dict) -> None:
        s = Settings()
        picks = {
            g: catalog.pick(g, s.preferred_grade, TODAY)
            for g in ("PAINT-INT-WALL", "APPL-DISHWASHER", "ELEC-SWITCH")
        }
        assert all(p is not None and p.fallback_shortfall == 0 for p in picks.values())
        lines = [
            (
                Tier.HIGH,
                line_cost(Decimal("420"), picks["PAINT-INT-WALL"].primary, labor["L-PNT-WALL"]),
            ),
            (
                Tier.MEDIUM,
                line_cost(Decimal("1"), picks["APPL-DISHWASHER"].primary, labor["L-APPL-INSTALL"]),
            ),
            (Tier.LOW, line_cost(Decimal("1"), None, None, estimate=Decimal("14.995"))),
        ]
        totals = tier_totals(lines)
        assert totals[Tier.LOW] == Decimal("15.00")  # half-up on the PM estimate
        total = sum(totals.values(), Z)
        assert not needs_asset_manager_approval(total, s.approval_threshold)
        ctx = TransitionContext(scope_total=total, approval_threshold=s.approval_threshold)
        st = transition("planned", "scope_submitted", ctx)
        assert st is Stage.APPROVED
        st = transition(st, Event.FIRST_PO_SIGNED)
        with pytest.raises(GuardFailed):
            transition(st, Event.WORK_COMPLETED)  # no media facts: fails closed
        st = transition(
            st, Event.WORK_COMPLETED, TransitionContext(rooms_missing_after_media=frozenset())
        )
        assert transition(transition(st, Event.QA_RUN), Event.QA_FAILED) is Stage.IN_PROGRESS

    def test_schedule_projection_escalation_dedup_over_days(self, labor: dict) -> None:
        approval = TODAY  # Friday
        tasks = [
            ScheduleTask("demo", "demo", Decimal("8")),
            ScheduleTask("paint", "paint", Decimal("16"), materials_ready=date(2026, 11, 29)),
            ScheduleTask(
                "dw", "fixtures_appliances", Decimal("4"), materials_ready=date(2026, 12, 2)
            ),
        ]
        plan = build_schedule(tasks, approval, CAL)
        assert plan.tasks["demo"] == (date(2026, 11, 27), date(2026, 11, 27))
        assert plan.tasks["paint"] == (date(2026, 11, 30), date(2026, 12, 1))  # Sun delivery
        assert plan.finish == date(2026, 12, 2)

        sent: dict = {}
        common = dict(planned_finish=plan.finish, approved_budget=Decimal("10000"))
        # Day 1: dishwasher delayed to after Christmas -> slip, plus paint blocked 3 days.
        today = date(2026, 12, 4)
        late_dw = [ScheduleTask("dw", "fixtures_appliances", Decimal("4"), date(2026, 12, 25))]
        proj = project_finish(late_dw, today, approval, None, CAL)
        assert proj == date(2026, 12, 28)  # delivery on the 25th holiday, 26-27 weekend
        es = evaluate_unit(
            "u1",
            today=today,
            projected_finish=proj,
            projected_spend=Decimal("11500"),
            blocked_since={"paint": date(2026, 12, 1)},
            **common,
        )
        assert {e.kind for e in _send(sent, es)} == set(EscalationKind)
        # Day 2: same facts, one day longer blocked -> nothing re-sent.
        es = evaluate_unit(
            "u1",
            today=today + timedelta(1),
            projected_finish=proj,
            projected_spend=Decimal("11500"),
            blocked_since={"paint": date(2026, 12, 1)},
            **common,
        )
        assert _send(sent, es) == []
        # Day 3: spend worse, block cleared and re-blocked -> overspend + new blocked episode.
        es = evaluate_unit(
            "u1",
            today=date(2026, 12, 10),
            projected_finish=proj,
            projected_spend=Decimal("12000"),
            blocked_since={"paint": date(2026, 12, 6)},
            **common,
        )
        assert sorted(e.kind for e in _send(sent, es)) == [
            EscalationKind.BLOCKED,
            EscalationKind.OVERSPEND,
        ]

    def test_schedule_to_qa_outcome(self) -> None:
        tasks = [ScheduleTask("a", "paint", Decimal("80"))]  # 10 working days
        plan = build_schedule(tasks, TODAY, CAL)
        start, finish = plan.tasks["a"]
        assert (start, finish) == (date(2026, 11, 27), date(2026, 12, 10))
        timeline = timeline_deviation(start, finish, date(2026, 12, 11), CAL)  # 1 day late
        assert timeline == Decimal("10.00")
        out = qa_outcome(
            approved_costs={"L1": Decimal("900"), "L2": Decimal("100")},
            verdicts={"L1": "done_as_specified", "L2": "partial"},  # model output as strings
            recorded_issues=["I1", "I2"],
            photo_results={"I2": True, "I1": True},
            budget=budget_deviation(Decimal("11000"), Decimal("10000")),
            timeline=timeline,
        )
        assert out.result is QaResult.PASS_ and out.scope == Decimal("10.00")
        out = qa_outcome(
            approved_costs={"L1": Decimal("900"), "L2": Decimal("100")},
            verdicts={"L1": "done_as_specified", "L2": "partial"},
            recorded_issues=["I1", "I2"],
            photo_results={"I1": True, "I2": None},
            budget=Z,
            timeline=timeline_deviation(start, finish, date(2026, 12, 14), CAL),  # 2 days late
        )
        assert out.result is QaResult.FLAGGED and out.flags == ("timeline",)
        assert out.photos_not_verifiable == 1


class TestContracts:
    def test_judge_photos_keeps_recorded_order(self) -> None:
        assert judge_photos(["b", "a"], {"a": True, "b": False}) == [False, True]

    def test_judge_lines_takes_cost_from_records(self) -> None:
        [ln] = judge_lines({"L1": Decimal("5")}, {"L1": "missing"})
        assert ln.approved_cost == Decimal("5") and ln.verdict is LineVerdict.MISSING


class TestFindings:
    def test_unrecorded_swap_reported_as_different_item_is_not_a_pass(self) -> None:
        # Design §5.4: an approved swap is "done with a different item"; an installed item
        # that does not match what's visible is a deviation. qa_outcome takes no record of which
        # lines had an approved swap, so a model saying done_different_item on a line the PM
        # never swapped is counted as no deviation and the unit passes.
        out = qa_outcome(
            approved_costs={"L1": Decimal("5000")},
            verdicts={"L1": "done_different_item"},  # no swap was recorded for L1
            recorded_issues=["I1"],
            photo_results={"I1": True},
            budget=Z,
            timeline=Z,
        )
        assert out.result is not QaResult.PASS_

    def test_overspend_escalation_never_shows_at_or_under_threshold(self) -> None:
        d = date(2026, 12, 1)
        [e] = evaluate_unit(
            "u",
            today=d,
            planned_finish=d,
            projected_finish=d,
            approved_budget=Decimal("10000"),
            projected_spend=Decimal("11004"),
            blocked_since={},
        )
        # 10.04% fires the >10% alert, but the PM is told "10.0% over".
        assert e.magnitude > Decimal("10"), e.message

    def test_under_budget_by_a_fraction_is_not_negative_zero(self) -> None:
        shown = budget_deviation(Decimal("9999.99"), Decimal("10000"))
        assert str(shown) in {"0", "0.00"}, shown  # actual: "-0.00"

    def test_budget_under_a_fractional_threshold_is_not_flagged(self) -> None:
        # Scope is compared unrounded; budget arrives rounded up, so 10.001% flags at 10.005%.
        # Resolved by contract: thresholds have at most 2 decimals (so rounding up to 2 decimals
        # never crosses one), and a 3-decimal threshold is refused.
        with pytest.raises(ValueError):
            self._fractional_threshold_outcome()

    def _fractional_threshold_outcome(self) -> object:
        return qa_outcome(
            approved_costs={"L1": Decimal("1")},
            verdicts={"L1": "done_as_specified"},
            recorded_issues=["I1"],
            photo_results={"I1": True},
            budget=budget_deviation(Decimal("11000.10"), Decimal("10000")),
            timeline=Z,
            threshold=Decimal("10.005"),
        )

    def test_judge_photos_refuses_bare_string_and_non_bool_values(self) -> None:
        with pytest.raises((TypeError, ValueError)):
            judge_photos("ab", {"a": True, "b": False})  # a str is not a list of issue ids
        with pytest.raises((TypeError, ValueError)):
            judge_photos(["i1"], {"i1": 1})  # returned as [1] today

    def test_judge_lines_refuses_non_mapping_with_value_error(self) -> None:
        with pytest.raises(ValueError):
            judge_lines({"L1": Decimal("1")}, ["L1"])  # type: ignore[arg-type]  # TypeError today
