"""Tests for the teardown proof, with Docker stubbed.

Two properties matter. A stopped container still counts as one left behind, and
neighbours are compared by state rather than by count, because a teardown that stopped a
neighbour would leave the count identical and look clean.
"""

from __future__ import annotations

import pytest

from alertdrill import cleanroom, runner, safety


def container(cid: str, name: str, state: str) -> dict:
    return {"ID": cid, "Names": name, "State": state}


@pytest.fixture
def stub(monkeypatch):
    monkeypatch.setattr(runner, "compose_base", lambda: ["true"])
    monkeypatch.setattr(cleanroom.subprocess, "run", lambda *a, **k: None)
    return monkeypatch


def wire(monkeypatch, ours_before, ours_after, theirs_before, theirs_after):
    ours = iter([ours_before, ours_after])
    theirs = iter([theirs_before, theirs_after])
    monkeypatch.setattr(safety, "project_containers", lambda: next(ours))
    monkeypatch.setattr(safety, "foreign_containers", lambda: next(theirs))


NEIGHBOUR = [container("n1", "kubedrift-control-plane", "running")]


def test_a_clean_teardown_passes(stub):
    wire(stub, [container("a", "alertdrill_target_1", "running")], [], NEIGHBOUR, NEIGHBOUR)
    assert cleanroom.run().passed


def test_a_stopped_container_counts_as_left_behind(stub):
    """exited is not a pass. The container is still on the host."""
    wire(
        stub,
        [container("a", "alertdrill_target_1", "running")],
        [container("a", "alertdrill_target_1", "exited")],
        NEIGHBOUR,
        NEIGHBOUR,
    )
    result = cleanroom.run()
    assert not result.passed
    remaining = next(c for c in result.checks if c.name.endswith("containers_remaining"))
    assert remaining.observed == 1


def test_a_stopped_neighbour_fails_even_though_the_count_is_unchanged(stub):
    """The reason neighbours are compared by state and not by count."""
    stopped = [container("n1", "kubedrift-control-plane", "exited")]
    wire(stub, [container("a", "x", "running")], [], NEIGHBOUR, stopped)
    result = cleanroom.run()
    assert not result.passed
    assert not next(c for c in result.checks if c.name == "neighbours.unchanged").passed
    # The count check still passes, which is precisely why it cannot stand alone.
    assert next(c for c in result.checks if c.name == "neighbours.count").passed


def test_a_removed_neighbour_fails(stub):
    wire(stub, [container("a", "x", "running")], [], NEIGHBOUR, [])
    assert not cleanroom.run().passed


def test_it_refuses_when_there_is_no_neighbour(stub):
    """A clean room proved in an empty room demonstrates nothing about isolation."""
    wire(stub, [container("a", "x", "running")], [], [], [])
    with pytest.raises(cleanroom.CleanRoomError, match="no neighbouring container"):
        cleanroom.run()


def test_it_refuses_when_nothing_of_ours_is_running(stub):
    wire(stub, [], [], NEIGHBOUR, NEIGHBOUR)
    with pytest.raises(cleanroom.CleanRoomError, match="nothing to tear down"):
        cleanroom.run()
