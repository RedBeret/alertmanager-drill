"""Tests for the drill runner, with the target and receiver stubbed.

The two properties worth guarding are that an unobserved value fails rather than passes,
and that the target is restored no matter how the drill ends.
"""

from __future__ import annotations

import pytest

from alertdrill import drill, observe
from alertdrill.contract import RuleContract

RULE = RuleContract(
    alert="TargetServiceDown",
    rule_file="lab/prometheus/rules/drill.rules.yml",
    break_path="/break",
    fix_path="/fix",
    max_fire_seconds=60,
    max_resolve_seconds=60,
    receiver="oncall-critical",
    labels={"severity": "critical", "team": "platform"},
    annotations=("summary", "description"),
    expect_suppressed=False,
)


def delivery(status: str, at: float, receiver: str = "oncall-critical", **labels):
    merged = {"alertname": "TargetServiceDown", "severity": "critical", "team": "platform"}
    merged.update(labels)
    return observe.Delivery(
        alertname="TargetServiceDown",
        status=status,
        receiver=receiver,
        receiver_path=f"/{receiver}",
        labels=merged,
        annotations={"summary": "s", "description": "d"},
        received_at=at,
    )


@pytest.fixture
def posts(monkeypatch):
    """Record every POST the drill makes so restoration can be asserted."""
    seen: list[str] = []
    monkeypatch.setattr(drill, "_post", seen.append)
    monkeypatch.setattr(observe, "reset_receiver", lambda: None)
    monkeypatch.setattr(drill.time, "time", lambda: 1000.0)
    return seen


def test_a_clean_drill_passes_every_check(posts, monkeypatch):
    monkeypatch.setattr(
        observe,
        "wait_for_delivery",
        lambda alert, status, started, timeout_seconds: delivery(status, started + 10),
    )
    result = drill.run_rule(RULE)
    assert result.passed, [c.as_dict() for c in result.checks if not c.passed]
    assert result.fire_seconds == 10.0
    assert result.resolve_seconds == 10.0


def test_a_notification_that_never_arrives_fails_rather_than_passes(posts, monkeypatch):
    """The whole point. No delivery means no observation, and no observation is a fail."""
    monkeypatch.setattr(
        observe, "wait_for_delivery", lambda alert, status, started, timeout_seconds: None
    )
    result = drill.run_rule(RULE)
    assert not result.passed
    names = {c.name for c in result.checks if not c.passed}
    assert "firing.delivered" in names
    assert "firing.latency" in names
    assert "firing.receiver" in names
    assert all(
        c.observed == drill.NOT_OBSERVED
        for c in result.checks
        if c.name in {"firing.receiver", "resolved.receiver"}
    )


def test_latency_over_the_bound_fails(posts, monkeypatch):
    monkeypatch.setattr(
        observe,
        "wait_for_delivery",
        lambda alert, status, started, timeout_seconds: delivery(status, started + 999),
    )
    result = drill.run_rule(RULE)
    assert not result.passed
    latency = next(c for c in result.checks if c.name == "firing.latency")
    assert latency.observed == "over 60s"


def test_wrong_receiver_fails_even_though_the_alert_fired(posts, monkeypatch):
    """Firing correctly but reaching the wrong team is still a paging failure."""
    monkeypatch.setattr(
        observe,
        "wait_for_delivery",
        lambda alert, status, started, timeout_seconds: delivery(
            status, started + 5, receiver="default"
        ),
    )
    result = drill.run_rule(RULE)
    assert not result.passed
    assert next(c for c in result.checks if c.name == "firing.delivered").passed
    assert not next(c for c in result.checks if c.name == "firing.receiver").passed


def test_a_missing_label_fails(posts, monkeypatch):
    monkeypatch.setattr(
        observe,
        "wait_for_delivery",
        lambda alert, status, started, timeout_seconds: delivery(
            status, started + 5, team=None
        ),
    )
    result = drill.run_rule(RULE)
    assert not result.passed
    assert not next(c for c in result.checks if c.name == "firing.label.team").passed


def test_the_target_is_restored_even_when_the_drill_raises(posts, monkeypatch):
    def explode(*args, **kwargs):
        raise observe.ObservationError("receiver died mid drill")

    monkeypatch.setattr(observe, "wait_for_delivery", explode)
    with pytest.raises(observe.ObservationError):
        drill.run_rule(RULE)
    assert posts[-1].endswith("/fix"), f"target was not restored, posts were {posts}"


def test_the_target_is_restored_after_a_clean_run(posts, monkeypatch):
    monkeypatch.setattr(
        observe,
        "wait_for_delivery",
        lambda alert, status, started, timeout_seconds: delivery(status, started + 5),
    )
    drill.run_rule(RULE)
    assert posts[-1].endswith("/fix")


def test_baseline_must_be_inactive(monkeypatch):
    monkeypatch.setattr(observe, "prometheus_rule_state", lambda alert: "firing")
    with pytest.raises(drill.DrillError, match="baseline is not clean"):
        drill.require_healthy_baseline(RULE)


def test_an_alert_prometheus_does_not_know_is_refused(monkeypatch):
    """The contract naming a rule the stack never loaded would otherwise look like a
    rule that simply failed to fire."""
    monkeypatch.setattr(observe, "prometheus_rule_state", lambda alert: None)
    with pytest.raises(drill.DrillError, match="does not know a rule"):
        drill.require_healthy_baseline(RULE)


def test_result_dict_counts_agree_with_the_checks(posts, monkeypatch):
    monkeypatch.setattr(
        observe,
        "wait_for_delivery",
        lambda alert, status, started, timeout_seconds: delivery(status, started + 5),
    )
    payload = drill.run_rule(RULE).as_dict()
    assert payload["passed"] + payload["failed"] == payload["total"]
    assert payload["total"] == len(payload["checks"])
    assert payload["outcome"] == "pass"
