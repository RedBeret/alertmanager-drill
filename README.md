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

Stage 1 of 6 is complete: the contract, the isolated stack, and the operator commands.
The drill logic itself lands in the stages below.

- declared alerting contract in `drill/contract.yaml`
- isolated four-service stack on loopback-only ports
- Compose project label used as the safety boundary before any destructive action
- `alertctl` operator command with `doctor`, `up`, `down`, `status`, and `test`
- readiness polled against each service's own endpoint rather than container state
- 20 unit and contract tests, including checks that the contract cannot pass vacuously

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
| `down` | remove only this project's containers, networks, and volumes |
| `test` | run the unit and contract tests |

Every command runs through `./scripts/lab.sh`, which is a thin wrapper around the
project-local `alertctl`. CI runs the same entrypoints, so it cannot drift from a
workstation.

## What the contract declares

`drill/contract.yaml` declares, for each rule under test, the condition that makes it
fire, the maximum seconds to notification, the receiver it must arrive at, the labels and
annotation keys it must carry, and the maximum seconds to resolution.

Every check records the expected value, the observed value, and a pass field. A reading
the stack does not supply compares unequal and fails, so a missing observation is never an
implicit pass. A notification that arrives at the wrong receiver fails routing even though
the rule fired correctly.

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
| 2 | promtool rule validation and negative fixtures that must fail |
| 3 | live fire drill with measured latency |
| 4 | routing and resolution checks against the declared receiver |
| 5 | silence and inhibition handling |
| 6 | JSON, Markdown, and JUnit evidence, CI, and the clean-room teardown proof |

The full plan and the twelve done criteria are in
[docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md).
