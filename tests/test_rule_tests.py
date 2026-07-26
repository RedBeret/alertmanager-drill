"""Checks on the rule unit tests themselves.

promtool test rules is only as good as what it asserts. A test file that declares no
alert_rule_test, or that only ever expects an empty alert list, passes trivially and
proves nothing about whether a rule can fire.
"""

from __future__ import annotations

import yaml

from alertdrill import config, contract


def load_test_files() -> list[dict]:
    return [
        yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(config.RULE_TESTS.glob("*.test.yml"))
    ]


def test_rule_unit_tests_exist():
    assert list(config.RULE_TESTS.glob("*.test.yml")), "no promtool test files"


def test_every_test_file_references_a_real_rule_file():
    for path in sorted(config.RULE_TESTS.glob("*.test.yml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        for reference in raw["rule_files"]:
            assert (path.parent / reference).resolve().is_file(), reference


def test_every_test_file_asserts_something():
    for raw in load_test_files():
        assert raw.get("tests"), "a test file with no tests passes trivially"
        for case in raw["tests"]:
            assert case.get("alert_rule_test"), "a test case with no assertions proves nothing"


def test_at_least_one_assertion_expects_an_alert_to_actually_fire():
    """A suite that only ever expects empty alert lists would pass against a rule file
    that had been deleted."""
    fired = 0
    for raw in load_test_files():
        for case in raw["tests"]:
            for assertion in case["alert_rule_test"]:
                fired += len(assertion.get("exp_alerts") or [])
    assert fired > 0, "no assertion expects an alert to fire"


def test_at_least_one_assertion_expects_no_alert():
    """The inverse. Without a negative case a rule that fired constantly would pass."""
    empty = 0
    for raw in load_test_files():
        for case in raw["tests"]:
            for assertion in case["alert_rule_test"]:
                if not assertion.get("exp_alerts"):
                    empty += 1
    assert empty > 0, "no assertion expects the absence of an alert"


def test_every_contract_alert_has_a_unit_test():
    """A rule the contract will drill live should also be pinned statically."""
    tested = set()
    for raw in load_test_files():
        for case in raw["tests"]:
            for assertion in case["alert_rule_test"]:
                tested.add(assertion["alertname"])
    for rule in contract.load().rules:
        assert rule.alert in tested, f"{rule.alert} has no promtool unit test"


def test_expected_labels_cover_every_label_the_contract_declares():
    """If the contract routes on severity, the unit test must assert severity, or the rule
    could lose that label and only the live drill would notice."""
    declared: dict[str, dict[str, str]] = {r.alert: r.labels for r in contract.load().rules}
    for raw in load_test_files():
        for case in raw["tests"]:
            for assertion in case["alert_rule_test"]:
                wanted = declared.get(assertion["alertname"])
                if not wanted:
                    continue
                for alert in assertion.get("exp_alerts") or []:
                    for key, value in wanted.items():
                        assert alert["exp_labels"].get(key) == value, (
                            f"{assertion['alertname']} unit test does not pin {key}={value}"
                        )
