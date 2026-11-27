# Quality Score

Current quality grade per area. Re-grade when a PR materially changes an area.

| Area | Grade (A–F) | Last graded | Gaps |
|------|-------------|-------------|------|
| Domain (lifecycle, tiers) | A | 2026-11-27 | Tier-rules file can drop/weaken the severity floor (TD-002) |
| Inventory (CSV loaders, catalog) | B | 2026-11-27 | Strict parsing refuses some legitimate spreadsheet output; invisible-prefix formulas (TD-001) |
| Calc (costing, schedule, alerts, QA metrics) | B | 2026-11-27 | Overspend alert depends on caller Decimal precision; `recorded_swaps` None/generator handling (TD-003) |
| Repo hygiene and CI | B | 2026-11-27 | gitleaks download unverified; actions not SHA-pinned (TD-004) |

All areas: 567 tests incl. QA-agent regression tests; known Lows pinned as strict xfail in `tests/qa/`.

Grading: **A** solid, tested, documented · **B** works, minor gaps · **C** works, notable gaps · **D** fragile · **F** broken/missing.
