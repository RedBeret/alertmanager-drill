"""Loading and validating the declared drill contract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from . import config

REQUIRED_RULE_FIELDS = (
    "alert",
    "rule_file",
    "break_path",
    "fix_path",
    "max_fire_seconds",
    "max_resolve_seconds",
    "receiver",
)


class ContractError(ValueError):
    """Raised when the contract is missing something the drill needs to compare."""


@dataclass(frozen=True)
class RuleContract:
    alert: str
    rule_file: str
    break_path: str
    fix_path: str
    max_fire_seconds: int
    max_resolve_seconds: int
    receiver: str
    labels: dict[str, str]
    annotations: tuple[str, ...]
    expect_suppressed: bool


@dataclass(frozen=True)
class Contract:
    version: int
    stack: dict[str, str]
    rules: tuple[RuleContract, ...]


def load(path: Path | None = None) -> Contract:
    source = path or config.CONTRACT
    if not source.is_file():
        raise ContractError(f"contract not found at {source}")
    raw = yaml.safe_load(source.read_text(encoding="utf-8")) or {}

    if raw.get("version") != 1:
        raise ContractError(f"unsupported contract version: {raw.get('version')!r}")
    if not raw.get("rules"):
        raise ContractError("contract declares no rules, so it would pass without proving anything")

    rules = []
    for entry in raw["rules"]:
        missing = [field for field in REQUIRED_RULE_FIELDS if entry.get(field) in (None, "")]
        if missing:
            raise ContractError(
                f"rule {entry.get('alert', '<unnamed>')!r} is missing: {', '.join(missing)}"
            )
        rules.append(
            RuleContract(
                alert=entry["alert"],
                rule_file=entry["rule_file"],
                break_path=entry["break_path"],
                fix_path=entry["fix_path"],
                max_fire_seconds=int(entry["max_fire_seconds"]),
                max_resolve_seconds=int(entry["max_resolve_seconds"]),
                receiver=entry["receiver"],
                labels=dict(entry.get("labels") or {}),
                annotations=tuple(entry.get("annotations") or ()),
                expect_suppressed=bool(entry.get("expect_suppressed", False)),
            )
        )

    return Contract(
        version=raw["version"],
        stack=dict(raw.get("stack") or {}),
        rules=tuple(rules),
    )
