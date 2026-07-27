"""Running one rule's drill and comparing what happened against what was declared.

The shape of every check is the same as the sibling labs use: an expected value, an
observed value, and a pass field. A value the stack did not supply is recorded as not
observed and compares unequal, so a drill that learned nothing fails rather than passing
quietly.

Restoring the target runs in a finally block. A drill that raises partway must still leave
the target healthy, or the next run starts dirty and its baseline means nothing.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from . import config, observe
from .contract import RuleContract

NOT_OBSERVED = "not observed"


class DrillError(RuntimeError):
    """Raised when the drill cannot start from a known state."""


@dataclass(frozen=True)
class Check:
    name: str
    expected: object
    observed: object

    @property
    def passed(self) -> bool:
        return self.observed == self.expected

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "expected": self.expected,
            "observed": self.observed,
            "pass": self.passed,
        }


@dataclass
class RuleResult:
    alert: str
    checks: list[Check] = field(default_factory=list)
    fire_seconds: float | None = None
    resolve_seconds: float | None = None

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)

    def as_dict(self) -> dict:
        return {
            "alert": self.alert,
            "fire_seconds": self.fire_seconds,
            "resolve_seconds": self.resolve_seconds,
            "passed": sum(1 for check in self.checks if check.passed),
            "failed": sum(1 for check in self.checks if not check.passed),
            "total": len(self.checks),
            "outcome": "pass" if self.passed else "fail",
            "checks": [check.as_dict() for check in self.checks],
        }


def post_to_target(url: str) -> None:
    request = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10):
            return
    except (urllib.error.URLError, OSError) as error:
        raise DrillError(f"could not post to {url}: {error}") from error


def _within(observed: float | None, bound: float) -> str:
    """Latency is compared as a verdict rather than a number, so the report says what the
    bound was and whether it held instead of leaving a reader to do the arithmetic."""
    if observed is None:
        return NOT_OBSERVED
    return f"within {bound:g}s" if observed <= bound else f"over {bound:g}s"


def require_healthy_baseline(rule: RuleContract) -> None:
    """A drill that starts from an already firing alert proves nothing about firing."""
    state = observe.prometheus_rule_state(rule.alert)
    if state is None:
        raise DrillError(
            f"Prometheus does not know a rule called {rule.alert}. "
            "The contract names an alert the running stack has not loaded."
        )
    if state != "inactive":
        raise DrillError(
            f"baseline is not clean: {rule.alert} is already {state}. "
            "Bring the target back to a healthy state before drilling."
        )


def run_rule(rule: RuleContract, target_url: str | None = None) -> RuleResult:
    """Break the target, observe, then always restore it."""
    base = target_url or config.TARGET_URL
    result = RuleResult(alert=rule.alert)
    observe.reset_receiver()

    try:
        started = time.time()
        post_to_target(f"{base}{rule.break_path}")

        firing = observe.wait_for_delivery(
            rule.alert, "firing", started, timeout_seconds=rule.max_fire_seconds
        )
        if firing is not None:
            result.fire_seconds = round(firing.elapsed_since(started), 2)

        result.checks.append(
            Check("firing.delivered", True, firing is not None),
        )
        result.checks.append(
            Check(
                "firing.latency",
                f"within {rule.max_fire_seconds:g}s",
                _within(result.fire_seconds, rule.max_fire_seconds),
            )
        )
        result.checks.append(
            Check(
                "firing.receiver",
                rule.receiver,
                firing.receiver if firing else NOT_OBSERVED,
            )
        )
        for key, value in sorted(rule.labels.items()):
            result.checks.append(
                Check(
                    f"firing.label.{key}",
                    value,
                    firing.labels.get(key, NOT_OBSERVED) if firing else NOT_OBSERVED,
                )
            )
        for key in rule.annotations:
            present = bool(firing.annotations.get(key)) if firing else False
            result.checks.append(Check(f"firing.annotation.{key}", True, present))

        # Restore, then prove the all-clear arrives too. An alert that fires and never
        # clears leaves an on-call engineer chasing a fault that is already fixed.
        cleared = time.time()
        post_to_target(f"{base}{rule.fix_path}")
        resolved = observe.wait_for_delivery(
            rule.alert, "resolved", cleared, timeout_seconds=rule.max_resolve_seconds
        )
        if resolved is not None:
            result.resolve_seconds = round(resolved.elapsed_since(cleared), 2)

        result.checks.append(Check("resolved.delivered", True, resolved is not None))
        result.checks.append(
            Check(
                "resolved.latency",
                f"within {rule.max_resolve_seconds:g}s",
                _within(result.resolve_seconds, rule.max_resolve_seconds),
            )
        )
        result.checks.append(
            Check(
                "resolved.receiver",
                rule.receiver,
                resolved.receiver if resolved else NOT_OBSERVED,
            )
        )
        return result
    finally:
        # Unconditional. If this drill raised, the target must still come back healthy.
        try:
            post_to_target(f"{base}{rule.fix_path}")
        except DrillError:
            pass
