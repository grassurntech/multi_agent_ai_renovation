# Architecture

Top-level map of the system. Keep this file short; deep dives belong in `docs/design-docs/`.

## System overview
Four AI agents (Reno Assessor, Planner, Coordinator, QA) run the apartment renovation loop — inspect → scope → coordinate → verify — inside a simple web app that owns each unit's stage. Agents do judgment; a plain, tested domain core does every calculation. Full design: [reno-agents-system.md](docs/design-docs/reno-agents-system.md).

Built so far: **phase 1, the domain core** (no AI, database or web code). Phase 2 adds the agents, DB, media pipeline and job queue; phase 3 the web app.

## Components
| Component | Responsibility | Location | Owner doc |
|-----------|----------------|----------|-----------|
| Settings | `RENO_*` environment settings with design defaults and range checks | `src/reno_agents/config.py` | [design §5](docs/design-docs/reno-agents-system.md) |
| Domain | Enums, unit lifecycle state machine, tier rules + severity floor | `src/reno_agents/domain/`, `config/tier_rules.toml` | design §3, §5.2 |
| Inventory | CSV loaders for inventory and labor rates; catalog picks (primary + 2 fallbacks) | `src/reno_agents/inventory/` | design §5.2, §6 |
| Calc | Money, costing and approval rules, working-day schedule, escalations, QA metrics | `src/reno_agents/calc/` | design §3, §5.2–5.4 |
| Sample data | Fictional inventory and labor rates | `data/sample/` | `data/sample/README.md` |

## Data flow
Phase 1 is a library: callers (agents in phase 2, the web app in phase 3) pass records and judgements in and get decisions and numbers back. Typical paths: inventory CSV → loader → catalog pick → line cost → tier totals → lifecycle `scope_submitted`; approval date → schedule → projected finish → escalations → dedup; approved scope + QA verdicts/photo judgements → QA outcome.

## Key boundaries & invariants
- **Agents do judgment, code does arithmetic** — no model-produced number is used for money or schedule maths.
- **The web app owns the stage machine**; agents never change a unit's stage (`domain/lifecycle.py` only answers "what next, or refuse").
- **Records beat model output**: QA costs, issue lists and recorded swaps come from records; the QA agent supplies only verdicts and photo judgements, reconciled by id.
- **Only approved, unexpired inventory** is ever picked (`inventory/catalog.py`).
- Phase 1 code makes no network, database or model calls.

## External dependencies
| Service | Purpose | Reference |
|---------|---------|-----------|
| None in phase 1 | Runtime deps are `pydantic` and `pydantic-settings` only | `pyproject.toml` |
| GitHub Actions + gitleaks | CI: lint, types, tests, secret scan | `.github/workflows/ci.yml` |
