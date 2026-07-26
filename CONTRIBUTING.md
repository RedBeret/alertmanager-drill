# Contributing

## Before you start

```bash
./scripts/bootstrap.sh
./scripts/lab.sh doctor
./scripts/lab.sh test
```

`doctor` must pass before anything else is worth debugging. It checks the Python version,
the Docker daemon, which Compose command is available, and that the contract parses.

## The rule that matters most

Every gate in this project must be able to fail. Before accepting a new check, break the
thing it guards and confirm the check goes red. A gate that has only ever been observed
passing is not evidence.

The same applies to the contract. A check that compares an observation the stack did not
supply must fail, never pass by default.

## Style

- Plain declarative sentences in prose and commit messages. No marketing tone.
- No em dashes or en dashes anywhere. Use a hyphen, a comma, or reword.
- Match the surrounding code. Comments are sparse and explain why, not what.
- Keep pull requests small and merge each one before starting the next.

## Checks that run in CI

```bash
./scripts/lab.sh test
./.venv/bin/ruff check src tests lab
bash -n scripts/bootstrap.sh
bash -n scripts/lab.sh
```

CI runs the same `./scripts/lab.sh` entrypoints a workstation does. Do not add drill logic
to the workflow file; add it to `alertctl` and call it from both.

## Isolation

Do not add a published port that binds beyond `127.0.0.1`, and do not add a destructive
action that does not check the Compose project label first. There are tests for both.
