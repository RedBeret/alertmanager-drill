# alertmanager-drill

[![CI](https://github.com/RedBeret/alertmanager-drill/actions/workflows/ci.yml/badge.svg)](https://github.com/RedBeret/alertmanager-drill/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Prometheus](https://img.shields.io/badge/Prometheus-3.7-E6522C?logo=prometheus&logoColor=white)](compose.yml)

Most alert rules have never fired outside the editor they were written in. They are
committed, reviewed, and trusted for years without anyone confirming that the rule
evaluates, that Alertmanager routes it to the right receiver, that the notification
arrives, or that it clears when the condition does.

alertmanager-drill proves those things for a declared set of rules. It drives a real
service into a real failing state, measures how long the notification actually took to
arrive, checks it against the receiver and labels the contract declares, remediates the
condition, and requires the resolved notification to arrive too.

Everything runs locally in WSL with Docker. No cloud account, paging vendor, or
production credentials are required.

## Current state

Stages 1 and 2 of 6 are complete: the contract, the isolated stack, the operator
commands, and the full static gate. The live drill lands in the stages below.

- declared alerting contract in `drill/contract.yaml`
- isolated four-service stack on loopback-only ports
- Compose project label used as the safety boundary before any destructive action
- `alertctl` operator command with `doctor`, `up`, `down`, `status`, `validate`, and `test`
- readiness polled against each service's own endpoint rather than container state
- static validation with promtool and amtool run from the images the stack itself uses
- negative fixtures the validators must reject, so the gate is provably live
- rule unit tests over synthetic series, asserting what does and does not fire
- 43 unit and contract tests, including checks that no gate can pass vacuously

## Architecture

```mermaid
flowchart LR
    OP["WSL operator"] --> CLI["alertctl"]
    CLI --> TGT["Target service"]
    TGT --> PROM["Prometheus, scrape and rule evaluation"]
    PROM --> AM["Alertmanager, routing and grouping"]
    AM --> RCV["Webhook receiver"]
    RCV --> EV["Measured latency and delivered payload"]
```

The target service exposes a gauge and two control endpoints. The drill calls `/break` to
start the condition and `/fix` to clear it, so the alert fires from a real state change
observed in a real scrape rather than from a metric written directly into Prometheus.

## Requirements

- WSL2 with an Ubuntu distribution
- Python 3.11 or newer
- Docker with a reachable daemon
- Docker Compose v1 or v2

## Quick start

```bash
git clone https://github.com/RedBeret/alertmanager-drill.git
cd alertmanager-drill
./scripts/bootstrap.sh
./scripts/lab.sh doctor
./scripts/lab.sh up
```

`up` builds the two lab images, starts all four services, and then polls every service's
own endpoint until it answers. It reports which service failed to become ready rather
than a bare timeout.

## Commands

| Command | What it does |
| --- | --- |
| `doctor` | check Python, the Docker daemon, the Compose command, and that the contract parses |
| `up` | start the isolated stack and wait for every endpoint to answer |
| `status` | report container state and endpoint reachability |
| `validate` | check the Prometheus config, the rule files, and the Alertmanager config |
| `drill` | break the target for real, measure what reached the receiver, then restore it |
| `evidence` | drill once and write JSON, Markdown, and JUnit that agree |
| `silence-drill` | prove a silence suppresses delivery rather than the alert being broken |
| `down` | remove only this project's containers, networks, and volumes |
| `clean-room` | tear down and prove every neighbouring container was untouched |
| `test` | run the unit and contract tests |

Every command runs through `./scripts/lab.sh`, which is a thin wrapper around the
project-local `alertctl`. CI runs the same entrypoints, so it cannot drift from a
workstation.

## Static validation

```bash
./scripts/lab.sh validate
```

`validate` runs `promtool check config`, `promtool check rules` on every rule file, and
`amtool check-config`. It needs no running stack.

It then does the half that matters more. A validator that accepted anything would also
pass every check above, so `validate` keeps fixtures that must be rejected and fails if any
of them is accepted:

| Fixture | Why it must fail |
| --- | --- |
| `unparseable-expression.rules.yml` | the expression is not valid PromQL |
| `missing-expression.rules.yml` | labels, annotations, and a `for` duration but no `expr`, which is the shape a half-finished rule actually takes |
| `undefined-receiver.alertmanager.yml` | the route sends everything to a receiver that is not defined |

Repairing any fixture makes `validate` exit non-zero and name it, which is how the second
phase was checked rather than assumed.

## Rule unit tests

`validate` also runs `promtool test rules`, which drives synthetic series through the real
rule files and asserts exactly which alerts exist at a given second, with which labels and
annotations. Syntax checking only proves a rule parses. These prove it fires when it should
and, just as importantly, stays quiet when it should not:

- nothing fires while the target is healthy
- nothing fires while the condition is younger than the rule's `for` duration, so a single
  bad scrape does not page
- past the `for` duration the alert exists carrying every label the Alertmanager route
  matches on
- a target that recovers inside the `for` window never fires at all
- an unscrapeable target raises the warning alert, not the critical one, so a network blip
  does not page as a service fault

The assertions are tied to `for: 15s` in `drill.rules.yml`. Changing that duration to 60s
makes them fail, and so does changing the `team` label. Both were checked by making the
change and watching the suite go red.

`tests/test_rule_tests.py` guards the guards: it fails if a test file asserts nothing, if
no assertion expects an alert to fire, if none expects an alert to be absent, if a rule the
contract drills has no unit test, or if a unit test does not pin a label the contract
routes on.

Both tools ship inside the Prometheus and Alertmanager images the stack already pins, so
they are run from those images rather than installed separately. The validator is then the
same build as the runtime and the two cannot drift. The configs are mounted at the same
paths the running containers use, so promtool resolves the `rule_files` glob exactly the
way Prometheus will. `tests/test_tools.py` fails if those two mount paths ever diverge,
because that divergence is silent: validation would pass while the stack stayed wrong.

## The drill

```bash
./scripts/lab.sh drill
```

For each rule the contract declares, `drill` breaks the target through the target's own
API, waits for the notification, compares it against what was declared, clears the
condition, and requires the resolved notification too.

Latency is measured from the moment the condition began, not from when Prometheus noticed
or when the observer started polling. The gap between those is exactly the delay an on-call
engineer lives through, and a stopwatch started later would hide the front of it.

Restoring the target runs in a `finally` block. A drill that raises partway still leaves
the target healthy, because otherwise the next run starts dirty and its baseline means
nothing. The drill also refuses to start if the alert is already firing, or if Prometheus
has never heard of the rule the contract names.

A sample run:

```
PASS  firing.delivered               expected True
PASS  firing.latency                 expected 'within 60s'
PASS  firing.receiver                expected 'oncall-critical'
PASS  firing.label.severity          expected 'critical'
PASS  firing.label.team              expected 'platform'
PASS  firing.annotation.summary      expected True
PASS  firing.annotation.description  expected True
PASS  resolved.delivered             expected True
PASS  resolved.latency               expected 'within 60s'
PASS  resolved.receiver              expected 'oncall-critical'
fire 20.3s, resolve 4.25s
```

Declaring the wrong receiver makes it exit 1 with `firing.receiver` failing while
`firing.delivered` still passes, which is the point: an alert that fires correctly and
reaches the wrong team is still a paging failure.

## Suppression

```bash
./scripts/lab.sh silence-drill
```

A silenced alert and a broken alert both deliver nothing. Checking only that no
notification arrived would pass just as happily against a rule that never fired, so the
drill requires two things at once: Alertmanager must report the alert as `suppressed`, and
the receiver must stay empty.

Pointing the contract at a condition that never fires shows why both are needed:

```
FAIL  silenced.alertmanager_state  expected 'suppressed', observed None
PASS  silenced.no_delivery         expected 0
```

The delivery check passes there. Only the state check catches it.

Silences are removed in a `finally` block and the command fails if any active silence is
left behind, because a leftover silence would suppress the next drill and make a broken
alerting path look healthy.

## Evidence

```bash
./scripts/lab.sh evidence
```

Runs the drill once and renders three reports from the same in-memory result:
`artifacts/evidence/drill.json` is authoritative, `drill.md` is the operator view, and
`drill.xml` is JUnit so CI shows a failed comparison as a failed test rather than a log
line nobody opens.

Rendering all three from one result is deliberate. Reports built from separate passes over
the stack are how a JSON file and a Markdown file end up disagreeing about whether a
release was good, and a reviewer has no way to tell which one lied. `tests/test_evidence.py`
fails if the outcome or the counts differ between formats, if a run with zero checks
renders as a pass, if a missing latency is written as `0s` instead of `not observed`, or if
any report contains credential-shaped text.

## Continuous integration

`.github/workflows/ci.yml` runs the same `./scripts/lab.sh` entrypoints a workstation does,
in two jobs. `validate` is the static gate. `live` starts the real stack, drills every
declared rule, proves suppression, writes evidence, and publishes it as an artifact.

The live job waits on the static gate, because starting containers before the rules are
known to parse wastes a runner and buries the real error under a timeout. Teardown runs
under `if: always()`, so a run that fails a gate still leaves nothing behind.

The pipeline holds no drill logic of its own. `tests/test_ci.py` fails if any run step is
something other than a project entrypoint, if a gate stops being invoked, if teardown
becomes conditional on success, if the evidence upload is allowed to find no files, or if a
run step interpolates a `${{ }}` expression.

`clean-room` is deliberately excluded and there is a test recording why: it deletes the
stack and refuses without a neighbouring container, which a fresh runner does not have.

## What the contract declares

`drill/contract.yaml` declares, for each rule under test, the condition that makes it
fire, the maximum seconds to notification, the receiver it must arrive at, the labels and
annotation keys it must carry, and the maximum seconds to resolution.

Every check records the expected value, the observed value, and a pass field. A reading
the stack does not supply compares unequal and fails, so a missing observation is never an
implicit pass. A notification that arrives at the wrong receiver fails routing even though
the rule fired correctly.

## Proving teardown leaves a clean room

```bash
./scripts/lab.sh clean-room
```

Surveys every container on the host, tears the stack down, surveys again, and compares.
Two things must hold. No `alertdrill` container survives in any state, because a stopped
container is still one left behind and `exited` is not a pass. And every neighbouring
container is in exactly the state it was in beforehand.

Neighbours are compared by state, not by count. A teardown that stopped a neighbour would
leave the count identical and look clean, so `neighbours.count` passing while
`neighbours.unchanged` fails is a case the tests cover deliberately.

The command refuses to run when no neighbouring container exists at all, since a clean room
proved in an empty room demonstrates nothing about isolation. It also refuses when nothing
of ours is running, since there would be nothing to tear down.

Because it deletes the stack, this is not part of CI. Run `./scripts/lab.sh up` afterwards.

## Isolation

Every container carries the Compose project label `alertdrill`, and `safety.py` refuses to
act on a container that does not. Every published port binds to `127.0.0.1` only:
Prometheus 19090, Alertmanager 19093, the receiver 19094, and the target 19095. Teardown
removes only `alertdrill` containers, networks, and volumes.

## Challenges and resolutions

**The receiver could not write its capture file.** The container runs as UID 10001 and the
named volume mounted at `/captures` was created root-owned, so the first write failed with
`Permission denied` and the service exited before serving anything. The directory is now
created in the image and given to the runtime user, because Docker copies ownership from
the image when it first populates a named volume.

**Compose v1 rejected the compose file.** The file used the top-level `name:` key from the
Compose specification, which v1 does not accept, and WSL boxes still commonly ship v1
1.29.2. The project name comes from `-p` in the command builder instead. The Compose
command is now detected rather than assumed, and `up --wait` is not used because v1 has no
such flag and it would report the container started rather than the service answering.

## Roadmap

| Stage | Delivers |
| --- | --- |
| 1 | contract, isolated stack, operator commands (done) |
| 2 | promtool rule validation and negative fixtures that must fail (done) |
| 3 | live fire drill with measured latency (done) |
| 4 | routing and resolution checks against the declared receiver (done) |
| 5 | silence handling (done) |
| 6 | JSON, Markdown, and JUnit evidence, CI, and the clean-room teardown proof (done) |

The full plan and the twelve done criteria are in
[docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md).
