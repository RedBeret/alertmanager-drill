"""Proving teardown removes this project and nothing else.

Two things are measured. Every alertdrill container must be gone in any state, because a
stopped container is still one left behind. And every neighbouring container must be in
exactly the state it was in beforehand, compared by state rather than by count. A teardown
that stopped a neighbour would leave the count identical and look clean.

The command refuses to run when there is no neighbouring container at all. A clean room
proved in an empty room demonstrates nothing about isolation.
"""

from __future__ import annotations

import subprocess

from . import config, runner, safety
from .drill import Check, RuleResult


class CleanRoomError(RuntimeError):
    """Raised when the proof cannot be made meaningful."""


def _snapshot(containers: list[dict]) -> dict[str, str]:
    """Identity to state. Names are included so a failure report is readable."""
    return {c["ID"]: f"{c.get('Names', '?')}:{c.get('State', '?')}" for c in containers}


def run() -> RuleResult:
    ours_before = safety.project_containers()
    theirs_before = _snapshot(safety.foreign_containers())

    if not theirs_before:
        raise CleanRoomError(
            "no neighbouring container is running, so a clean room here would prove "
            "nothing about isolation. Start any other container and run this again."
        )
    if not ours_before:
        raise CleanRoomError(
            "no alertdrill containers are running, so there is nothing to tear down. "
            "Run ./scripts/lab.sh up first."
        )

    subprocess.run(
        [*runner.compose_base(), "down", "--volumes", "--remove-orphans"],
        check=True,
        capture_output=True,
        timeout=300,
    )

    ours_after = safety.project_containers()
    theirs_after = _snapshot(safety.foreign_containers())

    result = RuleResult(alert="clean-room")
    result.checks.append(
        Check(f"{config.COMPOSE_PROJECT}.containers_remaining", 0, len(ours_after))
    )
    result.checks.append(
        Check("neighbours.unchanged", theirs_before, theirs_after),
    )
    result.checks.append(
        Check("neighbours.count", len(theirs_before), len(theirs_after)),
    )
    return result
