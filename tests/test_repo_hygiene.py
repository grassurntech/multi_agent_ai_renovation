"""Public-repo hygiene: no real emails, no key-like strings, placeholder-only env example."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_EMAIL_DOMAINS = {"example.com", "example.org", "example.net"}
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".mp4", ".mov", ".lock"}
KEY_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{35}"),  # Google API key
    re.compile(r"sk-(ant-)?[A-Za-z0-9_\-]{20,}"),  # OpenAI / Anthropic style
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]


def tracked_text_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    files = [ROOT / p for p in out.stdout.splitlines()]
    return [f for f in files if f.is_file() and f.suffix not in BINARY_SUFFIXES]


def test_no_real_email_addresses() -> None:
    email = re.compile(r"[A-Za-z0-9._%+\-]+@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})")
    offenders = [
        (f.name, m.group(0))
        for f in tracked_text_files()
        for m in email.finditer(f.read_text(errors="ignore"))
        if m.group(1).lower() not in ALLOWED_EMAIL_DOMAINS
    ]
    assert offenders == []


def test_no_key_like_strings() -> None:
    offenders = [
        (f.name, p.pattern)
        for f in tracked_text_files()
        for p in KEY_PATTERNS
        if p.search(f.read_text(errors="ignore"))
    ]
    assert offenders == []


def test_env_example_has_only_placeholders() -> None:
    for line in (ROOT / ".env.example").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        allowed = {"changeme", "USD", "15000", "better"}
        assert value == "" or value.startswith("your-") or value in allowed, key


def test_required_public_repo_files_exist() -> None:
    for name in [
        "README.md",
        "LICENSE",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "SECURITY.md",
        "CHANGELOG.md",
        ".env.example",
        ".github/workflows/ci.yml",
    ]:
        assert (ROOT / name).is_file(), name
