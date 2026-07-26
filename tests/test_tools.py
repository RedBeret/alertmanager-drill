"""Checks on how the validators are invoked.

These are static. They exist because the validator and the running container mount the
same files, and if those two mount paths drift, promtool would happily validate a layout
Prometheus never sees. That failure is silent: validation passes and the stack is still
wrong.
"""

from __future__ import annotations

import yaml

from alertdrill import config, tools


def compose_volumes(service: str) -> list[str]:
    compose = yaml.safe_load(config.COMPOSE_FILE.read_text(encoding="utf-8"))
    return compose["services"][service]["volumes"]


def container_target(service: str, host_suffix: str) -> str:
    for volume in compose_volumes(service):
        host, target = volume.split(":")[0], volume.split(":")[1]
        if host.endswith(host_suffix):
            return target
    raise AssertionError(f"{service} does not mount anything ending in {host_suffix}")


def test_prometheus_config_is_validated_where_the_container_reads_it():
    assert container_target("prometheus", "prometheus.yml") == tools.PROM_CONFIG_MOUNTPOINT


def test_prometheus_rules_are_validated_where_the_container_reads_them():
    assert container_target("prometheus", "prometheus/rules") == tools.PROM_RULES_MOUNTPOINT


def test_alertmanager_config_is_validated_where_the_container_reads_it():
    assert container_target("alertmanager", "alertmanager.yml") == tools.AM_CONFIG_MOUNTPOINT


def test_rules_glob_in_prometheus_config_covers_the_rules_directory():
    """promtool check config only walks the rule files the glob matches, so a rule file
    outside the glob would pass validation by never being looked at."""
    prom = yaml.safe_load((config.LAB / "prometheus" / "prometheus.yml").read_text())
    globs = prom["rule_files"]
    assert any(pattern.startswith(tools.PROM_RULES_MOUNTPOINT) for pattern in globs)
    on_disk = {path.name for path in config.RULES_DIR.glob("*.rules.yml")}
    assert on_disk, "no rule files on disk"
    for name in on_disk:
        assert any(name.endswith(pattern.split("*")[-1]) for pattern in globs), name


def test_validators_come_from_the_images_the_stack_runs():
    """A separately pinned validator could drift from the runtime it is validating."""
    import inspect

    source = inspect.getsource(tools)
    assert "config.PROMETHEUS_IMAGE" in source
    assert "config.ALERTMANAGER_IMAGE" in source
