"""Checks that must pass before anything in this project stops or removes a container.

The rule is the same one the sibling labs use: identify the target by a label only this
project sets, and refuse rather than guess. A container that does not carry the project
label is never a valid target, no matter what its name looks like.
"""

from __future__ import annotations

import json
import subprocess

from . import config


class SafetyError(RuntimeError):
    """Raised when a destructive action cannot be proven safe."""


def docker_available() -> bool:
    try:
        subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            check=True,
            capture_output=True,
            timeout=30,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return True


def project_containers() -> list[dict]:
    """Every container carrying this project's Compose label, running or not."""
    result = subprocess.run(
        [
            "docker",
            "ps",
            "--all",
            "--filter",
            f"label={config.PROJECT_LABEL}={config.COMPOSE_PROJECT}",
            "--format",
            "{{json .}}",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def foreign_containers() -> list[dict]:
    """Containers that do not belong to this project, recorded so teardown can prove it
    left them alone. Compared by exact state rather than by count, because a teardown that
    stopped a neighbour would keep the count identical."""
    result = subprocess.run(
        ["docker", "ps", "--all", "--format", "{{json .}}"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    everything = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    ours = {container["ID"] for container in project_containers()}
    return [c for c in everything if c["ID"] not in ours]


def assert_owned(container_id: str) -> None:
    """Refuse to act on a container this project does not own."""
    owned = {c["ID"] for c in project_containers()}
    if container_id not in owned:
        raise SafetyError(
            f"container {container_id} does not carry "
            f"{config.PROJECT_LABEL}={config.COMPOSE_PROJECT} and will not be touched"
        )
