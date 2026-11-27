# Multi-Agent AI Renovation

Open-source AI agents that run the apartment renovation loop — **inspect → scope → coordinate → verify** — for real estate teams that renovate units before leasing them.

> **Status: Phase 1 — domain core.** The design is accepted. This phase ships the tested rules and
> maths every agent relies on (unit lifecycle, inventory loading, item picks, costing, approvals,
> schedule, escalations, QA metrics). The agents (phase 2) and web app (phase 3) come next.

## What it does

Four agents, built on [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/) and wrapped in a simple web app:

| Agent | Job |
|-------|-----|
| **Reno Assessor** | Finds problems from photos and videos of a unit, citing the photo or video timestamp for each one |
| **Reno Planner** | Turns those problems into tiered scopes using only approved inventory and labor rates |
| **Reno Coordinator** | Runs the approved renovation: roadmap, budget, timeline, purchase orders, daily summary, escalations |
| **Reno QA** | Independently judges finished work against the plan and the "before" media |

Agents do the judgment; plain, tested code does the arithmetic (costs, totals, schedules). People stay in charge of every approval and stage change. It's built for a portfolio of 100+ units in progress at once, not one unit at a time.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+.

```bash
git clone https://github.com/grassurntech/multi_agent_ai_renovation.git
cd multi_agent_ai_renovation
uv sync
uv run pytest
```

Fictional sample inventory and labor rates live in [`data/sample/`](data/sample/); tier rules are
in [`config/tier_rules.toml`](config/tier_rules.toml). Settings are read from `RENO_*` environment
variables — see [`.env.example`](.env.example).

## Planned stack

Python 3.11+ · FastAPI · Jinja2 + HTMX · SQLAlchemy (SQLite by default, PostgreSQL optional) · ffmpeg · uv · Nixpacks / Docker.
Models are configurable per agent: Gemini by default, with other providers through LiteLLM.

## Documentation

- [CLAUDE.md](CLAUDE.md) — table of contents for all project docs, plus the contribution rules (QA agents and docs sync)
- [ARCHITECTURE.md](ARCHITECTURE.md) — system map
- [Full system design](docs/design-docs/reno-agents-system.md) — roles, unit lifecycle, the four agents, media, inventory, web app

## License

[Apache-2.0](LICENSE)
