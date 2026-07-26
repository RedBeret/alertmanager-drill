"""The negative fixtures must stay rejectable.

Every fixture here exists to prove a validator is still doing something. These tests are
static and cheap: they confirm the files exist, are registered, and are not accidentally
sitting where the real validation would pick them up. Whether the validators actually
reject them is checked by `alertctl validate`, which needs Docker.
"""

from __future__ import annotations

import yaml

from alertdrill import config


def test_every_registered_rule_fixture_exists():
    for name in config.NEGATIVE_RULE_FIXTURES:
        assert (config.FIXTURES / name).is_file(), name


def test_every_registered_alertmanager_fixture_exists():
    for name in config.NEGATIVE_ALERTMANAGER_FIXTURES:
        assert (config.FIXTURES / name).is_file(), name


def test_there_is_at_least_one_fixture_of_each_kind():
    """An empty list would make the second phase of validate pass without checking."""
    assert config.NEGATIVE_RULE_FIXTURES
    assert config.NEGATIVE_ALERTMANAGER_FIXTURES


def test_no_fixture_sits_in_the_real_rules_directory():
    """A negative fixture inside lab/prometheus/rules would be loaded by Prometheus and
    would break the stack rather than prove anything."""
    for name in config.NEGATIVE_RULE_FIXTURES:
        assert not (config.RULES_DIR / name).exists(), name


def test_rule_fixtures_are_not_silently_valid():
    """Cheap structural check so a fixture cannot be edited into something valid without
    the edit being obvious. The real proof is promtool rejecting them in validate."""
    for name in config.NEGATIVE_RULE_FIXTURES:
        raw = yaml.safe_load((config.FIXTURES / name).read_text(encoding="utf-8"))
        rules = [rule for group in raw["groups"] for rule in group["rules"]]
        assert rules, name
        # Each fixture is broken by either having no expr at all or an unparseable one.
        assert any("expr" not in rule or " is not(" in str(rule.get("expr", "")) for rule in rules)


def test_alertmanager_fixture_routes_to_an_undefined_receiver():
    for name in config.NEGATIVE_ALERTMANAGER_FIXTURES:
        raw = yaml.safe_load((config.FIXTURES / name).read_text(encoding="utf-8"))
        defined = {receiver["name"] for receiver in raw["receivers"]}
        assert raw["route"]["receiver"] not in defined, name
