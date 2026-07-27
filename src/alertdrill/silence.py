"""Creating and removing Alertmanager silences, and drilling that suppression works.

A silenced alert and a broken alert both deliver nothing. Telling them apart is the whole
point of this module: the drill requires Alertmanager to report the alert as suppressed
while the receiver stays empty. Checking only that no notification arrived would pass just
as happily against a rule that never fired at all.

Silences are removed in a finally block. Leaving one behind would suppress the next drill
and make a broken alerting path look healthy.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

from . import config, observe
from .contract import RuleContract
from .drill import Check, DrillError, RuleResult, post_to_target


def _request(method: str, path: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{config.ALERTMANAGER_URL}{path}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json"} if body else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as error:
        raise DrillError(f"alertmanager {method} {path} failed: {error}") from error


def create(alertname: str, minutes: int = 10) -> str:
    now = datetime.now(UTC)
    payload = {
        "matchers": [
            {"name": "alertname", "value": alertname, "isRegex": False, "isEqual": True}
        ],
        "startsAt": now.isoformat(),
        "endsAt": (now + timedelta(minutes=minutes)).isoformat(),
        "createdBy": "alertmanager-drill",
        "comment": f"drill suppression check for {alertname}",
    }
    created = _request("POST", "/api/v2/silences", payload)
    silence_id = created.get("silenceID") or created.get("id")
    if not silence_id:
        raise DrillError(f"alertmanager did not return a silence id: {created}")
    return silence_id


def expire(silence_id: str) -> None:
    _request("DELETE", f"/api/v2/silence/{silence_id}")


def active_ids() -> list[str]:
    return [
        entry["id"]
        for entry in _request("GET", "/api/v2/silences") or []
        if entry.get("status", {}).get("state") == "active"
    ]


def run(rule: RuleContract, target_url: str | None = None) -> RuleResult:
    """Silence the alert, break the target, and require suppression rather than silence."""
    base = target_url or config.TARGET_URL
    result = RuleResult(alert=f"{rule.alert} (silenced)")
    silence_id: str | None = None

    try:
        observe.reset_receiver()
        silence_id = create(rule.alert)

        post_to_target(f"{base}{rule.break_path}")

        # Alertmanager must know about the alert and mark it suppressed. Without this the
        # check would pass against a rule that never fired.
        suppressed = observe.wait_for_alert_state(
            rule.alert, "suppressed", timeout_seconds=rule.max_fire_seconds
        )
        result.checks.append(Check("silenced.alertmanager_state", "suppressed",
                                   "suppressed" if suppressed else observe.alert_state(rule.alert)))

        # And nothing may reach the receiver.
        delivered = [d for d in observe.deliveries() if d.alertname == rule.alert]
        result.checks.append(Check("silenced.no_delivery", 0, len(delivered)))
        return result
    finally:
        try:
            post_to_target(f"{base}{rule.fix_path}")
            # A silenced alert sends no resolved notification, so nothing else here waits
            # for the rule to settle. Without this the command returns while the alert is
            # still firing and the next one refuses to start on an unclean baseline.
            observe.wait_until_alert_clears(rule.alert)
        except (DrillError, observe.ObservationError):
            pass
        if silence_id:
            try:
                expire(silence_id)
            except DrillError:
                pass
