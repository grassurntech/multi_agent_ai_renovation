"""Editable tier rules (``config/tier_rules.toml``) and the severity floor."""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reno_agents.domain.enums import Severity, Tier

# Higher number = higher impact.
_IMPACT = {Tier.LOW: 0, Tier.MEDIUM: 1, Tier.HIGH: 2}


@dataclass(frozen=True)
class TierRule:
    tier: Tier
    description: str
    examples: tuple[str, ...]


@dataclass(frozen=True)
class TierRules:
    rules: dict[Tier, TierRule]
    severity_floor: dict[Severity, Tier]


def _enum(kind: type[Tier] | type[Severity], value: Any, where: str) -> Any:
    try:
        return kind(value)
    except ValueError:
        allowed = ", ".join(m.value for m in kind)
        raise ValueError(f"{where}: {value!r} is not one of {allowed}") from None


def load_tier_rules(path: Path) -> TierRules:
    """Read and validate a tier rules TOML file. Raises ``ValueError`` on any problem."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))  # TOMLDecodeError is a ValueError
    tiers_raw = data.get("tiers")
    if not isinstance(tiers_raw, dict):
        raise ValueError("tier rules need a [tiers] table")

    rules: dict[Tier, TierRule] = {}
    for name, body in tiers_raw.items():
        tier = _enum(Tier, name, "tiers")
        if not isinstance(body, dict):
            raise ValueError(f"tiers.{name} must be a table")
        description = body.get("description")
        examples = body.get("examples", [])
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"tiers.{name}.description must be non-empty text")
        if not isinstance(examples, list) or not all(isinstance(e, str) for e in examples):
            raise ValueError(f"tiers.{name}.examples must be a list of text")
        rules[tier] = TierRule(tier, description.strip(), tuple(examples))
    missing = [t.value for t in Tier if t not in rules]
    if missing:
        raise ValueError(f"tier rules are missing tiers: {', '.join(missing)}")

    floor_raw = data.get("severity_floor", {})
    if not isinstance(floor_raw, dict):
        raise ValueError("[severity_floor] must be a table")
    floor = {
        _enum(Severity, sev, "severity_floor"): _enum(Tier, tier, f"severity_floor.{sev}")
        for sev, tier in floor_raw.items()
    }
    return TierRules(rules, floor)


def apply_floor(proposed: Tier, severity: Severity, rules: TierRules) -> Tier:
    """Raise ``proposed`` to the severity's floor if it is below it; never lower it."""
    floor = rules.severity_floor.get(severity)
    if floor is None or _IMPACT[proposed] >= _IMPACT[floor]:
        return proposed
    return floor


def rules_as_prompt_text(rules: TierRules) -> str:
    """Plain-text tier rules for the Planner prompt."""
    lines = ["Each scope line goes in exactly one tier, by the impact of the issue it fixes."]
    for tier in (Tier.HIGH, Tier.MEDIUM, Tier.LOW):
        rule = rules.rules[tier]
        lines.append(f"{tier.value.capitalize()}: {rule.description}")
        if rule.examples:
            lines.append(f"  Examples: {', '.join(rule.examples)}.")
    for severity, tier in rules.severity_floor.items():
        label = severity.value.replace("_", "-")
        lines.append(f"Issues of severity {label} are always at least {tier.value} tier.")
    return "\n".join(lines)
