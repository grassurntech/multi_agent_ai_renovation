# Tech Debt Tracker

| ID | Description | Area | Impact (H/M/L) | Added | Plan / Owner |
|----|-------------|------|----------------|-------|--------------|
| TD-001 | CSV text guard: formulas behind invisible characters (ZWSP/BOM/bidi) and U+2028/9 pass; legitimate text starting with `-`/`@`/`+` (e.g. `-20F rated`) is refused — prefer escaping on export; also dates with a time part, `$` for unlisted dollar currencies, `1,000` in coverage, Alt+Enter line breaks are refused; SKU dedup casefold/NFKC quirks | Inventory | L | 2026-11-27 | Before phase 3 CSV upload/export |
| TD-002 | Severity floor can be dropped or lowered by the tier-rules TOML, mutated after load, or bypassed with a str-keyed table / str-subclass severity; tier strings not normalised like severities | Domain | M | 2026-11-27 | Before phase 2 Planner |
| TD-003 | QA/alerts edge cases: `recorded_swaps=None` raises TypeError and a generator is consumed; overspend alert and threshold check depend on caller Decimal precision; >60-digit costs; zero-cost deviating line hidden beside priced lines; zero approved budget skips overspend; ids not normalised for alert dedup; `date.min` timeline overflow; epoch/datetime `RENO_HOLIDAYS`; falsy `rooms_missing_after_media` | Calc / Settings | L | 2026-11-27 | Phase 2 wiring |
| TD-004 | CI/repo: gitleaks binary downloaded without checksum; actions pinned by tag not SHA; `.gitignore` lacks `*.pem`/`*.key`/service-account JSON; commit-author emails not scanned; LICENSE has no project copyright line | Repo | L | 2026-11-27 | Before phase 2 |
| TD-005 | No `(QA_REVIEW, QA_RUN)` re-run after "Needs evidence" without recording a failure; `QaOutcome` lacks not-verifiable line ids and budget/timeline figures needed for the §5.4 report | Domain / Calc | M | 2026-11-27 | Phase 2/3 QA report |

Each row's pinned tests live in `tests/qa/` as strict xfail. Remove rows when resolved; note the PR that fixed it in the commit message.
