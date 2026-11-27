# CLAUDE.md — AI Reno Agents

This file is the **table of contents** for the project. Read it first, then open only the docs relevant to the task. Keep this file short: it points to detail, it doesn't hold it.

## Table of contents

| File | What it covers | Read when… |
|------|----------------|------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System map: components, data flow, boundaries | Touching more than one component, or adding one |
| **Design docs** | | |
| [docs/design-docs/index.md](docs/design-docs/index.md) | Index of all design docs + status | Looking for a past design decision |
| [docs/design-docs/core-beliefs.md](docs/design-docs/core-beliefs.md) | Guiding principles and accepted trade-offs | Any non-obvious design choice |
| **Execution plans** | | |
| [docs/PLANS.md](docs/PLANS.md) | How plans are written and moved | Starting multi-step work |
| [docs/exec-plans/active/](docs/exec-plans/active/) | Plans in progress | Resuming work |
| [docs/exec-plans/completed/](docs/exec-plans/completed/) | Shipped plans with outcomes | Understanding why something was built |
| [docs/exec-plans/tech-debt-tracker.md](docs/exec-plans/tech-debt-tracker.md) | Known debt, impact, owner | Taking a shortcut, or paying one down |
| **Product** | | |
| [docs/PRODUCT_SENSE.md](docs/PRODUCT_SENSE.md) | Target users, problems, prioritization | Deciding what/whether to build |
| [docs/product-specs/index.md](docs/product-specs/index.md) | Index of product specs + status | Building a user-facing feature |
| [docs/product-specs/new-user-onboarding.md](docs/product-specs/new-user-onboarding.md) | Onboarding flow spec | Working on first-run experience |
| **Engineering standards** | | |
| [docs/DESIGN.md](docs/DESIGN.md) | Visual/interaction standards, tokens | UI or styling work |
| [docs/FRONTEND.md](docs/FRONTEND.md) | Frontend stack and conventions | Frontend code |
| [docs/RELIABILITY.md](docs/RELIABILITY.md) | SLOs, failure modes, runbooks | Error handling, infra, ops |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model, secrets, auth | Auth, data handling, secrets, dependencies |
| [docs/QUALITY_SCORE.md](docs/QUALITY_SCORE.md) | Quality grade per area | Before/after a change that affects an area's quality |
| **Generated & references** | | |
| [docs/generated/db-schema.md](docs/generated/db-schema.md) | DB schema (generated — never hand-edit) | Querying or migrating data |
| [docs/references/](docs/references/) | Vendor `llms.txt` references (design system, Nixpacks, uv) | Using one of those tools |

| **QA agents** | | |
| [.claude/agents/qa-functional.md](.claude/agents/qa-functional.md) | Unit, integration, regression testing agent | Run by Rule 2 |
| [.claude/agents/qa-adversarial.md](.claude/agents/qa-adversarial.md) | Break-it agent: prompt injection, rogue tool calls, malformed input | Run by Rule 2 |

When a new doc is added anywhere under `docs/`, add a row here and in the relevant `index.md`.

# NON-NEGOTIABLE RULES

These two rules are mandatory on every task. They cannot be skipped, shortened, or deferred unless the user explicitly says so for that specific task.

**Workflow order:** dev task complete → **Rule 2 (QA agents)** → fix findings → re-run QA → commit / push / PR → **Rule 1 (docs sync)**.

## Rule 1: Sync the relevant docs every time we ship or PR

**Trigger:** as soon as something ships, or a commit is pushed and a PR is opened or updated. Not on failed pushes or local-only commits.

**Analyse first, then locate, then write.** Never update every doc. Never write before steps 1–2 are done.

1. **Analyse** — From the diff, list candidate details (what changed and why). Map each to the doc(s) it belongs in using the table below. Only files with at least one mapped detail are "relevant"; leave every other file untouched.
2. **Grade** — Score each candidate detail before writing anything:
   - **A — Must record:** changes how someone builds, runs, or reasons about the system (new component, API/contract change, schema change, new principle, new risk, shipped/changed spec, new debt).
   - **B — Record briefly:** useful context, one line at most (minor convention, small behaviour change).
   - **C — Skip:** implementation detail visible in the code or git history (refactors, renames, test tweaks, formatting, bug-fix mechanics).
3. **Update** — Write only A and B details, into only the relevant files. Edit existing sections in place rather than appending logs; replace stale statements instead of adding new ones beside them. Keep each update to the minimum lines needed. Update "Last updated" dates where a file has one.
4. **Report** — In the PR (or as a follow-up commit `docs: sync after <PR>`), list which files were updated and which detail was skipped as C, so the grading is reviewable.

**Change → doc map**

| Change in the PR | Update |
|------------------|--------|
| New/removed component, service, or data flow | `ARCHITECTURE.md` |
| Significant design decision or principle | `docs/design-docs/` (+ `index.md`) |
| Plan step completed / plan shipped | `docs/exec-plans/active/` → move to `completed/`; `docs/PLANS.md` |
| Shortcut taken or debt paid down | `docs/exec-plans/tech-debt-tracker.md` |
| DB migration | Regenerate `docs/generated/db-schema.md` |
| User-facing feature built/changed | Matching file in `docs/product-specs/` (+ `index.md`) |
| UI tokens, components, patterns | `docs/DESIGN.md` |
| Frontend stack or convention | `docs/FRONTEND.md` |
| Error handling, retries, monitoring, infra | `docs/RELIABILITY.md` |
| Auth, secrets, permissions, dependency risk | `docs/SECURITY.md` |
| Area quality materially better/worse | `docs/QUALITY_SCORE.md` |
| New doc added | This file's table of contents |

**Don't:** bloat docs with changelogs, restate code, duplicate a detail across files (record it once, link from elsewhere), or touch docs the PR didn't affect.

## Rule 2: Independent QA agents after every dev task

**Trigger:** a dev task is complete (code written, builds, author's own checks pass) — before it is committed for PR.

1. **Spawn both QA subagents in parallel**, each in its own worktree (`isolation: "worktree"`), against the latest commit of the working branch:
   - `qa-functional` — unit, integration, and **regression** testing.
   - `qa-adversarial` — tries to break the code and the agents: prompt injection (direct and indirect), unexpected/malformed tool calls, malformed input, abuse of limits.
2. **Brief them with the code, not a conclusion.** Give the branch, the diff range, and what the task was meant to do. Do not tell them it works or what to expect — they must form their own view.
3. **They report, they don't fix.** QA agents may add tests and repro scripts, but never change product code.
4. **Gate:** no PR while any **Critical** or **High** finding is open, unless the user explicitly accepts the risk. Fix the findings in the main session, then re-run the affected QA agent to confirm.
5. **Keep the tests.** New regression tests that QA writes for real bugs get merged with the fix, so the bug can't return.
6. **Report to the user** — findings by severity, what was fixed, what is still open. Feed lasting results into Rule 1 (`docs/QUALITY_SCORE.md`, `docs/SECURITY.md`, `docs/RELIABILITY.md`, `tech-debt-tracker.md`) as relevant.
