"""CI must run the same entrypoints a workstation does.

The failure this prevents is quiet: someone removes a step, CI keeps reporting green, and
the gate only exists on the machine of whoever last ran it by hand. These tests read the
workflow and fail if a gate stops running there.
"""

from __future__ import annotations

import yaml

from alertdrill import config

WORKFLOW = config.ROOT / ".github" / "workflows" / "ci.yml"

# Commands CI must invoke. Each one is a gate that would otherwise be local only.
REQUIRED_COMMANDS = (
    "./scripts/bootstrap.sh",
    "./scripts/lab.sh test",
    "./scripts/lab.sh validate",
)


def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def run_steps() -> list[str]:
    raw = workflow()
    steps = []
    for job in raw["jobs"].values():
        for step in job["steps"]:
            if "run" in step:
                steps.append(step["run"])
    return steps


def test_workflow_exists():
    assert WORKFLOW.is_file()


def test_ci_runs_every_required_command():
    joined = "\n".join(run_steps())
    for command in REQUIRED_COMMANDS:
        assert command in joined, f"CI does not run {command}"


def test_ci_holds_no_drill_logic_of_its_own():
    """Every run step must be a project entrypoint or a plain check, never a reimplementation
    of what alertctl does. Duplicated logic is how CI and a workstation drift apart."""
    allowed_prefixes = ("./scripts/", "test -x", "bash -n", "./.venv/bin/ruff", "docker compose")
    for step in run_steps():
        for line in (raw.strip() for raw in step.splitlines()):
            if not line or line.startswith("#"):
                continue
            assert line.startswith(allowed_prefixes), f"CI runs logic of its own: {line}"


def test_ci_does_not_interpolate_untrusted_input():
    """A run step containing an expression is how workflow injection happens."""
    for step in run_steps():
        assert "${{" not in step, f"run step interpolates an expression: {step}"


def test_workflow_declares_least_privilege_permissions():
    assert workflow().get("permissions") == {"contents": "read"}
