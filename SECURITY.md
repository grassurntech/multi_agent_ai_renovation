# Security policy

## Supported versions

Only the latest `main` branch receives security fixes.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's **private vulnerability reporting**:
open the repository's **Security** tab and choose **Report a vulnerability**. Do not open a public
issue for a security problem.

Include what you found, how to reproduce it, and the impact you expect. We aim to acknowledge
reports within a few working days.

## What not to include

- Real tenant or unit photos and videos, addresses, or anyone's personal details.
- API keys, passwords, session secrets, or other credentials (yours or anyone else's).
- Real supplier price lists or contracts.

If a report needs sample data, use fictional data like the files in `data/sample/`.

## Project safeguards

- Secrets come only from environment variables; `.env.example` holds placeholders only.
- gitleaks runs in a pre-commit hook and in CI.
- `tests/test_repo_hygiene.py` fails the build if a tracked file contains a non-example email
  address or a key-like string.
