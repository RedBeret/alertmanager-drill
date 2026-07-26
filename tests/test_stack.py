"""Checks on the committed stack definition itself.

These run without Docker. They exist because a misconfigured route or a port bound to all
interfaces is the kind of defect that stays invisible until the drill is already running.
"""

from __future__ import annotations

import yaml

from alertdrill import config, contract, runner


def load_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_every_published_port_binds_to_loopback_only():
    compose = load_yaml(config.COMPOSE_FILE)
    for name, service in compose["services"].items():
        for published in service.get("ports", []):
            assert published.startswith("127.0.0.1:"), f"{name} publishes {published} beyond loopback"


def test_compose_is_always_invoked_with_the_project_name():
    """The project label is what safety.py checks before removing anything, and it comes
    from -p rather than a compose key, so the invariant lives in the command builder."""
    base = runner.compose_base()
    assert "-p" in base
    assert base[base.index("-p") + 1] == config.COMPOSE_PROJECT


def test_compose_file_has_no_top_level_name_key():
    """Compose v1 rejects it, and WSL boxes still ship v1."""
    assert "name" not in load_yaml(config.COMPOSE_FILE)


def test_compose_declares_every_expected_service():
    compose = load_yaml(config.COMPOSE_FILE)
    assert set(compose["services"]) == set(config.SERVICES)


def test_pinned_images_match_config():
    """config.py is what the evidence reports, so it must not drift from compose."""
    compose = load_yaml(config.COMPOSE_FILE)
    assert compose["services"]["prometheus"]["image"] == config.PROMETHEUS_IMAGE
    assert compose["services"]["alertmanager"]["image"] == config.ALERTMANAGER_IMAGE


def test_every_contract_receiver_is_defined_in_alertmanager():
    """A contract expecting a receiver Alertmanager does not define could never pass, and
    would look like a routing bug rather than a configuration error."""
    am = load_yaml(config.LAB / "alertmanager" / "alertmanager.yml")
    defined = {receiver["name"] for receiver in am["receivers"]}
    for rule in contract.load().rules:
        assert rule.receiver in defined, f"{rule.receiver} is not an Alertmanager receiver"


def test_alertmanager_receivers_send_resolved():
    """Without send_resolved the resolution half of the drill can never observe anything."""
    am = load_yaml(config.LAB / "alertmanager" / "alertmanager.yml")
    for receiver in am["receivers"]:
        for webhook in receiver.get("webhook_configs", []):
            assert webhook.get("send_resolved") is True, receiver["name"]


def test_prometheus_loads_the_rules_directory():
    prom = load_yaml(config.LAB / "prometheus" / "prometheus.yml")
    assert any("rules" in pattern for pattern in prom["rule_files"])


def test_declared_severity_labels_have_a_matching_route():
    """A rule labelled critical with no route for critical silently lands on the default
    receiver, which is a routing failure the contract is meant to catch."""
    am = load_yaml(config.LAB / "alertmanager" / "alertmanager.yml")
    matchers = [m for route in am["route"].get("routes", []) for m in route.get("matchers", [])]
    for rule in contract.load().rules:
        severity = rule.labels.get("severity")
        if severity:
            assert any(f'severity="{severity}"' == m for m in matchers), severity
