"""Locating Docker Compose and waiting for the stack to actually be ready.

WSL boxes still commonly carry the standalone docker-compose v1 binary rather than the v2
plugin, so the command is detected rather than assumed. Readiness is polled against each
service's own endpoint instead of using `up --wait`, which v1 does not have and which would
report the container started rather than the service answering.
"""

from __future__ import annotations

import shutil
import subprocess
import time
import urllib.error
import urllib.request

from . import config


class ComposeUnavailable(RuntimeError):
    """Raised when neither Compose v2 nor v1 can be found."""


def compose_command() -> list[str]:
    docker = shutil.which("docker")
    if docker:
        probe = subprocess.run(
            [docker, "compose", "version"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if probe.returncode == 0:
            return [docker, "compose"]
    legacy = shutil.which("docker-compose")
    if legacy:
        return [legacy]
    raise ComposeUnavailable("Docker Compose v1 or v2 is required")


def compose_base() -> list[str]:
    return [*compose_command(), "-p", config.COMPOSE_PROJECT, "-f", str(config.COMPOSE_FILE)]


def endpoints() -> dict[str, str]:
    return {
        "prometheus": f"{config.PROMETHEUS_URL}/-/ready",
        "alertmanager": f"{config.ALERTMANAGER_URL}/-/ready",
        "receiver": f"{config.RECEIVER_URL}/health",
        "target": f"{config.TARGET_URL}/metrics",
    }


def reachable(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except (urllib.error.URLError, OSError):
        return False


def wait_until_ready(deadline_seconds: int = 120) -> list[str]:
    """Poll every endpoint until all answer or the deadline passes.

    Returns the services still not answering, so the caller reports what specifically
    failed rather than a bare timeout.
    """
    deadline = time.monotonic() + deadline_seconds
    pending = dict(endpoints())
    while pending and time.monotonic() < deadline:
        for name, url in list(pending.items()):
            if reachable(url):
                del pending[name]
        if pending:
            time.sleep(2)
    return sorted(pending)
