from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from alertdrill import config, contract


def write(tmp_path: Path, body: str) -> Path:
    target = tmp_path / "contract.yaml"
    target.write_text(textwrap.dedent(body), encoding="utf-8")
    return target


def test_committed_contract_loads():
    loaded = contract.load()
    assert loaded.version == 1
    assert loaded.rules, "the committed contract must declare at least one rule"


def test_every_declared_rule_file_exists():
    for rule in contract.load().rules:
        assert (config.ROOT / rule.rule_file).is_file(), rule.rule_file


def test_every_declared_alert_exists_in_its_rule_file():
    """A contract naming an alert that no rule defines would pass vacuously."""
    import yaml

    for rule in contract.load().rules:
        raw = yaml.safe_load((config.ROOT / rule.rule_file).read_text(encoding="utf-8"))
        defined = {r["alert"] for group in raw["groups"] for r in group["rules"]}
        assert rule.alert in defined, f"{rule.alert} is declared but not defined"


def test_missing_file_is_rejected(tmp_path: Path):
    with pytest.raises(contract.ContractError, match="not found"):
        contract.load(tmp_path / "absent.yaml")


def test_unsupported_version_is_rejected(tmp_path: Path):
    path = write(tmp_path, """
        version: 99
        rules: []
        """)
    with pytest.raises(contract.ContractError, match="unsupported contract version"):
        contract.load(path)


def test_empty_rule_set_is_rejected(tmp_path: Path):
    """An empty contract would report success without proving anything."""
    path = write(tmp_path, """
        version: 1
        rules: []
        """)
    with pytest.raises(contract.ContractError, match="no rules"):
        contract.load(path)


def test_rule_missing_a_required_field_is_rejected(tmp_path: Path):
    path = write(tmp_path, """
        version: 1
        rules:
          - alert: Incomplete
            rule_file: lab/prometheus/rules/drill.rules.yml
            break_path: /break
            fix_path: /fix
            max_fire_seconds: 60
        """)
    with pytest.raises(contract.ContractError, match="max_resolve_seconds"):
        contract.load(path)
