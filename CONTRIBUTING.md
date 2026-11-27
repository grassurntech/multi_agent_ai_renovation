# Contributing

Thanks for helping. This project is public, so please read the data rules before your first commit.

## Set up

1. Install [uv](https://docs.astral.sh/uv/).
2. `uv sync` — creates `.venv` and installs the package with its dev tools.
3. `uv tool install pre-commit` (or `pip install pre-commit`), then `pre-commit install` to run
   gitleaks and ruff on every commit.

## Check your change

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

All four run in CI and must pass.

## Branches and pull requests

- Branch from `main`; never commit to `main` directly.
- Keep each pull request to one purpose and fill in the PR template checklist.
- Write the failing test first for new behaviour and bug fixes.

## Data rules

- **Never commit real customer media, addresses, names, emails or phone numbers.** Use
  `example.com` for any email address.
- **Never commit real vendor pricing or supplier names.** Sample data is fictional.
- Never commit secrets. Keys belong in your local `.env`, which is git-ignored.

## Review rules (from CLAUDE.md)

1. **Independent QA after every dev task.** A functional QA pass (unit, integration, regression)
   and an adversarial pass (malformed input, prompt injection, rogue tool calls, limit abuse) run
   before a pull request. Critical and High findings are fixed first; regression tests QA writes
   are kept.
2. **Docs sync on every ship or PR.** Update only the docs the change affects, as mapped in
   `CLAUDE.md`.
