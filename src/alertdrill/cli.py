"""alertctl, the single operator entry point for the drill."""

from __future__ import annotations

import argparse
import subprocess
import sys

from . import config, contract, drill, evidence, observe, runner, safety, tools


def cmd_doctor(_: argparse.Namespace) -> int:
    checks: list[tuple[str, bool, str]] = []

    checks.append(("python >= 3.11", sys.version_info >= (3, 11), sys.version.split()[0]))
    checks.append(("docker daemon reachable", safety.docker_available(), "docker info"))

    try:
        compose = runner.compose_command()
        checks.append(("docker compose", True, " ".join(compose)))
    except runner.ComposeUnavailable as error:
        checks.append(("docker compose", False, str(error)))

    checks.append(("compose file present", config.COMPOSE_FILE.is_file(), str(config.COMPOSE_FILE)))
    checks.append(("contract present", config.CONTRACT.is_file(), str(config.CONTRACT)))

    try:
        loaded = contract.load()
        checks.append(("contract parses", True, f"{len(loaded.rules)} rule(s) declared"))
    except contract.ContractError as error:
        checks.append(("contract parses", False, str(error)))

    rule_files = sorted(config.RULES_DIR.glob("*.rules.yml"))
    checks.append(("rule files present", bool(rule_files), f"{len(rule_files)} file(s)"))

    width = max(len(name) for name, _, _ in checks)
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {detail}")

    failed = [name for name, ok, _ in checks if not ok]
    if failed:
        print(f"\ndoctor failed: {', '.join(failed)}")
        return 1
    print("\ndoctor passed")
    return 0


def cmd_up(_: argparse.Namespace) -> int:
    subprocess.run([*runner.compose_base(), "up", "--build", "--detach"], check=True)
    pending = runner.wait_until_ready()
    if pending:
        print(f"stack did not become ready: {', '.join(pending)}")
        return 1
    print("stack is up and every endpoint answers")
    return cmd_status(argparse.Namespace())


def cmd_down(_: argparse.Namespace) -> int:
    # Compose is scoped to this project name, so it can only remove what this project owns.
    subprocess.run(
        [*runner.compose_base(), "down", "--volumes", "--remove-orphans"],
        check=True,
    )
    remaining = safety.project_containers()
    if remaining:
        print(f"teardown left {len(remaining)} container(s) behind")
        return 1
    print("teardown removed every alertdrill container")
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    containers = safety.project_containers()
    if not containers:
        print("no alertdrill containers")
        return 1
    for container in containers:
        print(f"{container['State']:<10} {container['Names']:<28} {container['Image']}")

    unreachable = [name for name, url in runner.endpoints().items() if not runner.reachable(url)]
    for name, url in runner.endpoints().items():
        print(f"{'up  ' if name not in unreachable else 'down'}  {name:<13} {url}")
    return 1 if unreachable else 0


def cmd_validate(_: argparse.Namespace) -> int:
    """Static checks. Nothing here needs the stack running."""
    results = [tools.check_prometheus_config(), tools.check_alertmanager_config()]
    rule_files = sorted(config.RULES_DIR.glob("*.rules.yml"))
    if not rule_files:
        print("FAIL  no rule files found, so validation would pass without checking anything")
        return 1
    results.extend(tools.check_rule_file(path) for path in rule_files)

    rule_tests = sorted(config.RULE_TESTS.glob("*.test.yml"))
    if not rule_tests:
        print("FAIL  no rule unit tests found, so the rules are only checked for syntax")
        return 1
    results.extend(tools.run_rule_unit_tests(path) for path in rule_tests)

    for result in results:
        print(f"{'PASS' if result.passed else 'FAIL'}  {result.name}")
        if not result.passed:
            for line in result.output.splitlines():
                print(f"        {line}")

    failed = [result.name for result in results if not result.passed]

    # Second phase. Everything above proves the good files are accepted, which a validator
    # that accepted anything would also do. These fixtures must be rejected.
    print()
    for name in config.NEGATIVE_RULE_FIXTURES:
        rejected = not tools.check_rule_file(config.FIXTURES / name).passed
        print(f"{'PASS' if rejected else 'FAIL'}  rejects {name}")
        if not rejected:
            failed.append(f"{name} was accepted")
    for name in config.NEGATIVE_ALERTMANAGER_FIXTURES:
        rejected = not tools.check_alertmanager_config(config.FIXTURES / name).passed
        print(f"{'PASS' if rejected else 'FAIL'}  rejects {name}")
        if not rejected:
            failed.append(f"{name} was accepted")

    total = len(results) + len(config.NEGATIVE_RULE_FIXTURES) + len(
        config.NEGATIVE_ALERTMANAGER_FIXTURES
    )
    if failed:
        print(f"\nvalidate failed: {', '.join(failed)}")
        return 1
    print(f"\nvalidate passed, {total} check(s), including {total - len(results)} that must fail")
    return 0


def _run_all_rules() -> list[drill.RuleResult]:
    loaded = contract.load()
    results = []
    for rule in loaded.rules:
        drill.require_healthy_baseline(rule)
        print(f"drilling {rule.alert}")
        result = drill.run_rule(rule)
        results.append(result)

        width = max(len(check.name) for check in result.checks)
        for check in result.checks:
            mark = "PASS" if check.passed else "FAIL"
            print(f"  {mark}  {check.name.ljust(width)}  expected {check.expected!r}", end="")
            print("" if check.passed else f", observed {check.observed!r}")

        fired = "not observed" if result.fire_seconds is None else f"{result.fire_seconds}s"
        cleared = "not observed" if result.resolve_seconds is None else f"{result.resolve_seconds}s"
        print(f"  fire {fired}, resolve {cleared}")
        print(f"  {result.as_dict()['passed']} of {result.as_dict()['total']} checks passed\n")

    return results


def _report(results: list[drill.RuleResult]) -> int:
    failed = [result.alert for result in results if not result.passed]
    if failed:
        print(f"drill failed: {', '.join(failed)}")
        return 1
    print(f"drill passed, {len(results)} rule(s)")
    return 0


def cmd_drill(_: argparse.Namespace) -> int:
    """Break the target for real, measure what reached the receiver, then restore it."""
    return _report(_run_all_rules())


def cmd_evidence(_: argparse.Namespace) -> int:
    """One drill, three reports. All rendered from the same result so they cannot disagree."""
    results = _run_all_rules()
    paths = evidence.write_all(results)
    for name, path in paths.items():
        print(f"  {name:<9} {path}")
    return _report(results)


def cmd_test(_: argparse.Namespace) -> int:
    # check=False on purpose: pytest's exit code is the result being reported, not an error
    # in running it, so it is returned rather than raised.
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"], cwd=config.ROOT, check=False
    )
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="alertctl",
        description="Prove Prometheus alert rules fire, route, and resolve.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("doctor", help="check the operator environment").set_defaults(fn=cmd_doctor)
    commands.add_parser("up", help="start the isolated drill stack").set_defaults(fn=cmd_up)
    commands.add_parser("down", help="remove only this project's containers").set_defaults(
        fn=cmd_down
    )
    commands.add_parser("status", help="report stack and endpoint health").set_defaults(
        fn=cmd_status
    )
    commands.add_parser("validate", help="check the rules and configs statically").set_defaults(
        fn=cmd_validate
    )
    commands.add_parser("drill", help="fire each declared rule for real and measure").set_defaults(
        fn=cmd_drill
    )
    commands.add_parser("evidence", help="drill once, write JSON, Markdown, and JUnit").set_defaults(
        fn=cmd_evidence
    )
    commands.add_parser("test", help="run unit and contract tests").set_defaults(fn=cmd_test)

    args = parser.parse_args(argv)
    try:
        return int(args.fn(args))
    except safety.SafetyError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    except runner.ComposeUnavailable as error:
        print(f"unavailable: {error}", file=sys.stderr)
        return 2
    except drill.DrillError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    except observe.ObservationError as error:
        # Never a pass. If the stack cannot be read, nothing was proven either way.
        print(f"could not observe the stack: {error}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as error:
        print(f"command failed with exit {error.returncode}", file=sys.stderr)
        return error.returncode


if __name__ == "__main__":
    raise SystemExit(main())
