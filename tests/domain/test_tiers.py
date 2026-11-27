from pathlib import Path

import pytest

from reno_agents.domain.enums import Severity, Tier
from reno_agents.domain.tiers import apply_floor, load_tier_rules, rules_as_prompt_text

RULES = load_tier_rules(Path(__file__).resolve().parents[2] / "config" / "tier_rules.toml")
GOOD_TIERS = """
[tiers.high]
description = "h"
examples = ["a"]
[tiers.medium]
description = "m"
examples = []
[tiers.low]
description = "l"
examples = []
"""


def test_shipped_rules_have_all_tiers() -> None:
    assert set(RULES.rules) == {Tier.HIGH, Tier.MEDIUM, Tier.LOW}
    assert any("panel" in e for e in RULES.rules[Tier.HIGH].examples)
    assert any("switch" in e for e in RULES.rules[Tier.LOW].examples)
    assert RULES.severity_floor == {Severity.SYSTEM_LEVEL: Tier.HIGH, Severity.SAFETY: Tier.HIGH}


def test_system_level_and_safety_never_below_high() -> None:
    assert apply_floor(Tier.LOW, Severity.SYSTEM_LEVEL, RULES) is Tier.HIGH
    assert apply_floor(Tier.MEDIUM, Severity.SAFETY, RULES) is Tier.HIGH


def test_floor_never_lowers_a_tier() -> None:
    assert apply_floor(Tier.HIGH, Severity.MINOR, RULES) is Tier.HIGH
    assert apply_floor(Tier.LOW, Severity.MINOR, RULES) is Tier.LOW


def test_prompt_text_mentions_every_tier() -> None:
    text = rules_as_prompt_text(RULES).lower()
    assert all(t in text for t in ("high", "medium", "low"))
    assert "electrical panel" in text


def test_missing_tier_rejected(tmp_path: Path) -> None:
    p = tmp_path / "bad.toml"
    p.write_text('[tiers.high]\ndescription = "x"\nexamples = []\n')
    with pytest.raises(ValueError):
        load_tier_rules(p)


@pytest.mark.parametrize(
    "extra",
    [
        '[severity_floor]\nsystem_level = "highest"\n',
        '[severity_floor]\ncatastrophic = "high"\n',
        '[tiers.urgent]\ndescription = "x"\nexamples = []\n',
    ],
)
def test_invalid_enum_values_rejected(tmp_path: Path, extra: str) -> None:
    p = tmp_path / "bad.toml"
    p.write_text(GOOD_TIERS + extra)
    with pytest.raises(ValueError):
        load_tier_rules(p)


def test_malformed_toml_is_value_error(tmp_path: Path) -> None:
    p = tmp_path / "bad.toml"
    p.write_text("[tiers.high\n")
    with pytest.raises(ValueError):
        load_tier_rules(p)


def test_examples_must_be_strings(tmp_path: Path) -> None:
    p = tmp_path / "bad.toml"
    p.write_text(GOOD_TIERS.replace('examples = ["a"]', "examples = [1]"))
    with pytest.raises(ValueError):
        load_tier_rules(p)
