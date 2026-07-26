"""Running promtool and amtool out of the images the stack already runs.

Both tools ship inside the Prometheus and Alertmanager images, so validation happens on
exactly the build that will serve. Pinning a separate validator binary would let the
checker and the runtime drift, which is the failure this project exists to catch
elsewhere.

Config files are mounted at the same paths the running containers use, so promtool
resolves the rule_files glob the same way Prometheus will.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import config

PROM_CONFIG_MOUNTPOINT = "/etc/prometheus/prometheus.yml"
PROM_RULES_MOUNTPOINT = "/etc/prometheus/rules"
AM_CONFIG_MOUNTPOINT = "/etc/alertmanager/alertmanager.yml"


@dataclass(frozen=True)
class ToolResult:
    name: str
    passed: bool
    exit_code: int
    output: str


def _run(args: list[str]) -> tuple[int, str]:
    completed = subprocess.run(args, check=False, capture_output=True, text=True, timeout=180)
    return completed.returncode, (completed.stdout + completed.stderr).strip()


def check_prometheus_config(
    config_file: Path | None = None,
    rules_dir: Path | None = None,
) -> ToolResult:
    """promtool check config, which also walks every rule file the config references."""
    cfg = config_file or (config.LAB / "prometheus" / "prometheus.yml")
    rules = rules_dir or config.RULES_DIR
    code, output = _run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "promtool",
            "-v",
            f"{cfg}:{PROM_CONFIG_MOUNTPOINT}:ro",
            "-v",
            f"{rules}:{PROM_RULES_MOUNTPOINT}:ro",
            config.PROMETHEUS_IMAGE,
            "check",
            "config",
            PROM_CONFIG_MOUNTPOINT,
        ]
    )
    return ToolResult("promtool check config", code == 0, code, output)


def check_rule_file(rule_file: Path) -> ToolResult:
    """promtool check rules on a single file, so a bad fixture names itself in the report."""
    mountpoint = f"/rules/{rule_file.name}"
    code, output = _run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "promtool",
            "-v",
            f"{rule_file}:{mountpoint}:ro",
            config.PROMETHEUS_IMAGE,
            "check",
            "rules",
            mountpoint,
        ]
    )
    return ToolResult(f"promtool check rules {rule_file.name}", code == 0, code, output)


def run_rule_unit_tests(test_file: Path) -> ToolResult:
    """promtool test rules, which drives synthetic series through the real rule files.

    The whole repository is mounted read-only because the test file references its rule
    files by relative path, the same way it reads on disk.
    """
    relative = test_file.relative_to(config.ROOT)
    code, output = _run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "promtool",
            "-v",
            f"{config.ROOT}:/work:ro",
            config.PROMETHEUS_IMAGE,
            "test",
            "rules",
            f"/work/{relative}",
        ]
    )
    return ToolResult(f"promtool test rules {test_file.name}", code == 0, code, output)


def check_alertmanager_config(config_file: Path | None = None) -> ToolResult:
    cfg = config_file or (config.LAB / "alertmanager" / "alertmanager.yml")
    code, output = _run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "amtool",
            "-v",
            f"{cfg}:{AM_CONFIG_MOUNTPOINT}:ro",
            config.ALERTMANAGER_IMAGE,
            "check-config",
            AM_CONFIG_MOUNTPOINT,
        ]
    )
    return ToolResult("amtool check-config", code == 0, code, output)
