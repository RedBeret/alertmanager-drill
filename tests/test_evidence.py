"""The three reports must agree, and none may leak a secret.

Disagreement is the interesting failure. If JSON says pass and Markdown says fail, a
reviewer has no way to tell which one lied, and the evidence is worth less than nothing
because it looks authoritative.
"""

from __future__ import annotations

import json
from xml.etree import ElementTree

from alertdrill import evidence
from alertdrill.drill import Check, RuleResult


def passing_result() -> RuleResult:
    return RuleResult(
        alert="TargetServiceDown",
        checks=[
            Check("firing.delivered", True, True),
            Check("firing.receiver", "oncall-critical", "oncall-critical"),
        ],
        fire_seconds=20.3,
        resolve_seconds=4.25,
    )


def failing_result() -> RuleResult:
    return RuleResult(
        alert="TargetServiceDown",
        checks=[
            Check("firing.delivered", True, True),
            Check("firing.receiver", "oncall-critical", "default"),
            Check("resolved.delivered", True, False),
        ],
        fire_seconds=20.3,
        resolve_seconds=None,
    )


def test_counts_reconcile():
    report = evidence.build_report([failing_result()])
    assert report["passed"] + report["failed"] == report["total"]
    assert report["total"] == 3
    assert report["failed"] == 2


def test_outcome_is_fail_when_any_check_fails():
    assert evidence.build_report([failing_result()])["outcome"] == "fail"


def test_outcome_is_pass_only_when_everything_passed():
    assert evidence.build_report([passing_result()])["outcome"] == "pass"


def test_an_empty_run_is_not_a_pass():
    """Zero checks means nothing was proven, which must never render as success."""
    report = evidence.build_report([])
    assert report["outcome"] == "fail"
    assert report["total"] == 0


def test_all_three_formats_agree_on_outcome_and_counts(tmp_path):
    paths = evidence.write_all([failing_result()], tmp_path)

    loaded = json.loads(paths["json"].read_text(encoding="utf-8"))
    markdown = paths["markdown"].read_text(encoding="utf-8")
    root = ElementTree.fromstring(paths["junit"].read_text(encoding="utf-8"))

    assert loaded["outcome"] == "fail"
    assert f"Outcome: **{loaded['outcome']}**" in markdown
    assert (
        f"{loaded['passed']} passed, {loaded['failed']} failed, {loaded['total']} total"
        in markdown
    )
    assert root.attrib["tests"] == str(loaded["total"])
    assert root.attrib["failures"] == str(loaded["failed"])
    assert len(root.findall(".//testcase")) == loaded["total"]
    assert len(root.findall(".//failure")) == loaded["failed"]


def test_junit_marks_exactly_the_failed_checks(tmp_path):
    paths = evidence.write_all([failing_result()], tmp_path)
    root = ElementTree.fromstring(paths["junit"].read_text(encoding="utf-8"))
    failed = {
        case.attrib["name"] for case in root.findall(".//testcase") if case.find("failure") is not None
    }
    assert failed == {"firing.receiver", "resolved.delivered"}


def test_an_unobserved_latency_is_rendered_as_such_not_as_zero(tmp_path):
    """Rendering a missing measurement as 0s would read as instant delivery."""
    paths = evidence.write_all([failing_result()], tmp_path)
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "resolve not observed" in markdown
    assert "resolve 0s" not in markdown


def test_reports_contain_no_credential_material(tmp_path):
    paths = evidence.write_all([passing_result(), failing_result()], tmp_path)
    banned = ("password", "secret", "token", "bearer", "authorization", "api_key")
    for path in paths.values():
        body = path.read_text(encoding="utf-8").lower()
        for word in banned:
            assert word not in body, f"{path.name} contains {word}"


def test_every_file_is_written(tmp_path):
    paths = evidence.write_all([passing_result()], tmp_path)
    assert set(paths) == {"json", "markdown", "junit"}
    for path in paths.values():
        assert path.is_file() and path.stat().st_size > 0
