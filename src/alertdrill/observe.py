"""Reading what the stack actually did.

Everything here observes. Nothing here changes the target's state, so a failed drill can
call any of it while cleaning up.

The one design rule: elapsed time is always measured from a moment the caller passes in,
never from when polling happened to start. The interesting number is how long it took from
the condition beginning to a human being told, and a stopwatch started when the observer
got around to looking would quietly hide the front of that interval.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from . import config


class ObservationError(RuntimeError):
    """Raised when the stack cannot be read at all, which is never a pass."""


def _get(url: str, timeout: float = 5.0) -> Any:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as error:
        raise ObservationError(f"could not read {url}: {error}") from error


def _post(url: str, timeout: float = 5.0) -> Any:
    request = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            return json.loads(body) if body else {}
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as error:
        raise ObservationError(f"could not post to {url}: {error}") from error


@dataclass(frozen=True)
class Delivery:
    """One notification as the receiver saw it."""

    alertname: str
    status: str
    receiver: str
    receiver_path: str
    labels: dict[str, str]
    annotations: dict[str, str]
    received_at: float

    def elapsed_since(self, started_at: float) -> float:
        return self.received_at - started_at


def reset_receiver() -> None:
    _post(f"{config.RECEIVER_URL}/reset")


def deliveries() -> list[Delivery]:
    """Flatten every captured webhook into one Delivery per alert.

    Alertmanager groups alerts, so a single webhook can carry several. Flattening here
    means a caller asking about one alertname never has to know that.
    """
    payload = _get(f"{config.RECEIVER_URL}/notifications")
    found: list[Delivery] = []
    for entry in payload.get("notifications", []):
        body = entry.get("payload", {})
        for alert in body.get("alerts", []):
            labels = alert.get("labels", {})
            found.append(
                Delivery(
                    alertname=labels.get("alertname", ""),
                    status=alert.get("status", body.get("status", "")),
                    receiver=body.get("receiver", ""),
                    receiver_path=entry.get("receiver_path", ""),
                    labels=labels,
                    annotations=alert.get("annotations", {}),
                    received_at=float(entry.get("received_at", 0.0)),
                )
            )
    return found


def wait_for_delivery(
    alertname: str,
    status: str,
    started_at: float,
    timeout_seconds: float,
    poll_seconds: float = 1.0,
) -> Delivery | None:
    """Wait for one notification, or return None once the budget is spent.

    None means the drill has an unobserved value, which the contract comparison must treat
    as a failure. It must never be read as "nothing was wrong".
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for delivery in deliveries():
            if (
                delivery.alertname == alertname
                and delivery.status == status
                and delivery.received_at >= started_at
            ):
                return delivery
        time.sleep(poll_seconds)
    return None


def alertmanager_alerts() -> list[dict]:
    return _get(f"{config.ALERTMANAGER_URL}/api/v2/alerts")


def alert_state(alertname: str) -> str | None:
    """active, suppressed, or unprocessed as Alertmanager sees it, or None if absent.

    This is what separates a silenced alert from a broken one. Both deliver nothing, and
    without asking Alertmanager they look identical.
    """
    for alert in alertmanager_alerts():
        if alert.get("labels", {}).get("alertname") == alertname:
            return alert.get("status", {}).get("state")
    return None


def wait_until_alert_clears(alertname: str, timeout_seconds: float = 90.0) -> bool:
    """Wait until Prometheus stops reporting the rule as pending or firing.

    A command that restores the target and returns immediately leaves the alert still
    firing for as long as the rule takes to re-evaluate, and the next command's baseline
    check then refuses. Every drill must hand back the state it borrowed.
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if prometheus_rule_state(alertname) == "inactive":
            return True
        time.sleep(1.0)
    return False


def wait_for_alert_state(
    alertname: str,
    state: str,
    timeout_seconds: float,
    poll_seconds: float = 1.0,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if alert_state(alertname) == state:
            return True
        time.sleep(poll_seconds)
    return False


def prometheus_rule_state(alertname: str) -> str | None:
    """inactive, pending, or firing as Prometheus currently sees it.

    Useful for telling "the rule never fired" apart from "the rule fired and the
    notification never arrived", which are different defects with different owners.
    """
    payload = _get(f"{config.PROMETHEUS_URL}/api/v1/rules")
    for group in payload.get("data", {}).get("groups", []):
        for rule in group.get("rules", []):
            if rule.get("name") == alertname:
                return rule.get("state")
    return None
