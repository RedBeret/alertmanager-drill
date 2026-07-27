"""Turning one drill result into the three reports the evidence contract promises.

All three are rendered from the same in-memory result. Rendering them from separate passes
over the stack is how a JSON report and a Markdown report end up disagreeing about whether
a release was good, and a reviewer has no way to tell which one lied.

The JSON is authoritative. Markdown is the operator view. JUnit is what CI turns into a
test report, so a failed comparison shows up as a failed test rather than a log line
nobody opens.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

from . import config
from .drill import RuleResult

FORMAT_VERSION = 1


def build_report(results: list[RuleResult], generated_at: str | None = None) -> dict:
    rules = [result.as_dict() for result in results]
    passed = sum(rule["passed"] for rule in rules)
    failed = sum(rule["failed"] for rule in rules)

    failures = [
        f"{rule['alert']}.{check['name']}"
        for rule in rules
        for check in rule["checks"]
        if not check["pass"]
    ]

    return {
        "format_version": FORMAT_VERSION,
        "generated_at": generated_at
        or datetime.now(UTC).replace(microsecond=0).isoformat(),
        "images": {
            "prometheus": config.PROMETHEUS_IMAGE,
            "alertmanager": config.ALERTMANAGER_IMAGE,
            "lab_base": config.PYTHON_BASE_IMAGE,
        },
        "rules": rules,
        "passed": passed,
        "failed": failed,
        "total": passed + failed,
        "outcome": "pass" if failed == 0 and passed > 0 else "fail",
        "failures": failures,
    }


def to_markdown(report: dict) -> str:
    lines = [
        "# alertmanager-drill evidence",
        "",
        f"Outcome: **{report['outcome']}**",
        "",
        f"- generated: {report['generated_at']}",
        (
            f"- checks: {report['passed']} passed, {report['failed']} failed, "
            f"{report['total']} total"
        ),
        f"- prometheus: `{report['images']['prometheus']}`",
        f"- alertmanager: `{report['images']['alertmanager']}`",
        "",
    ]
    for rule in report["rules"]:
        fired = "not observed" if rule["fire_seconds"] is None else f"{rule['fire_seconds']}s"
        cleared = (
            "not observed" if rule["resolve_seconds"] is None else f"{rule['resolve_seconds']}s"
        )
        lines += [
            f"## {rule['alert']}",
            "",
            f"Outcome: {rule['outcome']}. Fire {fired}, resolve {cleared}.",
            "",
            "| Check | Expected | Observed | Result |",
            "| --- | --- | --- | --- |",
        ]
        for check in rule["checks"]:
            mark = "pass" if check["pass"] else "fail"
            lines.append(
                f"| {check['name']} | `{check['expected']}` | `{check['observed']}` | {mark} |"
            )
        lines.append("")

    if report["failures"]:
        lines += ["## Failures", ""]
        lines += [f"- {name}" for name in report["failures"]]
        lines.append("")
    return "\n".join(lines)


def to_junit(report: dict) -> str:
    suites = ElementTree.Element(
        "testsuites",
        {
            "name": "alertmanager-drill",
            "tests": str(report["total"]),
            "failures": str(report["failed"]),
        },
    )
    for rule in report["rules"]:
        suite = ElementTree.SubElement(
            suites,
            "testsuite",
            {
                "name": rule["alert"],
                "tests": str(rule["total"]),
                "failures": str(rule["failed"]),
            },
        )
        for check in rule["checks"]:
            case = ElementTree.SubElement(
                suite,
                "testcase",
                {"classname": rule["alert"], "name": check["name"]},
            )
            if not check["pass"]:
                failure = ElementTree.SubElement(
                    case,
                    "failure",
                    {"message": f"expected {check['expected']!r}, observed {check['observed']!r}"},
                )
                failure.text = f"{check['name']} did not match the contract"
    return ElementTree.tostring(suites, encoding="unicode")


def write_all(results: list[RuleResult], directory: Path | None = None) -> dict[str, Path]:
    target = directory or config.EVIDENCE
    target.mkdir(parents=True, exist_ok=True)
    report = build_report(results)

    paths = {
        "json": target / "drill.json",
        "markdown": target / "drill.md",
        "junit": target / "drill.xml",
    }
    paths["json"].write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    paths["markdown"].write_text(to_markdown(report) + "\n", encoding="utf-8")
    paths["junit"].write_text(to_junit(report) + "\n", encoding="utf-8")
    return paths
