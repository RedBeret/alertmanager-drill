"""Tests for the suppression drill.

The property under test is the one that is easy to get wrong: checking only that no
notification arrived would pass just as happily against an alert that never fired. Both
deliver nothing.
"""

from __future__ import annotations

import pytest

from alertdrill import drill, observe, silence
from alertdrill.contract import RuleContract

RULE = RuleContract(
    alert="TargetServiceDown",
    rule_file="lab/prometheus/rules/drill.rules.yml",
    break_path="/break",
    fix_path="/fix",
    max_fire_seconds=5,
    max_resolve_seconds=5,
    receiver="oncall-critical",
    labels={"severity": "critical"},
    annotations=("summary",),
    expect_suppressed=True,
)


@pytest.fixture
def stub(monkeypatch):
    calls = {"posts": [], "expired": []}
    monkeypatch.setattr(silence, "post_to_target", calls["posts"].append)
    monkeypatch.setattr(observe, "reset_receiver", lambda: None)
    monkeypatch.setattr(silence, "create", lambda alert, minutes=10: "sil-1")
    monkeypatch.setattr(silence, "expire", calls["expired"].append)
    monkeypatch.setattr(observe, "deliveries", list)
    return calls


def test_suppressed_with_no_delivery_passes(stub, monkeypatch):
    monkeypatch.setattr(observe, "wait_for_alert_state", lambda *a, **k: True)
    result = silence.run(RULE)
    assert result.passed


def test_an_alert_that_never_fired_does_not_count_as_suppressed(stub, monkeypatch):
    """The important one. No delivery alone would look like success."""
    monkeypatch.setattr(observe, "wait_for_alert_state", lambda *a, **k: False)
    monkeypatch.setattr(observe, "alert_state", lambda alert: None)
    result = silence.run(RULE)
    assert not result.passed
    state = next(c for c in result.checks if c.name == "silenced.alertmanager_state")
    assert not state.passed
    assert state.observed is None
    # And the delivery check still passes, which is precisely why it cannot stand alone.
    assert next(c for c in result.checks if c.name == "silenced.no_delivery").passed


def test_a_delivery_that_slipped_through_a_silence_fails(stub, monkeypatch):
    monkeypatch.setattr(observe, "wait_for_alert_state", lambda *a, **k: True)
    monkeypatch.setattr(
        observe,
        "deliveries",
        lambda: [
            observe.Delivery(
                alertname="TargetServiceDown",
                status="firing",
                receiver="oncall-critical",
                receiver_path="/oncall-critical",
                labels={},
                annotations={},
                received_at=1.0,
            )
        ],
    )
    result = silence.run(RULE)
    assert not result.passed
    assert not next(c for c in result.checks if c.name == "silenced.no_delivery").passed


def test_the_silence_is_always_removed(stub, monkeypatch):
    """A silence left behind would suppress the next drill and make a broken alerting
    path look healthy."""
    monkeypatch.setattr(observe, "wait_for_alert_state", lambda *a, **k: True)
    silence.run(RULE)
    assert stub["expired"] == ["sil-1"]


def test_the_silence_is_removed_even_when_the_drill_raises(stub, monkeypatch):
    def explode(*args, **kwargs):
        raise observe.ObservationError("alertmanager died mid drill")

    monkeypatch.setattr(observe, "wait_for_alert_state", explode)
    with pytest.raises(observe.ObservationError):
        silence.run(RULE)
    assert stub["expired"] == ["sil-1"]
    assert stub["posts"][-1].endswith("/fix"), "target was not restored"


def test_a_missing_silence_id_is_refused(monkeypatch):
    monkeypatch.setattr(silence, "_request", lambda method, path, payload=None: {})
    with pytest.raises(drill.DrillError, match="did not return a silence id"):
        silence.create("TargetServiceDown")
