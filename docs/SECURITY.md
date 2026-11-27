# Security

## Threat model
- **Public repository.** Anything committed is public; a leaked key or personal detail cannot be recalled.
- **Untrusted uploads.** Inventory and labor CSVs are admin uploads but treated as hostile: text cells starting with `= + - @` or containing control characters are refused (spreadsheet formula injection), sizes are capped (300-char cells, 200 columns, 20,000 rows, 500 errors), and parse failures become row errors.
- **Untrusted model output.** From phase 2, agent output (severities, quantities, QA verdicts, photo judgements) is treated as hostile: it is validated and reconciled against records, guards fail closed, and errors are `ValueError`/`TypeError` with bounded messages.

## Secrets handling
- Never commit secrets; use environment variables / a secrets manager. `.env` is git-ignored; `.env.example` holds placeholders only.
- gitleaks runs as a pre-commit hook (`.pre-commit-config.yaml`) and over full history in CI.
- `tests/test_repo_hygiene.py` fails the build on a non-`example.com` email or a key-shaped string (Google, OpenAI/Anthropic, private key, AWS, GitHub, Slack, Stripe) in any tracked file.
- Vulnerabilities are reported via GitHub private vulnerability reporting (`SECURITY.md` at the repo root); no contact emails in the repo.

## AuthN / AuthZ
_TBD — phase 3 (built-in accounts, roles, QA reviewer ≠ unit PM)._

## Known risks
- CI downloads the gitleaks binary without a checksum, and actions are pinned by tag, not commit SHA (TD-004).
- Formula-like text hidden behind invisible characters (zero-width space, BOM, bidi marks) passes the CSV guard; any export must still escape cells (TD-001).
- `.gitignore` does not yet cover `*.pem`, `*.key` or service-account JSON; add before phase 2 brings Google credentials (TD-004).
