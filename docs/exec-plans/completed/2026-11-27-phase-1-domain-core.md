# Phase 1 — Domain Core Implementation Plan

> **Outcome (2026-11-27):** shipped in PR #2 (merged). Domain core built with 567 tests; QA agents found and fixed 2 High-in-effect issues (CSV formula injection, severity floor) and several Mediums; remaining Lows are TD-001–TD-005. QA fixes changed some interfaces below — notably `LineVerdict.INSTALLED_MISMATCH` + `recorded_swaps`, the record-based `qa_outcome(...)`, blocked-alert keys `<task>@<since>` and `rooms_missing_after_media=None` (fail closed). The PR #2 description lists them; the code is authoritative.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A public-repo-ready Python package holding every rule and calculation the four agents and
the web app will rely on — unit lifecycle, inventory/labor loading, item selection, sample data,
costing, approvals, schedule, escalations, QA metrics — fully tested, with no AI, database, or web
code yet.

**Architecture:** Pure, dependency-light Python modules under `src/reno_agents/`. Agents (phase 2)
and the web app (phase 3) call these functions; nothing here calls a model, a database, or the
network. "Agents do judgment, code does arithmetic" (design §5) — this phase *is* the arithmetic.

**Tech Stack:** Python ≥3.11, uv, Pydantic v2 + pydantic-settings, stdlib `csv`/`tomllib`/`decimal`,
pytest, ruff, mypy (strict), gitleaks, GitHub Actions.

**Spec:** [docs/design-docs/reno-agents-system.md](../../design-docs/reno-agents-system.md)

**Phase roadmap** (each phase gets its own plan, written after the previous one ships):
1. **Domain core** — this plan.
2. **Agents** — DB models + migrations, media pipeline (EXIF strip, HEIC→JPEG, ffmpeg frames,
   native-video adapter), the four ADK agents with per-agent model settings (LiteLLM), job queue +
   worker.
3. **Web app** — FastAPI + Jinja2/HTMX screens, auth/roles, uploads, approvals, PO/QA PDFs, SMTP
   notifications, DB-locked daily run, Nixpacks/Docker/Cloud Run.

## Global Constraints

- Python `>=3.11`; dependency management and commands via **uv**; package `reno_agents` in `src/` layout.
- Money is `decimal.Decimal`, never `float`; round to `0.01` with `ROUND_HALF_UP` at the end of each
  computed amount.
- Every "more than" threshold is **strictly greater than** (`>`): approval threshold, change-request
  %, >7 days slip, >10% overspend, >2 days blocked, >10% QA deviation.
- Defaults verbatim from the spec: approval threshold `15000`, `preferred_grade = better`,
  `change_request_pct = 10`, `low_confidence_threshold = 0.5`, `blocked_alert_days = 2`,
  `slip_alert_days = 7`, `overspend_alert_pct = 10`, `qa_deviation_pct = 10`, workdays Mon–Fri,
  `hours_per_day = 8`, currency `USD`.
- No AI, database, HTTP, or web code in this phase.
- Public repo: no secrets, no real names/emails/addresses/phone numbers; sample data uses fictional
  brands and suppliers; any email in the repo uses `example.com`. No contact emails in
  SECURITY/CODE_OF_CONDUCT — use GitHub's private vulnerability reporting and repository issues.
- License **Apache-2.0**.
- CLAUDE.md Rule 2 (QA agents) runs after the dev work and before any PR; Rule 1 (docs sync) after
  ship/PR. Plan decisions that the spec left open are recorded in "Decisions" below.

## Decisions made in this plan (spec left open)

- **Slip is measured in calendar days** (projected finish − planned finish), so ">7 days" means what
  a PM would count on a calendar. Durations are still built from working days.
- **Asset-manager rejection** (not in spec's diagram) sends the unit back to `planned` with a note.
- **Assessor re-run** allowed from `draft` and `assessed`; **Planner re-run** from `assessed` and `planned`.
- **Excel-friendly CSV parsing:** UTF-8 BOM, blank trailing rows, `y/n` in any case, and currency
  formatting (`$1,234.50`) are accepted; anything else malformed is a row error, never a silent guess.
- **A substitution group with fewer than 3 active approved items** still yields a pick, with a
  `fallback_shortfall` count the Planner/UI must surface.
- **QA result precedence:** `flagged` if any metric > threshold; else `needs_evidence` if any line is
  not verifiable; else `pass`.
- Tier rules file is **TOML** (stdlib `tomllib`, no extra dependency).

## Review Focus

1. **Inventory CSV saved from Excel/Sheets** (BOM, `$1,234.50`, lowercase `y`, blank trailing rows,
   duplicate SKU) → loads cleanly or gives a row-numbered error; never a wrong number. *Tests in Task 4.*
2. **Substitution group thinned by expired/unapproved items** → expired or unapproved items never
   picked; shortfall reported instead of a crash. *Tests in Task 5.*
3. **Scope total exactly at the threshold (15,000.00)** → approved by PM, no asset-manager step.
   *Tests in Tasks 3 and 8.*
4. **Approval on a weekend/holiday, or materials "ready" on a past date or weekend** → schedule
   starts on the next working day; past dates don't pull work earlier than the start. *Tests in Task 9.*
5. **Empty denominators in QA/budget maths** (all lines not verifiable, zero approved budget, zero
   planned duration) → no `ZeroDivisionError`; result is `needs_evidence` or a clear `ValueError`.
   *Tests in Task 11.*

---

## File Structure

```
pyproject.toml                         uv project, tool config
.env.example                           placeholder-only settings
.pre-commit-config.yaml                gitleaks + ruff
.github/workflows/ci.yml               lint, types, tests, secret scan
.github/dependabot.yml
.github/ISSUE_TEMPLATE/{bug_report,feature_request}.md
.github/pull_request_template.md
README.md  LICENSE  CONTRIBUTING.md  CODE_OF_CONDUCT.md  SECURITY.md  CHANGELOG.md
config/tier_rules.toml                 editable tier rules
data/sample/inventory.csv              ~60 fictional items
data/sample/labor_rates.csv            matching labor rates
src/reno_agents/__init__.py
src/reno_agents/config.py              Settings
src/reno_agents/domain/enums.py        shared enums
src/reno_agents/domain/lifecycle.py    unit state machine
src/reno_agents/domain/tiers.py        tier rules + severity floor
src/reno_agents/inventory/schema.py    InventoryItem, LaborRate, RowError, LoadResult
src/reno_agents/inventory/loader.py    CSV loaders
src/reno_agents/inventory/catalog.py   Catalog, Pick
src/reno_agents/calc/money.py          to_money()
src/reno_agents/calc/costing.py        quantities, line cost, totals, approval rules
src/reno_agents/calc/schedule.py       WorkCalendar, TRADE_ORDER, build/project schedule
src/reno_agents/calc/alerts.py         escalation rules + dedup
src/reno_agents/calc/qa_metrics.py     four QA deviations + result
tests/...                              mirrors src/, plus test_repo_hygiene.py, test_sample_data.py
```

---

### Task 1: Project scaffold and public-repo hygiene

**Files:**
- Create: `pyproject.toml`, `src/reno_agents/__init__.py`, `.env.example`, `.pre-commit-config.yaml`,
  `.github/workflows/ci.yml`, `.github/dependabot.yml`, `.github/ISSUE_TEMPLATE/bug_report.md`,
  `.github/ISSUE_TEMPLATE/feature_request.md`, `.github/pull_request_template.md`, `README.md`,
  `LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CHANGELOG.md`
- Modify: `.gitignore` (append `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `*.sqlite3`, `media/`, `data/local/`)
- Test: `tests/test_repo_hygiene.py`

**Interfaces:**
- Produces: importable package `reno_agents` with `__version__ = "0.1.0"`; `uv run pytest`,
  `uv run ruff check .`, `uv run mypy src` all work.

- [ ] **Step 1: Write `pyproject.toml`** — `name = "reno-agents"`, `version = "0.1.0"`,
  `requires-python = ">=3.11"`, `license = "Apache-2.0"`, dependencies `pydantic>=2.7`,
  `pydantic-settings>=2.7`; `[dependency-groups] dev = ["pytest>=8", "ruff>=0.6", "mypy>=1.10"]`;
  hatchling build backend with `packages = ["src/reno_agents"]`; ruff `line-length = 100`,
  `target-version = "py311"`, select `E,F,I,UP,B,SIM`; mypy `strict = true`; pytest `testpaths = ["tests"]`.
  Create `src/reno_agents/__init__.py` with `__version__ = "0.1.0"`. Run `uv sync`. Expected: creates `uv.lock`, no errors.

- [ ] **Step 2: Write the failing hygiene tests** in `tests/test_repo_hygiene.py`

```python
import re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_EMAIL_DOMAINS = {"example.com", "example.org", "example.net"}
KEY_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{35}"),            # Google API key
    re.compile(r"sk-(ant-)?[A-Za-z0-9_\-]{20,}"),     # OpenAI / Anthropic style
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]

def tracked_text_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    files = [ROOT / p for p in out.stdout.splitlines()]
    return [f for f in files if f.is_file() and f.suffix not in {".png", ".jpg", ".jpeg", ".mp4", ".mov", ".lock"}]

def test_no_real_email_addresses():
    email = re.compile(r"[A-Za-z0-9._%+\-]+@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})")
    offenders = [(f.name, m.group(0)) for f in tracked_text_files()
                 for m in email.finditer(f.read_text(errors="ignore"))
                 if m.group(1).lower() not in ALLOWED_EMAIL_DOMAINS]
    assert offenders == []

def test_no_key_like_strings():
    offenders = [(f.name, p.pattern) for f in tracked_text_files()
                 for p in KEY_PATTERNS if p.search(f.read_text(errors="ignore"))]
    assert offenders == []

def test_env_example_has_only_placeholders():
    for line in (ROOT / ".env.example").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        assert value == "" or value.startswith("your-") or value in {"changeme", "USD", "15000", "better"}, key

def test_required_public_repo_files_exist():
    for name in ["README.md", "LICENSE", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md",
                 "CHANGELOG.md", ".env.example", ".github/workflows/ci.yml"]:
        assert (ROOT / name).is_file(), name
```

  The patterns are written so their own source text doesn't match them (each literal is followed by
  `(` or `[`), so the test file and this plan pass their own scan.

- [ ] **Step 3: Run** `uv run pytest tests/test_repo_hygiene.py -v`. Expected: FAIL (missing files).

- [ ] **Step 4: Create the hygiene files.**
  - `LICENSE`: the canonical Apache-2.0 text fetched from `https://www.apache.org/licenses/LICENSE-2.0.txt`
    (ask the user before downloading), copyright line `Copyright 2026 The AI Reno Agents Authors`.
  - `CODE_OF_CONDUCT.md`: Contributor Covenant 2.1, enforcement contact = "open a private report via
    the repository's **Security → Report a vulnerability** form or contact the maintainers through
    GitHub" (no email).
  - `SECURITY.md`: supported versions (latest `main`), report via GitHub private vulnerability
    reporting, what not to include (real tenant photos, keys).
  - `CONTRIBUTING.md`: uv setup, `pre-commit install`, run tests/lint/types, branch + PR flow, "never
    commit real customer media or vendor pricing", the two QA-agent rules from CLAUDE.md summarised.
  - `README.md`: one-paragraph pitch, the four agents, status "Phase 1: domain core", quick start
    (`uv sync`, `uv run pytest`), link to the design doc, license badge text.
  - `CHANGELOG.md`: Keep-a-Changelog format, `## [Unreleased]`.
  - `.env.example`: `RENO_CURRENCY=USD`, `RENO_APPROVAL_THRESHOLD=15000`, `RENO_PREFERRED_GRADE=better`,
    `GOOGLE_API_KEY=your-google-api-key`, `RENO_SECRET_KEY=changeme`.
  - `.pre-commit-config.yaml`: `gitleaks/gitleaks` hook and `astral-sh/ruff-pre-commit` (ruff + ruff-format), pinned revs.
  - `.github/workflows/ci.yml`: on push/PR to `main`; job `test` on ubuntu-latest with
    `astral-sh/setup-uv`, `uv sync`, `uv run ruff check .`, `uv run ruff format --check .`,
    `uv run mypy src`, `uv run pytest`; job `secrets` with `gitleaks/gitleaks-action@v2`
    (`fetch-depth: 0`). Python 3.11 and 3.12 matrix.
  - `.github/dependabot.yml`: weekly for `pip` (uv) and `github-actions`.
  - Issue templates (bug, feature) and PR template with a checklist: tests, no secrets/personal data, docs synced (Rule 1).

- [ ] **Step 5: Run** `uv run pytest -v && uv run ruff check . && uv run mypy src`. Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: scaffold uv project and public-repo hygiene"
```

---

### Task 2: Shared enums and settings

**Files:**
- Create: `src/reno_agents/domain/__init__.py`, `src/reno_agents/domain/enums.py`, `src/reno_agents/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces (all `StrEnum`, lowercase values):
  - `Stage`: `draft, assessed, planned, awaiting_am_approval, approved, in_progress, complete, qa_review, ready_to_lease`
  - `Event`: `assessor_run, planner_run, scope_submitted, am_approved, am_rejected, first_po_signed, work_completed, qa_run, qa_passed, qa_failed`
  - `Grade`: `good, better, best`; `grade_rank(g: Grade) -> int` → 0/1/2
  - `Tier`: `high, medium, low`
  - `Severity`: `minor, moderate, major, system_level, safety`
  - `LineVerdict`: `done_as_specified, done_different_item, partial, missing, not_verifiable`
  - `QaResult`: `pass, flagged, needs_evidence` (member name `PASS_` since `pass` is a keyword; value `"pass"`)
  - `EscalationKind`: `slip, overspend, blocked`
- Produces: `class Settings(BaseSettings)` (env prefix `RENO_`) with fields
  `currency: str = "USD"`, `approval_threshold: Decimal = Decimal("15000")`,
  `preferred_grade: Grade = Grade.BETTER`, `change_request_pct: Decimal = Decimal("10")`,
  `low_confidence_threshold: float = 0.5`, `blocked_alert_days: int = 2`, `slip_alert_days: int = 7`,
  `overspend_alert_pct: Decimal = Decimal("10")`, `qa_deviation_pct: Decimal = Decimal("10")`,
  `hours_per_day: Decimal = Decimal("8")`, `workdays: frozenset[int] = frozenset({0,1,2,3,4})`
  (env as comma list `"0,1,2,3,4"`, each 0–6), `holidays: frozenset[date] = frozenset()` (env as comma list of ISO dates);
  `get_settings() -> Settings` (cached with `functools.lru_cache`).

- [ ] **Step 1: Write failing tests**

```python
from datetime import date
from decimal import Decimal
import pytest
from pydantic import ValidationError
from reno_agents.config import Settings
from reno_agents.domain.enums import Grade, grade_rank

def test_defaults_match_spec():
    s = Settings()
    assert s.approval_threshold == Decimal("15000")
    assert s.preferred_grade is Grade.BETTER
    assert s.change_request_pct == Decimal("10")
    assert s.low_confidence_threshold == 0.5
    assert (s.blocked_alert_days, s.slip_alert_days) == (2, 7)
    assert s.overspend_alert_pct == s.qa_deviation_pct == Decimal("10")
    assert s.workdays == frozenset({0, 1, 2, 3, 4})

def test_env_overrides(monkeypatch):
    monkeypatch.setenv("RENO_APPROVAL_THRESHOLD", "20000")
    monkeypatch.setenv("RENO_WORKDAYS", "0,1,2,3,4,5")
    monkeypatch.setenv("RENO_HOLIDAYS", "2026-12-25,2027-01-01")
    s = Settings()
    assert s.approval_threshold == Decimal("20000")
    assert 5 in s.workdays
    assert date(2026, 12, 25) in s.holidays

def test_invalid_workday_rejected(monkeypatch):
    monkeypatch.setenv("RENO_WORKDAYS", "0,7")
    with pytest.raises(ValidationError):
        Settings()

def test_grade_rank_order():
    assert [grade_rank(g) for g in (Grade.GOOD, Grade.BETTER, Grade.BEST)] == [0, 1, 2]
```

- [ ] **Step 2: Run** `uv run pytest tests/test_config.py -v`. Expected: FAIL (`ModuleNotFoundError`).
- [ ] **Step 3: Implement** `enums.py` and `config.py` per Interfaces. Annotate `workdays` and
  `holidays` with `Annotated[..., NoDecode]` (pydantic-settings ≥2.7; otherwise it tries to JSON-decode
  the env value and fails) and parse comma lists with a `field_validator(mode="before")`; set `model_config = SettingsConfigDict(env_prefix="RENO_", env_file=None)`
  (no `.env` read in tests).
- [ ] **Step 4: Run** `uv run pytest tests/test_config.py -v && uv run mypy src`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -am "feat: shared enums and settings"` (add new files first).

---

### Task 3: Unit lifecycle state machine

**Files:**
- Create: `src/reno_agents/domain/lifecycle.py`
- Test: `tests/domain/test_lifecycle.py`

**Interfaces:**
- Consumes: `Stage`, `Event` (Task 2).
- Produces:
  - `@dataclass(frozen=True) class TransitionContext: scope_total: Decimal | None = None; approval_threshold: Decimal | None = None; rooms_missing_after_media: frozenset[str] = frozenset()`
  - `class InvalidTransition(Exception)` — event not allowed from this stage.
  - `class GuardFailed(Exception)` — allowed but a precondition failed; `.reasons: list[str]`.
  - `def transition(stage: Stage, event: Event, ctx: TransitionContext = TransitionContext()) -> Stage`
  - `def allowed_events(stage: Stage) -> frozenset[Event]`

Transition table (from spec §3 + plan Decisions):

| From | Event | To |
|---|---|---|
| draft, assessed | assessor_run | assessed |
| assessed, planned | planner_run | planned |
| planned | scope_submitted | approved if `scope_total <= approval_threshold` else awaiting_am_approval (both required, else `GuardFailed`) |
| awaiting_am_approval | am_approved | approved |
| awaiting_am_approval | am_rejected | planned |
| approved | first_po_signed | in_progress |
| in_progress | work_completed | complete (`GuardFailed` listing rooms if `rooms_missing_after_media` non-empty) |
| complete | qa_run | qa_review |
| qa_review | qa_passed | ready_to_lease |
| qa_review | qa_failed | in_progress |

- [ ] **Step 1: Write failing tests**

```python
from decimal import Decimal
import pytest
from reno_agents.domain.enums import Event as E, Stage as S
from reno_agents.domain.lifecycle import GuardFailed, InvalidTransition, TransitionContext as Ctx, transition

T = Decimal("15000")

@pytest.mark.parametrize("frm,ev,to", [
    (S.DRAFT, E.ASSESSOR_RUN, S.ASSESSED), (S.ASSESSED, E.ASSESSOR_RUN, S.ASSESSED),
    (S.ASSESSED, E.PLANNER_RUN, S.PLANNED), (S.PLANNED, E.PLANNER_RUN, S.PLANNED),
    (S.AWAITING_AM_APPROVAL, E.AM_APPROVED, S.APPROVED), (S.AWAITING_AM_APPROVAL, E.AM_REJECTED, S.PLANNED),
    (S.APPROVED, E.FIRST_PO_SIGNED, S.IN_PROGRESS), (S.COMPLETE, E.QA_RUN, S.QA_REVIEW),
    (S.QA_REVIEW, E.QA_PASSED, S.READY_TO_LEASE), (S.QA_REVIEW, E.QA_FAILED, S.IN_PROGRESS),
])
def test_valid_transitions(frm, ev, to):
    assert transition(frm, ev) is to

def test_scope_exactly_at_threshold_is_pm_approved():
    assert transition(S.PLANNED, E.SCOPE_SUBMITTED, Ctx(Decimal("15000.00"), T)) is S.APPROVED

def test_scope_over_threshold_needs_asset_manager():
    assert transition(S.PLANNED, E.SCOPE_SUBMITTED, Ctx(Decimal("15000.01"), T)) is S.AWAITING_AM_APPROVAL

def test_scope_submit_without_totals_fails_guard():
    with pytest.raises(GuardFailed):
        transition(S.PLANNED, E.SCOPE_SUBMITTED)

def test_work_completed_requires_after_media_per_room():
    with pytest.raises(GuardFailed) as exc:
        transition(S.IN_PROGRESS, E.WORK_COMPLETED, Ctx(rooms_missing_after_media=frozenset({"Kitchen"})))
    assert "Kitchen" in " ".join(exc.value.reasons)
    assert transition(S.IN_PROGRESS, E.WORK_COMPLETED, Ctx()) is S.COMPLETE

@pytest.mark.parametrize("frm,ev", [
    (S.PLANNED, E.ASSESSOR_RUN), (S.DRAFT, E.PLANNER_RUN), (S.APPROVED, E.QA_RUN),
    (S.READY_TO_LEASE, E.QA_FAILED), (S.IN_PROGRESS, E.FIRST_PO_SIGNED),
])
def test_invalid_transitions(frm, ev):
    with pytest.raises(InvalidTransition):
        transition(frm, ev)
```

- [ ] **Step 2: Run** `uv run pytest tests/domain/test_lifecycle.py -v`. Expected: FAIL (import error).
- [ ] **Step 3: Implement** with a dict `{(Stage, Event): Stage}` for static rows plus explicit
  handling for `scope_submitted` and `work_completed`.
- [ ] **Step 4: Run** the tests + `uv run mypy src`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: unit lifecycle state machine`.

---

### Task 4: Inventory and labor CSV loaders

**Files:**
- Create: `src/reno_agents/inventory/__init__.py`, `src/reno_agents/inventory/schema.py`, `src/reno_agents/inventory/loader.py`, `src/reno_agents/calc/__init__.py`, `src/reno_agents/calc/money.py`, `src/reno_agents/calc/schedule.py` (only `TRADE_ORDER` for now; extended in Task 9)
- Test: `tests/inventory/test_loader.py`

**Interfaces:**
- Consumes: `Grade` (Task 2).
- Produces:
  - `calc/money.py`: `def to_money(x: Decimal) -> Decimal` (quantize `0.01`, `ROUND_HALF_UP`); `def parse_money(text: str) -> Decimal` — strips surrounding spaces, one leading currency symbol (`$ € £ ₹`), thousands commas; raises `ValueError` otherwise.
  - `calc/schedule.py`: `TRADE_ORDER: tuple[str, ...] = ("demo", "rough_in", "repairs", "paint", "flooring", "fixtures_appliances", "hardware", "clean")`
  - `schema.py`: `class InventoryItem(BaseModel, frozen=True)` with fields exactly the spec §6 columns:
    `sku, category, subcategory, item_name, brand, model, spec, unit: str; unit_cost: Decimal (>=0); currency: str; supplier: str; lead_time_days: int (>=0); grade: Grade; substitution_group: str; coverage_per_unit: Decimal (>0); coverage_unit: str; waste_pct: Decimal (0–100); approved: bool; approved_until: date`.
    `class LaborRate(BaseModel, frozen=True)`: `task_code, category, task_name, unit: str; rate: Decimal (>=0); currency: str; typical_hours_per_unit: Decimal (>=0); trade: str (must be in TRADE_ORDER)`.
    `@dataclass(frozen=True) class RowError: row: int; field: str | None; message: str` (`row` = 1-based line number in the file, header = 1).
    `@dataclass class LoadResult(Generic[T]): items: list[T]; errors: list[RowError]`; property `ok -> bool`.
  - `loader.py`: `def load_inventory(text: str, *, currency: str) -> LoadResult[InventoryItem]`;
    `def load_labor_rates(text: str, *, currency: str) -> LoadResult[LaborRate]`. Rules: strip UTF-8
    BOM; skip fully blank rows; header must contain every required column (extra columns ignored;
    missing → one `RowError(1, None, "missing columns: ...")` and no items); `approved` accepts
    `y/n/yes/no` any case; money via `parse_money`; row currency must equal `currency`; duplicate
    `sku` (or `task_code`) → error on the later row; a row with any error is excluded from `items`.

- [ ] **Step 1: Write failing tests** (helper `HEADER` = the spec's inventory column list joined by commas)

```python
from decimal import Decimal
from reno_agents.inventory.loader import load_inventory, load_labor_rates

HEADER = ("sku,category,subcategory,item_name,brand,model,spec,unit,unit_cost,currency,supplier,"
          "lead_time_days,grade,substitution_group,coverage_per_unit,coverage_unit,waste_pct,approved,approved_until")
PAINT = "PNT-001,Paint,Interior wall,Eggshell wall paint,Northfield,NF-200,Eggshell white,gallon,38.00,USD,Acme Supply,2,better,PAINT-INT-WALL,350,sq_ft,10,Y,2027-12-31"

def test_loads_valid_row():
    r = load_inventory(f"{HEADER}\n{PAINT}\n", currency="USD")
    assert r.ok and r.items[0].unit_cost == Decimal("38.00") and r.items[0].approved is True

def test_excel_quirks_accepted():
    row = PAINT.replace("38.00", '"$1,038.50"').replace(",Y,", ",y,")
    r = load_inventory(f"﻿{HEADER}\n{row}\n,,,,,,,,,,,,,,,,,,\n\n", currency="USD")
    assert r.ok and r.items[0].unit_cost == Decimal("1038.50")

def test_bad_cost_is_row_error_not_guess():
    r = load_inventory(f"{HEADER}\n{PAINT.replace('38.00', 'thirty')}\n", currency="USD")
    assert r.items == [] and r.errors[0].row == 2 and r.errors[0].field == "unit_cost"

def test_duplicate_sku_flagged_on_later_row():
    r = load_inventory(f"{HEADER}\n{PAINT}\n{PAINT}\n", currency="USD")
    assert len(r.items) == 1 and r.errors[0].row == 3 and r.errors[0].field == "sku"

def test_missing_column_rejects_file():
    r = load_inventory(HEADER.replace(",waste_pct", "") + "\n", currency="USD")
    assert r.items == [] and r.errors[0].row == 1 and "waste_pct" in r.errors[0].message

def test_currency_mismatch_is_error():
    r = load_inventory(f"{HEADER}\n{PAINT.replace('USD', 'EUR')}\n", currency="USD")
    assert r.errors[0].field == "currency"

def test_labor_trade_must_be_known():
    h = "task_code,category,task_name,unit,rate,currency,typical_hours_per_unit,trade"
    r = load_labor_rates(f"{h}\nL-PNT,Paint,Paint walls,sq_ft,1.25,USD,0.02,paint\n"
                         f"L-XXX,Other,Mystery,each,5,USD,1,plumbing_magic\n", currency="USD")
    assert len(r.items) == 1 and r.errors[0].field == "trade"
```

- [ ] **Step 2: Run** `uv run pytest tests/inventory/test_loader.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** using `csv.DictReader` over `io.StringIO(text.removeprefix("﻿"))`
  and `reader.line_num` for row numbers. Money and `approved` parsing live in
  `field_validator(mode="before")` on the models, so Pydantic errors carry the field name; convert
  `ValidationError` into `RowError`s using the first error's `loc[0]` as `field`. Currency, SKU
  duplicates and header checks are done in the loader.
- [ ] **Step 4: Run** tests + mypy. Expected: PASS.
- [ ] **Step 5: Commit** `feat: inventory and labor CSV loaders`.

---

### Task 5: Catalog — primary + 2 fallbacks

**Files:**
- Create: `src/reno_agents/inventory/catalog.py`
- Test: `tests/inventory/test_catalog.py`

**Interfaces:**
- Consumes: `InventoryItem`, `Grade`, `grade_rank`.
- Produces:
  - `@dataclass(frozen=True) class Pick: primary: InventoryItem; fallbacks: tuple[InventoryItem, ...]; fallback_shortfall: int` (`2 - len(fallbacks)`)
  - `class Catalog: def __init__(self, items: Iterable[InventoryItem]) -> None`
    - `def active(self, today: date) -> list[InventoryItem]` — `approved and approved_until >= today`
    - `def search(self, today: date, *, category: str | None = None, subcategory: str | None = None, substitution_group: str | None = None, grade: Grade | None = None) -> list[InventoryItem]` — active only, case-insensitive equality on strings
    - `def groups(self, today: date) -> dict[str, list[InventoryItem]]`
    - `def pick(self, substitution_group: str, preferred_grade: Grade, today: date) -> Pick | None` — `None` if group has no active items
  - Ordering key (spec §5.2): `(abs(grade_rank(item.grade) - grade_rank(preferred)), item.lead_time_days, item.unit_cost, item.sku)`; primary = first, fallbacks = next two.

- [ ] **Step 1: Write failing tests** (build items with a small `make(sku, grade, lead, cost, approved=True, until=date(2027,12,31), group="G")` helper using `InventoryItem.model_validate`)

```python
TODAY = date(2026, 11, 27)

def test_primary_matches_preferred_grade_then_fallbacks_by_closeness():
    cat = Catalog([make("A", "good", 3, "30"), make("B", "better", 2, "38"),
                   make("C", "best", 4, "52"), make("D", "better", 5, "35")])
    p = cat.pick("G", Grade.BETTER, TODAY)
    assert p.primary.sku == "B" and [f.sku for f in p.fallbacks] == ["D", "A"] and p.fallback_shortfall == 0

def test_expired_and_unapproved_never_picked():
    cat = Catalog([make("A", "better", 1, "10", until=date(2026, 11, 26)),
                   make("B", "better", 1, "10", approved=False), make("C", "good", 9, "99")])
    p = cat.pick("G", Grade.BETTER, TODAY)
    assert p.primary.sku == "C" and p.fallbacks == () and p.fallback_shortfall == 2

def test_approved_until_today_is_still_active():
    assert Catalog([make("A", "better", 1, "10", until=TODAY)]).pick("G", Grade.BETTER, TODAY) is not None

def test_unknown_group_returns_none():
    assert Catalog([]).pick("NOPE", Grade.BETTER, TODAY) is None

def test_tie_broken_by_sku_for_determinism():
    cat = Catalog([make("Z", "better", 1, "10"), make("Y", "better", 1, "10")])
    assert cat.pick("G", Grade.BETTER, TODAY).primary.sku == "Y"
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** tests + mypy → PASS.
- [ ] **Step 5: Commit** `feat: inventory catalog with primary and fallback picks`.

---

### Task 6: Sample data

**Files:**
- Create: `data/sample/inventory.csv`, `data/sample/labor_rates.csv`, `data/sample/README.md` (states all brands/suppliers/prices are fictional)
- Test: `tests/test_sample_data.py`

**Interfaces:**
- Consumes: `load_inventory`, `load_labor_rates`, `Catalog`, `TRADE_ORDER`.
- Produces: sample files later phases and the README quick start use.

Content rules: ~60 inventory rows; categories Paint, Flooring, Appliance, Fixture, Hardware,
Lighting, Electrical, Plumbing, Cabinetry; **every substitution group has ≥3 active approved items
as of 2026-11-27** across good/better/best; plus exactly one expired item and one `approved = N` item
(in groups that still have ≥3 active); include an electrical panel group (`ELEC-PANEL`) and a
switch/outlet group so High/Low tier examples exist; fictional brands (e.g. Northfield, Harbor Coat,
Kelvo, Securo) and suppliers (Acme Supply, BuildRight Co, ApplianceHub). Labor: one rate per task
type used by the inventory categories, every `trade` in `TRADE_ORDER`, all `USD`.

- [ ] **Step 1: Write failing tests**

```python
from datetime import date
from pathlib import Path
from reno_agents.inventory.catalog import Catalog
from reno_agents.inventory.loader import load_inventory, load_labor_rates

D = Path(__file__).resolve().parents[1] / "data" / "sample"
TODAY = date(2026, 11, 27)

def test_sample_inventory_loads_without_errors():
    r = load_inventory((D / "inventory.csv").read_text(), currency="USD")
    assert r.errors == [] and 55 <= len(r.items) <= 70

def test_every_group_has_three_active_items():
    items = load_inventory((D / "inventory.csv").read_text(), currency="USD").items
    groups = Catalog(items).groups(TODAY)
    assert groups and all(len(v) >= 3 for v in groups.values()), {k: len(v) for k, v in groups.items()}

def test_sample_includes_filter_cases():
    items = load_inventory((D / "inventory.csv").read_text(), currency="USD").items
    assert sum(not i.approved for i in items) == 1
    assert sum(i.approved and i.approved_until < TODAY for i in items) == 1
    assert any(i.substitution_group == "ELEC-PANEL" for i in items)

def test_sample_labor_loads():
    r = load_labor_rates((D / "labor_rates.csv").read_text(), currency="USD")
    assert r.errors == [] and len(r.items) >= 10
```

- [ ] **Step 2: Run** → FAIL (files missing). **Step 3: Write the two CSVs.** **Step 4: Run** all tests (incl. hygiene) → PASS.
- [ ] **Step 5: Commit** `feat: fictional sample inventory and labor rates`.

---

### Task 7: Tier rules config

**Files:**
- Create: `config/tier_rules.toml`, `src/reno_agents/domain/tiers.py`
- Test: `tests/domain/test_tiers.py`

**Interfaces:**
- Consumes: `Tier`, `Severity`.
- Produces:
  - `@dataclass(frozen=True) class TierRule: tier: Tier; description: str; examples: tuple[str, ...]`
  - `@dataclass(frozen=True) class TierRules: rules: dict[Tier, TierRule]; severity_floor: dict[Severity, Tier]`
  - `def load_tier_rules(path: Path) -> TierRules` (raises `ValueError` if any tier missing or a value isn't a valid enum)
  - `def apply_floor(proposed: Tier, severity: Severity, rules: TierRules) -> Tier` — returns the higher-impact of `proposed` and the floor (high > medium > low)
  - `def rules_as_prompt_text(rules: TierRules) -> str` — plain text block for the Planner prompt (phase 2)
- `tier_rules.toml` content: the three tier descriptions and examples verbatim from spec §5.2
  (High: whole-system failures — electrical panel, plumbing main, HVAC; security/safety — entry
  locks, smoke detectors; cosmetic upgrades that lift lease appeal — full repaint, flooring, kitchen
  refresh. Medium: single appliance or fixture replacement — dishwasher, vanity; cosmetic fixes
  limited to one room. Low: isolated single-component fixes — one switch, an outlet, a cabinet
  hinge, a drawer pull) and `[severity_floor] system_level = "high"`, `safety = "high"`.

- [ ] **Step 1: Write failing tests**

```python
from pathlib import Path
import pytest
from reno_agents.domain.enums import Severity, Tier
from reno_agents.domain.tiers import apply_floor, load_tier_rules, rules_as_prompt_text

RULES = load_tier_rules(Path(__file__).resolve().parents[2] / "config" / "tier_rules.toml")

def test_shipped_rules_have_all_tiers():
    assert set(RULES.rules) == {Tier.HIGH, Tier.MEDIUM, Tier.LOW}
    assert any("panel" in e for e in RULES.rules[Tier.HIGH].examples)
    assert any("switch" in e for e in RULES.rules[Tier.LOW].examples)

def test_system_level_and_safety_never_below_high():
    assert apply_floor(Tier.LOW, Severity.SYSTEM_LEVEL, RULES) is Tier.HIGH
    assert apply_floor(Tier.MEDIUM, Severity.SAFETY, RULES) is Tier.HIGH

def test_floor_never_lowers_a_tier():
    assert apply_floor(Tier.HIGH, Severity.MINOR, RULES) is Tier.HIGH
    assert apply_floor(Tier.LOW, Severity.MINOR, RULES) is Tier.LOW

def test_prompt_text_mentions_every_tier():
    text = rules_as_prompt_text(RULES).lower()
    assert all(t in text for t in ("high", "medium", "low"))

def test_missing_tier_rejected(tmp_path):
    p = tmp_path / "bad.toml"
    p.write_text('[tiers.high]\ndescription = "x"\nexamples = []\n')
    with pytest.raises(ValueError):
        load_tier_rules(p)
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (`tomllib`). **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: editable tier rules with severity floor`.

---

### Task 8: Quantities, costing, approval rules

**Files:**
- Create: `src/reno_agents/calc/costing.py`
- Test: `tests/calc/test_costing.py`

**Interfaces:**
- Consumes: `InventoryItem`, `LaborRate`, `Tier`, `to_money`.
- Produces:
  - `def purchase_quantity(measured: Decimal, coverage_per_unit: Decimal, waste_pct: Decimal) -> int` — `ceil(measured / coverage_per_unit * (1 + waste_pct/100))`; `ValueError` if `measured <= 0`.
  - `class MissingEstimate(Exception)`
  - `@dataclass(frozen=True) class LineCost: purchase_qty: int | None; materials: Decimal; labor: Decimal; total: Decimal`
  - `def line_cost(measured_qty: Decimal, item: InventoryItem | None, labor: LaborRate | None, estimate: Decimal | None = None) -> LineCost` — with `item`: materials = `purchase_qty × unit_cost`; labor = `rate × measured_qty` (0 if `labor` is None); with `item is None` (procurement needed): `estimate` required else `MissingEstimate`, `materials = estimate`, `purchase_qty = None`.
  - `def tier_totals(lines: Iterable[tuple[Tier, LineCost]]) -> dict[Tier, Decimal]` — all three tiers present, zero if empty.
  - `def needs_asset_manager_approval(total: Decimal, threshold: Decimal) -> bool` — `total > threshold`
  - `def change_request_needs_asset_manager(original_total: Decimal, new_total: Decimal, threshold: Decimal, pct: Decimal) -> bool` — `new_total > threshold or (new_total - original_total) > original_total * pct / 100`

- [ ] **Step 1: Write failing tests**

```python
def test_paint_example_from_spec():
    assert purchase_quantity(Decimal("420"), Decimal("350"), Decimal("10")) == 2

def test_exact_coverage_does_not_round_up():
    assert purchase_quantity(Decimal("350"), Decimal("350"), Decimal("0")) == 1

def test_zero_or_negative_measure_rejected():
    with pytest.raises(ValueError):
        purchase_quantity(Decimal("0"), Decimal("350"), Decimal("10"))

def test_line_cost_materials_plus_labor(paint_item, paint_labor):   # 38.00/gal; labor 1.25/sq_ft
    c = line_cost(Decimal("420"), paint_item, paint_labor)
    assert (c.purchase_qty, c.materials, c.labor, c.total) == (2, Decimal("76.00"), Decimal("525.00"), Decimal("601.00"))

def test_procurement_needed_line_requires_estimate():
    with pytest.raises(MissingEstimate):
        line_cost(Decimal("1"), None, None)
    assert line_cost(Decimal("1"), None, None, estimate=Decimal("1200")).total == Decimal("1200.00")

def test_tier_totals_include_empty_tiers():
    t = tier_totals([(Tier.HIGH, LineCost(1, Decimal("10"), Decimal("5"), Decimal("15")))])
    assert t == {Tier.HIGH: Decimal("15.00"), Tier.MEDIUM: Decimal("0.00"), Tier.LOW: Decimal("0.00")}

def test_threshold_is_strictly_greater():
    assert not needs_asset_manager_approval(Decimal("15000.00"), Decimal("15000"))
    assert needs_asset_manager_approval(Decimal("15000.01"), Decimal("15000"))

@pytest.mark.parametrize("orig,new,expected", [
    ("10000", "11000", False),   # +10% exactly, under threshold
    ("10000", "11000.01", True), # just over 10%
    ("14000", "15001", True),    # crosses threshold with only a +7.15% increase
    ("20000", "20500", True),    # already over threshold: any change re-approved
])
def test_change_request_rule(orig, new, expected):
    assert change_request_needs_asset_manager(Decimal(orig), Decimal(new), Decimal("15000"), Decimal("10")) is expected
```

  (`paint_item` / `paint_labor` fixtures in `tests/calc/conftest.py`, built from the Task 4 `PAINT` row and labor row `L-PNT … 1.25 … 0.02 … paint`.)

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: quantity, line cost and approval rules`.

---

### Task 9: Work calendar and schedule

**Files:**
- Modify: `src/reno_agents/calc/schedule.py`
- Test: `tests/calc/test_schedule.py`

**Interfaces:**
- Consumes: `TRADE_ORDER` (Task 4).
- Produces:
  - `class WorkCalendar: def __init__(self, workdays: frozenset[int] = frozenset({0,1,2,3,4}), holidays: frozenset[date] = frozenset())`
    - `is_workday(d: date) -> bool`; `next_workday(d: date) -> date` (returns `d` if it is one)
    - `add_working_days(start: date, days: int) -> date` — finish date of a task of `days ≥ 1` working days starting on workday `start` (start counts as day 1)
    - `working_days_between(a: date, b: date) -> int` — count of workdays in `(a, b]`; negative if `b < a`
  - `@dataclass(frozen=True) class ScheduleTask: task_id: str; trade: str; hours: Decimal; materials_ready: date | None = None`
  - `@dataclass(frozen=True) class Schedule: tasks: dict[str, tuple[date, date]]; finish: date`
  - `def build_schedule(tasks: Sequence[ScheduleTask], start: date, calendar: WorkCalendar, hours_per_day: Decimal = Decimal("8")) -> Schedule` — `ValueError` on unknown trade or empty `tasks`.
  - `def project_finish(remaining: Sequence[ScheduleTask], today: date, approval_date: date, last_done: date | None, calendar: WorkCalendar, hours_per_day: Decimal = Decimal("8")) -> date` — `remaining` holds only unfinished tasks with remaining hours; if empty returns `last_done or today`; else `build_schedule(remaining, max(today, approval_date), ...)`.finish.

Algorithm (spec §5.3 schedule rules):
```
cursor = calendar.next_workday(start)
for trade in TRADE_ORDER:
    step = [t for t in tasks if t.trade == trade]
    if not step: continue
    for t in step:
        s = max(cursor, calendar.next_workday(t.materials_ready)) if t.materials_ready else cursor
        days = max(1, ceil(t.hours / hours_per_day))
        record t -> (s, calendar.add_working_days(s, days))
    cursor = calendar.next_workday(max(finish of step) + 1 day)
finish = max of all task finishes
```

- [ ] **Step 1: Write failing tests**

```python
CAL = WorkCalendar(holidays=frozenset({date(2026, 12, 25)}))
MON = date(2026, 11, 30)

def test_add_working_days_skips_weekend():
    assert CAL.add_working_days(date(2026, 11, 26), 3) == MON           # Thu, Fri, Mon

def test_approval_on_saturday_starts_monday():
    s = build_schedule([ScheduleTask("t1", "paint", Decimal("8"))], date(2026, 11, 28), CAL)
    assert s.tasks["t1"] == (MON, MON)

def test_trades_are_sequential_same_trade_parallel():
    s = build_schedule([ScheduleTask("a", "repairs", Decimal("16")), ScheduleTask("b", "repairs", Decimal("8")),
                        ScheduleTask("c", "paint", Decimal("8"))], MON, CAL)
    assert s.tasks["a"] == (MON, date(2026, 12, 1)) and s.tasks["b"][0] == MON
    assert s.tasks["c"] == (date(2026, 12, 2), date(2026, 12, 2)) and s.finish == date(2026, 12, 2)

def test_materials_gate_start_but_past_dates_do_not_pull_earlier():
    late = build_schedule([ScheduleTask("t", "paint", Decimal("8"), materials_ready=date(2026, 12, 3))], MON, CAL)
    past = build_schedule([ScheduleTask("t", "paint", Decimal("8"), materials_ready=date(2026, 11, 1))], MON, CAL)
    assert late.tasks["t"][0] == date(2026, 12, 3) and past.tasks["t"][0] == MON

def test_holiday_skipped():
    s = build_schedule([ScheduleTask("t", "paint", Decimal("16"))], date(2026, 12, 24), CAL)
    assert s.tasks["t"] == (date(2026, 12, 24), date(2026, 12, 28))

def test_unknown_trade_rejected():
    with pytest.raises(ValueError):
        build_schedule([ScheduleTask("t", "magic", Decimal("1"))], MON, CAL)

def test_projection_with_nothing_remaining():
    assert project_finish([], date(2026, 12, 10), MON, date(2026, 12, 9), CAL) == date(2026, 12, 9)

def test_working_days_between():
    assert CAL.working_days_between(date(2026, 11, 27), MON) == 1
    assert CAL.working_days_between(MON, date(2026, 11, 27)) == -1
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: working-day calendar and trade schedule`.

---

### Task 10: Escalation rules

**Files:**
- Create: `src/reno_agents/calc/alerts.py`
- Test: `tests/calc/test_alerts.py`

**Interfaces:**
- Consumes: `EscalationKind`, `Settings` fields (passed as plain values).
- Produces:
  - `@dataclass(frozen=True) class Escalation: unit_id: str; kind: EscalationKind; key: str; magnitude: Decimal; message: str` — `key` is `"unit"` for slip/overspend, the task id for blocked.
  - `def evaluate_unit(unit_id: str, *, today: date, planned_finish: date, projected_finish: date, approved_budget: Decimal, projected_spend: Decimal, blocked_since: Mapping[str, date], slip_alert_days: int = 7, overspend_alert_pct: Decimal = Decimal("10"), blocked_alert_days: int = 2) -> list[Escalation]`
    - slip: `(projected_finish - planned_finish).days > slip_alert_days` (calendar days); magnitude = days
    - overspend: `approved_budget > 0` and `(projected_spend - approved_budget) / approved_budget * 100 > overspend_alert_pct`; magnitude = pct rounded to 0.1
    - blocked: `(today - since).days > blocked_alert_days`; magnitude = days
  - `def filter_new(candidates: Iterable[Escalation], last_sent: Mapping[tuple[str, EscalationKind, str], Decimal]) -> list[Escalation]` — keep if no previous entry or `magnitude > previous`.

- [ ] **Step 1: Write failing tests**

```python
D = date(2026, 12, 10)
base = dict(today=D, planned_finish=date(2026, 12, 1), approved_budget=Decimal("10000"),
            projected_spend=Decimal("10000"), blocked_since={})

def test_slip_of_exactly_seven_days_is_not_escalated():
    assert evaluate_unit("u1", **{**base, "projected_finish": date(2026, 12, 8)}) == []

def test_slip_of_eight_days_escalates():
    [e] = evaluate_unit("u1", **{**base, "projected_finish": date(2026, 12, 9)})
    assert e.kind is EscalationKind.SLIP and e.magnitude == Decimal("8")

def test_overspend_boundary():
    at = evaluate_unit("u1", **{**base, "projected_finish": date(2026, 12, 1), "projected_spend": Decimal("11000")})
    over = evaluate_unit("u1", **{**base, "projected_finish": date(2026, 12, 1), "projected_spend": Decimal("11000.01")})
    assert at == [] and over[0].kind is EscalationKind.OVERSPEND

def test_zero_budget_does_not_crash():
    assert evaluate_unit("u1", **{**base, "projected_finish": date(2026, 12, 1), "approved_budget": Decimal("0")}) == []

def test_blocked_more_than_two_days():
    es = evaluate_unit("u1", **{**base, "projected_finish": date(2026, 12, 1),
                                "blocked_since": {"t1": date(2026, 12, 8), "t2": date(2026, 12, 7)}})
    assert [(e.kind, e.key) for e in es] == [(EscalationKind.BLOCKED, "t2")]

def test_dedup_only_resends_when_worse():
    e = Escalation("u1", EscalationKind.SLIP, "unit", Decimal("8"), "")
    assert filter_new([e], {("u1", EscalationKind.SLIP, "unit"): Decimal("8")}) == []
    assert filter_new([e], {("u1", EscalationKind.SLIP, "unit"): Decimal("7")}) == [e]
    assert filter_new([e], {}) == [e]
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: escalation rules with dedup`.

---

### Task 11: QA metrics

**Files:**
- Create: `src/reno_agents/calc/qa_metrics.py`
- Test: `tests/calc/test_qa_metrics.py`

**Interfaces:**
- Consumes: `LineVerdict`, `QaResult`, `WorkCalendar`.
- Produces:
  - `@dataclass(frozen=True) class QaLine: line_id: str; approved_cost: Decimal; verdict: LineVerdict` (verdict is judged against the PM-recorded **installed item**, so approved swaps arrive as `done_as_specified`)
  - `def scope_deviation(lines: Sequence[QaLine]) -> Decimal` — % (2 dp) = cost of `{partial, missing, done_different_item}` ÷ cost of all lines except `not_verifiable`; `0` if denominator is 0.
  - `def photo_deviation(resolved_as_planned: Sequence[bool | None]) -> Decimal` — % of `False` among non-`None`; `None` = not verifiable; `0` if none verifiable.
  - `def budget_deviation(actual: Decimal, approved: Decimal) -> Decimal` — `(actual - approved) / approved × 100`; `ValueError` if `approved <= 0`.
  - `def timeline_deviation(planned_start: date, planned_finish: date, actual_finish: date, calendar: WorkCalendar) -> Decimal` — `working_days_between(planned_finish, actual_finish) / max(1, working_days_between(planned_start, planned_finish) + 1) × 100`.
  - `@dataclass(frozen=True) class QaOutcome: result: QaResult; flags: tuple[str, ...]; not_verifiable: int` — flags are names of metrics over threshold: `"scope"`, `"photo"`, `"budget"`, `"timeline"`.
  - `def qa_outcome(*, scope: Decimal, photo: Decimal, budget: Decimal, timeline: Decimal, not_verifiable: int, threshold: Decimal = Decimal("10")) -> QaOutcome` — precedence per plan Decisions.

- [ ] **Step 1: Write failing tests**

```python
V = LineVerdict
def L(cost, v): return QaLine("x", Decimal(cost), v)

def test_scope_deviation_excludes_unverifiable_from_both_sides():
    lines = [L("900", V.DONE_AS_SPECIFIED), L("100", V.MISSING), L("5000", V.NOT_VERIFIABLE)]
    assert scope_deviation(lines) == Decimal("10.00")

def test_different_item_counts_as_deviation():
    assert scope_deviation([L("500", V.DONE_DIFFERENT_ITEM), L("500", V.DONE_AS_SPECIFIED)]) == Decimal("50.00")

def test_all_unverifiable_gives_zero_and_needs_evidence():
    lines = [L("100", V.NOT_VERIFIABLE)]
    assert scope_deviation(lines) == Decimal("0")
    o = qa_outcome(scope=Decimal("0"), photo=photo_deviation([None]), budget=Decimal("0"),
                   timeline=Decimal("0"), not_verifiable=1)
    assert o.result is QaResult.NEEDS_EVIDENCE

def test_exactly_ten_percent_passes_just_over_flags():
    z = Decimal("0")
    assert qa_outcome(scope=Decimal("10"), photo=z, budget=z, timeline=z, not_verifiable=0).result is QaResult.PASS_
    o = qa_outcome(scope=Decimal("10.01"), photo=z, budget=z, timeline=z, not_verifiable=2)
    assert o.result is QaResult.FLAGGED and o.flags == ("scope",)

def test_budget_deviation_and_zero_budget():
    assert budget_deviation(Decimal("11500"), Decimal("10000")) == Decimal("15.00")
    with pytest.raises(ValueError):
        budget_deviation(Decimal("1"), Decimal("0"))

def test_timeline_deviation_same_day_job():
    cal = WorkCalendar()
    d = date(2026, 11, 30)
    assert timeline_deviation(d, d, date(2026, 12, 1), cal) == Decimal("100.00")

def test_under_budget_is_negative_not_flagged():
    z = Decimal("0")
    assert qa_outcome(scope=z, photo=z, budget=Decimal("-20"), timeline=z, not_verifiable=0).result is QaResult.PASS_
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** full suite `uv run pytest && uv run ruff check . && uv run mypy src` → PASS.
- [ ] **Step 5: Commit** `feat: QA deviation metrics and outcome`.

---

### Task 12: QA agents, docs sync, close-out

**Files:**
- Modify: `ARCHITECTURE.md`, `docs/design-docs/core-beliefs.md`, `docs/PLANS.md`, `docs/QUALITY_SCORE.md`, `docs/SECURITY.md`, `docs/exec-plans/tech-debt-tracker.md` — only those with A/B-graded details (CLAUDE.md Rule 1)
- Move: this plan → `docs/exec-plans/completed/` with a one-line outcome at the top (after merge)

- [ ] **Step 1: Rule 2.** Spawn `qa-functional` and `qa-adversarial` in parallel, each with
  `isolation: "worktree"`, briefed with the branch name, the diff range (`main..HEAD`), and "Phase 1
  domain core per docs/exec-plans/active/2026-11-27-phase-1-domain-core.md" — no claims that it works.
  Adversarial focus for this phase: malformed/hostile CSV (formula injection like `=HYPERLINK(...)`
  in text cells, huge files, non-UTF-8), boundary values, Decimal edge cases.
- [ ] **Step 2:** Fix every Critical/High finding in the main session; keep QA's regression tests;
  re-run the affected QA agent. Report findings by severity to the user.
- [ ] **Step 3:** Push the branch and open a PR (with user's go-ahead), PR template checklist filled.
- [ ] **Step 4: Rule 1.** Grade candidate details A/B/C and update only relevant docs. Expected A
  details: ARCHITECTURE components table (`domain`, `inventory`, `calc`) and the "agents do
  judgment, code does arithmetic" invariant; core-beliefs (strict thresholds, Decimal money, no
  invented inventory); SECURITY (secret scanning, no-personal-data hygiene test). List skipped C
  details in the PR.
- [ ] **Step 5:** After merge, move this plan to `completed/` with its outcome line; update `docs/PLANS.md`.
