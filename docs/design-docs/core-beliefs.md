# Core Beliefs

The non-negotiable principles behind how this project is built. When a decision is unclear, check it against these.

1. **Agents do judgment, code does arithmetic.** Costs, quantities, totals, schedules, alerts and QA percentages are computed by tested code in `src/reno_agents/`; a model-produced number is never trusted for money or schedule maths.
2. **Records beat model output.** Where an agent's output meets the records (approved scope, costs, issues, recorded swaps), the records decide; the agent supplies judgements only, matched to records by id.
3. **Refuse, don't guess.** Malformed or ambiguous input (a CSV cell, a setting, a model value) is an error with a location, never a silent best guess.
4. **Safety guardrails fail closed.** A missing or unrecognised input to a guard (approval totals, after-media check, severity floor, recorded swaps) blocks or flags; it never lets work through.
5. **Never invent inventory.** Only approved, unexpired items are ever picked; no fit means "procurement needed".
6. **Money is `Decimal`; "more than" is strictly `>`.** Amounts round half-up to cents; a value exactly on a threshold (15,000.00, 10%, 7 days, 2 days) does not trigger it.
7. **Public by default.** No secrets, personal data, real vendor prices or tenant media in the repo; sample data is fictional.

## Trade-offs we accept
- Strict CSV parsing refuses some things spreadsheets emit (dates with times, `$` for unlisted dollar currencies, line breaks in cells); admins fix the file rather than the code guessing.
- Value and size caps (e.g. unit cost 1,000,000, 20,000 CSV rows) refuse rare real values so every calculation stays finite and fast.
- QA percentages are shown rounded up to 2 decimals, so a figure can read up to 0.01 high; in exchange a value just over the threshold is never shown as on it.
- A blocked task alerts once per blocking episode rather than daily, to keep alerts rare enough to be read.
