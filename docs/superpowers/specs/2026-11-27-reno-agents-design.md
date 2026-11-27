# AI Reno Agents — Design

**Date:** 2026-11-27
**Status:** Draft for approval
**Framework:** Google Agent Development Kit (ADK), Python

---

## 1. Intent and why

A real estate company buys or manages apartments, renovates them, and then leases them. Today the
inspect → scope → coordinate → verify loop is manual and slow. This project is a set of four AI agents,
wrapped in a simple web app, that runs that loop:

1. **Reno Assessor Agent** finds problems from photos and videos of a unit.
2. **Reno Planner Agent** turns problems into a tiered scope using only approved inventory.
3. **Reno Coordinator Agent** runs the approved renovation: roadmap, budget, timeline, purchase orders,
   daily exec summary, escalations.
4. **Reno QA Agent** independently judges finished work against the plan and the before media.

The repository is **public and open source**. Two audiences:

- **Installers:** other renovation / property companies who clone it, add their own inventory and
  keys, and run it.
- **The author's business:** a showcase on a business page, so it must look and install like a
  well-run open-source project.

**Scale target:** about 10 new units assessed per day, which with multi-week renovations means
**100+ units active at once**. The app must handle a portfolio, not one unit at a time.

---

## 2. Users and roles (PM-led operating model)

| Role | What they do |
|---|---|
| **Field inspector** | Walks the unit, uploads photos/videos, triggers the Assessor. Uploads completion media. |
| **Renovation PM** | Owns the unit. Reviews Planner tiers, selects scope, signs off POs, updates task progress and actual costs, receives escalations. Is the "human coordinator". |
| **Asset manager** | Approves plans above the budget threshold. Receives the daily exec summary. |
| **QA reviewer** | Reviews and signs off the QA report. **Must not be the PM of that unit.** |
| **Leasing** | Sees units that are QA-passed and "Ready to lease". Read-only. |
| **Admin** | Manages users, roles, settings, inventory and labor-rate uploads. |

One user may hold several roles, but the app enforces: a user cannot QA-sign-off a unit where they
are the assigned PM.

---

## 3. Unit lifecycle

Each unit moves through fixed stages. The **web app owns this state machine**; agents never change
stage on their own — they produce outputs, and the app (or a human action) moves the stage.

```
Draft ──(media uploaded + Assessor run)──▶ Assessed
Assessed ──(Planner run)──▶ Planned
Planned ──(PM selects scope; if total ≤ threshold)──▶ Approved
Planned ──(PM selects scope; if total > threshold)──▶ Awaiting asset-manager approval ──▶ Approved
Approved ──(first PO signed)──▶ In progress
In progress ──(PM marks work complete + completion media uploaded)──▶ Complete
Complete ──(QA run)──▶ QA review
QA review ──(reviewer passes)──▶ Ready to lease
QA review ──(reviewer fails)──▶ In progress  (with the QA issue list as rework tasks)
```

Rules:
- A PM can re-run the Assessor if more media is added before planning.
- **Change requests:** while In progress, the PM can add scope lines (e.g. a problem found behind a
  wall). If the new approved total exceeds the original approval by more than the threshold rule,
  it goes back through asset-manager approval; work on other lines continues.
- Every stage change is recorded in an audit log (who, when, from, to, note).

---

## 4. Media: multiple photos and videos

- A unit accepts **many photos and many videos**, in one upload or across several visits.
- Supported: JPEG, PNG, HEIC/HEIF (converted to JPEG on upload), MP4, MOV.
- Uploader can optionally **tag a room** (Kitchen, Bath 1, Bedroom 2, Living, Entry, Exterior,
  Other). If untagged, the Assessor infers the room.
- Each media item is tagged **phase = before | progress | after**.
- **Privacy on upload:** strip EXIF metadata including GPS before storing.
- **Limits** are settings (defaults: 50 MB per photo, 500 MB per video, 100 items per upload).
  Phone-friendly upload with progress display; uploads that fail can be retried per file.

**Video analysis**
- If the configured model accepts video natively (e.g. Gemini), the video is sent as video.
- Otherwise the app **extracts key frames** with ffmpeg (scene-change detection plus a fixed
  interval, capped by a setting, default 1 frame / 3 s, max 60 frames per video) and sends frames.
- Every finding cites its evidence: `media_id` plus, for video, a **timestamp**. The UI shows the
  frame or jumps the player to that moment.
- Frame caps exist to keep model costs predictable; they are documented in the README.

---

## 5. The four agents

General principle: **agents do judgment, code does arithmetic.** Costs, totals, durations,
schedule projections and deviation percentages are computed by plain, tested Python. Agents do vision,
mapping issues to tasks, choosing items, and writing summaries. Every agent returns **structured
output** (Pydantic schemas) that the app validates before saving.

Each agent is a separate ADK agent, invoked by the app at the right stage. They share no in-memory
session; they read and write only through the database. This keeps them testable alone and keeps
QA independent.

### 5.1 Reno Assessor Agent

- **Input:** all `before` media for the unit, room tags, unit basics (bedrooms, baths, sq ft if known).
- **Does:** vision analysis across every photo and video; deduplicates the same issue seen in
  several items.
- **Output:** list of **issues**, each with: room, category (paint, flooring, appliance, electrical,
  plumbing, hardware, fixture, cabinetry, HVAC, structural, other), description, severity
  (minor / moderate / major / system-level / safety), estimated quantity where visible (e.g. wall
  area, count), confidence (0–1), evidence (media IDs + timestamps).
- Low-confidence issues (below a setting, default 0.5) are shown as "needs a human look" rather
  than dropped.
- Field inspector or PM can edit, add, or remove issues before planning. Edits are kept.

### 5.2 Reno Planner Agent

- **Input:** the unit's issues (as edited), approved inventory, labor rates, tier rules.
- **Tools:** inventory search (by category, subcategory, substitution group, grade; only
  `approved = Y` and `approved_until ≥ today`), labor-rate lookup.
- **Does:** maps each issue → one or more **scope lines** (task + inventory item + quantity +
  labor). For each line picks a **primary** item and **2 fallbacks** from the same
  `substitution_group`, ranked by grade fit for the tier and then lead time.
- **Tiers** (rules live in an editable config file; defaults below):
  - **High:** whole-system failures (electrical panel, plumbing main, HVAC), security / safety
    (entry locks, smoke detectors), and cosmetic upgrades that lift lease appeal (full repaint,
    flooring, kitchen refresh).
  - **Medium:** single appliance or fixture replacement (dishwasher, vanity), cosmetic fixes limited
    to one room.
  - **Low:** isolated single-component fixes (one switch, an outlet, a cabinet hinge, a drawer pull).
- **Output:** three tiers, each with its lines, tier cost (materials + labor, computed by code),
  and estimated duration (computed from labor hours and lead times).
- **Hard rule:** the Planner never invents an item. If no approved item fits, the line is marked
  **"No approved item — procurement needed"** with a plain description of what is needed.
- **PM selection:** the PM picks tiers and can include/exclude individual lines and swap primary for
  a fallback. The selected set is the **approved scope** once approval completes.
- **Approval threshold:** a setting (default 15,000 in the configured currency per unit). Above it,
  the asset manager must approve.

### 5.3 Reno Coordinator Agent

- **Input:** approved scope, POs, task progress, actual costs, delivery dates, progress media.
- **On approval:** builds the **roadmap** — an ordered task list with dependencies using simple trade
  ordering (demo → rough electrical/plumbing → repairs → paint → flooring → fixtures/appliances →
  hardware → clean), planned start/finish per task, material lead times.
- **Purchase orders:** drafts **one PO per supplier** from the approved lines. A PO is a document in
  the app (and downloadable PDF). **Nothing is sent to a supplier automatically.** The PM signs off
  the PO in the app; signing marks it "Issued", after which the PM places the order through their
  normal channel and records the expected delivery date.
- **Tracking (data entered by PM in the app):** task status (not started / in progress / done /
  blocked), actual cost per line or invoice, delivery dates, notes, progress media.
- **Daily run** (scheduled, time is a setting, default 07:00 local):
  - Recomputes each active unit's projected finish and projected spend (code).
  - Writes a **portfolio exec summary**: one email covering all active units — counts by stage,
    budget approved vs. spent vs. projected, units at risk, units completed, what needs a decision
    today. Sent to asset managers and PMs. Also shown on the dashboard.
- **Escalations** (sent immediately, not just in the daily summary):
  - projected finish slips **more than 7 days** past the approved plan, or
  - projected spend exceeds approved budget by **more than 10%**, or
  - a task is "blocked" for more than a setting (default 2 days).
  Escalations go to the unit's PM by email. They also appear in the next daily summary. The same
  escalation is not re-sent unless it gets worse (dedup).
- **Handoff:** when the PM marks the unit complete and at least one `after` media item exists for
  every room that has approved scope, the app moves the unit to Complete and triggers QA.

### 5.4 Reno QA Agent (independent judge)

- **Invoked only** when a unit reaches Complete.
- **Input:** approved scope (from the Planner, as approved), `before` media, `after` media, actual
  costs and dates (from the Coordinator's records). It does **not** see the Coordinator's or
  Planner's reasoning or summaries — only records and media.
- **Model:** configured separately; the docs recommend using a different model or provider from the
  Assessor for independence.
- **Checks — any one over 10% is flagged:**
  1. **Scope deviation:** each approved line is judged *done as specified / done with a different
     item / partial / missing / not verifiable from media*. Deviation % = cost of lines not done as
     specified ÷ total approved cost.
  2. **Photo comparison:** for each room with scope, before vs. after per issue — is the issue
     resolved, and does the visible item match the planned item's category, grade and spec
     (colour, finish, type)? Expressed as % of issues not resolved as planned.
  3. **Budget:** (actual − approved) ÷ approved.
  4. **Timeline:** (actual finish − planned finish) ÷ planned duration.
  Lines marked "not verifiable from media" are listed separately and count against the reviewer's
  attention, not as automatic failures.
- **Output: QA report** — an in-app page plus downloadable bundle (PDF report + approved scope +
  POs + before/after media index). Contents: overall result (Pass / Flagged), the four deviation
  figures, per-line verdicts with side-by-side before/after evidence, list of deviations over 10%,
  and recommended rework items.
- The **QA reviewer** makes the final call (Pass → Ready to lease; Fail → back to In progress with
  rework tasks). The agent recommends; the human decides.

---

## 6. Inventory and labor data

Starter format is **CSV** (opens in Excel / Google Sheets, diff-friendly in a public repo). Admins
upload a CSV in the app; the app validates it and shows row errors before replacing the active
inventory. The storage layer is behind an interface so a database table or external catalogue can
replace CSV later.

**`inventory.csv` columns:** `sku, category, subcategory, item_name, brand, model, spec, unit,
unit_cost, currency, supplier, lead_time_days, grade (good|better|best), substitution_group,
approved (Y|N), approved_until (YYYY-MM-DD)`

**`labor_rates.csv` columns:** `task_code, category, task_name, unit, rate, currency,
typical_hours_per_unit, trade`

The repo ships **sample data with fictional brands, suppliers and prices** — about 60 inventory
items across paint, flooring, appliances, fixtures, hardware, lighting, electrical, plumbing and
cabinetry, every substitution group having at least 3 approved items — plus matching labor rates.

---

## 7. Web app

- **Stack:** Python 3.11+, FastAPI, server-rendered Jinja2 templates with HTMX for interactivity
  (no JavaScript build step), SQLAlchemy with **SQLite by default** (PostgreSQL via config),
  APScheduler for the daily run, ffmpeg for video frames.
- **Screens:**
  - **Portfolio dashboard:** all units, filter by stage / PM / at-risk; key numbers.
  - **Unit page:** media gallery (photos + video player with evidence jumps), issues, plan tiers,
    approvals, roadmap, POs, budget vs. actual, timeline, audit log.
  - **Upload (mobile-first):** pick unit, pick phase, tag rooms, multi-file upload of photos and
    videos.
  - **Plan selection:** tiers side by side, include/exclude lines, swap to fallback, submit.
  - **Approvals inbox:** asset-manager approvals; PM PO sign-offs.
  - **QA review:** QA report with Pass / Fail.
  - **Leasing view:** Ready-to-lease units.
  - **Admin:** users and roles, settings, inventory and labor CSV upload.
- **Auth:** built-in accounts (hashed passwords, session cookies), role-based access. First admin
  created by a CLI command. SSO is a later option, not in v1.
- **Notifications:** email via SMTP settings. A notification interface so Slack/Teams can be added
  later.
- **Deploy:** Docker Compose for local / single server; a written guide for Google Cloud Run.
- **Media storage:** local disk by default, behind an interface so Google Cloud Storage / S3 can be
  configured.

---

## 8. Model provider flexibility

- Each agent's model is a **setting** (`ASSESSOR_MODEL`, `PLANNER_MODEL`, `COORDINATOR_MODEL`,
  `QA_MODEL`).
- Gemini models run through ADK natively. Other providers (OpenAI, Anthropic, local models via
  Ollama, etc.) run through ADK's **LiteLLM** integration.
- A small media adapter decides per model whether to send video natively or as extracted frames,
  and resizes images to the provider's limits.
- Defaults ship as Gemini so a new installer needs only one key to start.

---

## 9. Public repo, security and privacy

- **No secrets in the repo.** All keys, SMTP credentials, and the app's secret key come from
  environment variables; ship `.env.example` with placeholder values only; `.env` is git-ignored.
- **Secret scanning:** gitleaks in a pre-commit hook and in CI.
- **No personal data:** no real names, emails, addresses or phone numbers in code, docs, samples or
  tests. Sample users use `example.com` addresses. Sample media must be openly licensed or generated,
  with no people, house numbers or documents visible, and its licence recorded.
- **Uploaded media** stays in the installer's own storage; EXIF/GPS stripped on upload.
- **Repo hygiene:** README (what it is, screenshots, quick start, configuration, architecture),
  LICENSE (**Apache-2.0**, matching ADK), CONTRIBUTING, CODE_OF_CONDUCT, SECURITY (how to report
  vulnerabilities), CHANGELOG, issue and PR templates, Dependabot, GitHub Actions CI (lint, type
  check, tests, secret scan).
- **Tests:** unit tests for all arithmetic (costs, projections, deviations), state machine, CSV
  validation; agent tests with mocked model calls and fixed structured outputs; a small optional
  evaluation set of sample media with expected issues for checking Assessor quality.

---

## 10. Goals, non-goals, anti-goals

**Goals (v1)**
- Field staff can upload many photos and videos for a unit from a phone and get an issue list.
- PM gets three costed, tiered plans built only from approved inventory, each line with 2 approved
  fallbacks.
- Approvals with a configurable threshold; POs drafted per supplier, signed off by the PM.
- Portfolio-wide daily exec summary and immediate escalations (>7 days slip, >10% overspend).
- Independent QA report with four deviation checks and a human sign-off.
- Anyone can clone, set one API key, and run it with Docker in minutes using sample data.

**Non-goals (v1)**
- Sending orders or payments to suppliers automatically.
- Contractor scheduling, bidding, or a contractor portal.
- Managing leasing listings (the app only hands off "Ready to lease").
- Accounting / ERP integration.
- Native mobile apps (the web app is mobile-friendly instead).
- Multi-company SaaS hosting (one company per install).

**Anti-goals — failures even if it "works"**
- The Planner recommends an item that is not in the approved inventory.
- Money is committed without a PM sign-off.
- A secret, personal detail, or real customer media ends up in the public repo.
- QA rubber-stamps because it saw the Coordinator's view of the work.
- Alerts are so frequent that PMs ignore them.
- Model-produced numbers are trusted for money or schedule maths.

---

## 11. Approaches considered

| Approach | Trade-off | Decision |
|---|---|---|
| **A. One ADK pipeline chaining all four agents** | Natural ADK pattern, but the flow pauses for days (approvals, the work itself, QA sign-off); keeping one run open is fragile. | Rejected |
| **B. Four independent ADK agents, web app runs the workflow** | App stores each unit's stage, calls the right agent at each step, scheduler runs the daily Coordinator. Agents testable alone; QA truly independent. | **Chosen** |
| **C. Dedicated workflow engine (e.g. Temporal)** | Very robust for long processes, but another heavy service for every installer; overkill at this scale. | Rejected |

Interface options considered: ADK dev UI + CLI only (demo only, no phone upload or portfolio view),
API only (nobody can use it on its own), **simple web app** (chosen).

---

## 12. Decided by the product owner

- PM-led operating model (roles as in §2).
- About 10 units per day.
- Coordinator prepares POs for PM sign-off; no automatic ordering.
- Coordinator hands off to QA when work is complete.
- Starter inventory as a simple spreadsheet-style table.
- Tiering by impact and leasability, including cosmetic upgrades as high; single-component fixes low,
  whole-system failures high.
- Ability to use non-Gemini models, especially for photo analysis.
- Simple web app on top of the agents.
- Architecture B.
- Multiple photos and multiple videos per unit, uploaded and analysed.
- Public repo, no private details exposed.

## 13. Designer's calls (open to correction)

- CSV format; fictional sample brands/suppliers/prices; separate labor-rates sheet.
- Medium tier definition; tier rules in an editable config file.
- Approval threshold default 15,000; low-confidence threshold 0.5; blocked-task alert after 2 days.
- Escalations also on >10% projected overspend and long-blocked tasks, with dedup.
- One portfolio summary email rather than one per unit; default 07:00.
- QA deviation formulas in §5.4; reviewer cannot be that unit's PM.
- Stack (FastAPI, Jinja2 + HTMX, SQLAlchemy/SQLite, APScheduler, ffmpeg); built-in auth; SMTP email.
- Apache-2.0 licence; Docker Compose + Cloud Run guide.
- EXIF/GPS stripping; upload size limits; video frame caps.

## 14. Left to the builder

- Exact Pydantic schemas, database tables and migrations tool.
- Prompt wording for each agent, within the rules above.
- Page layout and styling (clean, responsive, accessible).
- PDF library for POs and QA reports.
- Frame-extraction details beyond the stated defaults.
- Project folder structure and package naming.
- Which Gemini model versions are the defaults.
