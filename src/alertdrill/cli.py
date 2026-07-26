"""alertctl, the single operator entry point for the drill."""

from __future__ import annotations

import argparse
import subprocess
import sys

from . import config, contract, runner, safety


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
    except subprocess.CalledProcessError as error:
        print(f"command failed with exit {error.returncode}", file=sys.stderr)
        return error.returncode


if __name__ == "__main__":
    raise SystemExit(main())
