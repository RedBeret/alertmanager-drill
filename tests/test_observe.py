"""Tests for the observation layer, with the network stubbed.

The behaviour worth pinning is what happens when nothing arrives. A helper that returns
something falsy on timeout is easy to misread downstream as "fine", so these tests fix the
contract: a timeout returns None, and unreadable endpoints raise rather than return empty.
"""

from __future__ import annotations

import pytest

from alertdrill import observe

FIRING_PAYLOAD = {
    "notifications": [
        {
            "received_at": 1000.0,
            "receiver_path": "/oncall-critical",
            "payload": {
                "receiver": "oncall-critical",
                "status": "firing",
                "alerts": [
                    {
                        "status": "firing",
                        "labels": {"alertname": "TargetServiceDown", "severity": "critical"},
                        "annotations": {"summary": "down"},
                    },
                    {
                        "status": "firing",
                        "labels": {"alertname": "OtherAlert", "severity": "warning"},
                        "annotations": {},
                    },
                ],
            },
        }
    ]
}


def test_grouped_alerts_are_flattened(monkeypatch):
    """Alertmanager groups alerts, so one webhook can carry several."""
    monkeypatch.setattr(observe, "_get", lambda url, timeout=5.0: FIRING_PAYLOAD)
    found = observe.deliveries()
    assert [d.alertname for d in found] == ["TargetServiceDown", "OtherAlert"]
    assert found[0].receiver == "oncall-critical"
    assert found[0].receiver_path == "/oncall-critical"
    assert found[0].labels["severity"] == "critical"


def test_elapsed_is_measured_from_the_moment_the_caller_supplies():
    delivery = observe.Delivery(
        alertname="X",
        status="firing",
        receiver="r",
        receiver_path="/r",
        labels={},
        annotations={},
        received_at=1030.0,
    )
    assert delivery.elapsed_since(1000.0) == 30.0


def test_wait_returns_none_when_nothing_arrives(monkeypatch):
    """None is the signal for an unobserved value. The contract must fail on it rather
    than treat the absence of bad news as good news."""
    monkeypatch.setattr(observe, "deliveries", list)
    monkeypatch.setattr(observe.time, "sleep", lambda _: None)
    assert observe.wait_for_delivery("X", "firing", 0.0, timeout_seconds=0.2) is None


def test_wait_ignores_deliveries_from_before_the_condition_started(monkeypatch):
    """A notification left over from an earlier run must not satisfy this one."""
    monkeypatch.setattr(observe, "_get", lambda url, timeout=5.0: FIRING_PAYLOAD)
    monkeypatch.setattr(observe.time, "sleep", lambda _: None)
    stale = observe.wait_for_delivery(
        "TargetServiceDown", "firing", started_at=2000.0, timeout_seconds=0.2
    )
    assert stale is None

    fresh = observe.wait_for_delivery(
        "TargetServiceDown", "firing", started_at=500.0, timeout_seconds=5
    )
    assert fresh is not None
    assert fresh.received_at == 1000.0


def test_wait_distinguishes_status(monkeypatch):
    monkeypatch.setattr(observe, "_get", lambda url, timeout=5.0: FIRING_PAYLOAD)
    monkeypatch.setattr(observe.time, "sleep", lambda _: None)
    assert (
        observe.wait_for_delivery("TargetServiceDown", "resolved", 0.0, timeout_seconds=0.2)
        is None
    )


def test_unreadable_endpoint_raises_rather_than_returning_empty(monkeypatch):
    """Returning [] here would let a totally dead stack look like a quiet one."""

    def boom(url, timeout=5.0):
        raise OSError("connection refused")

    monkeypatch.setattr(observe.urllib.request, "urlopen", boom)
    with pytest.raises(observe.ObservationError):
        observe.deliveries()
