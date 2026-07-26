# alertmanager-drill project plan

## Objective

Most alert rules have never fired outside the editor they were written in. They are
committed, reviewed, and trusted for years without anyone confirming that the rule
evaluates, that Alertmanager routes it to the right receiver, that the notification
arrives, or that it clears when the condition does.

alertmanager-drill proves those things for a declared set of rules. It drives a real
service into a real failing state, measures how long the notification actually took to
arrive, checks it against the receiver and labels the contract declares, remediates the
condition, and requires the resolved notification to arrive too. It emits evidence an
operator or reviewer can read.

The lab runs locally in WSL with Docker. No cloud account, paging vendor, or production
credentials are required.

## Version 1 scope

- Run natively from Ubuntu WSL with Docker.
- Stand up Prometheus, Alertmanager, a webhook receiver, and a target service that can
  be driven into a failing state on demand.
- Declare expected alerting behavior in `drill/contract.yaml`.
- Validate rule files with `promtool` before anything runs.
- Reject a malformed rule file and a rule whose expression cannot fire.
- Drive the target into the alerting condition through its own API, not by writing
  metrics directly into Prometheus.
- Measure fire latency from the moment the condition begins to the moment the webhook
  receives the notification.
- Compare the delivered notification against the declared receiver, labels, annotations,
  and severity.
- Clear the condition and require a resolved notification within a declared bound.
- Prove a silence suppresses delivery, and that suppression is reported as suppressed
  rather than counted as a pass.
- Produce JSON, Markdown, and JUnit evidence from one drill result.
- Provide a GitHub Actions pipeline and a local runner that execute the same commands.

## Non-goals

- A production alerting stack or a replacement for one.
- Paging vendor integration. The webhook receiver stands in for PagerDuty, Opsgenie, or
  Slack, and the contract checks routing and payload, not vendor delivery.
- Claiming a laptop measurement predicts production notification latency. The measured
  number is evidence that the path works and a bound on this stack, not a capacity claim.
- Testing Prometheus or Alertmanager themselves. Upstream correctness is assumed; what is
  under test is this repository's rules, routes, and receivers.
- Leaving the lab in a broken state. Every drill restores the condition it injected.

## Isolation and safety contract

- Every container carries the Compose project label `alertdrill`.
- Every published port binds to `127.0.0.1` only: Prometheus 19090, Alertmanager 19093,
  the webhook receiver 19094, and the target service 19095.
- Destructive commands verify the Compose project label before acting and refuse to
  operate on a container that does not carry it.
- Teardown removes only `alertdrill` containers, networks, and volumes.
- Neighbouring Docker containers must be left in the exact state they were in before a
  drill, and a teardown proof compares them by state rather than by count.
- Generated evidence, receiver captures, and local environment files are ignored by Git.

## Drill contract

`drill/contract.yaml` declares, for each rule under test:

- rule name and the rule file it lives in
- the condition command that makes it fire and the command that clears it
- maximum seconds from condition start to notification received
- maximum seconds from condition cleared to resolved notification received
- the receiver the notification must arrive at
- required labels, including severity
- required annotation keys
- whether the rule is expected to be suppressed by an active silence

Every check records the expected value, the observed value, and a pass field. A reading
the stack does not supply compares unequal and fails. A missing observation is never an
implicit pass, and a notification that arrives at the wrong receiver fails routing even
though it fired correctly.

## Evidence contract

The JSON report is authoritative and contains:

- report format version and timestamps
- the drill contract identity and the rule set under test
- tool and image versions
- every check with expected, observed, and pass fields
- measured fire latency and resolve latency per rule
- the receiver each notification actually arrived at
- suppression results for silenced rules
- overall outcome and failure reasons

The Markdown report is the operator view. JUnit is the CI test-report view. All three
outputs must agree on the overall outcome and the passed, failed, and total counts, and
none may contain a webhook credential or bearer token.

## Delivery stages

1. Contract, repository, toolchain, and the isolated Docker stack.
2. Static rule validation with promtool, including negative fixtures.
3. Live fire drill: real condition, measured latency, delivered notification.
4. Routing and resolution checks against the declared receiver and labels.
5. Silence and inhibition handling.
6. Multi-format evidence, GitHub Actions pipeline, and the clean-room teardown proof.

## Done criteria

Version 1 is complete only when all of the following are demonstrated from a clean clone:

1. `./scripts/bootstrap.sh` and `./scripts/lab.sh doctor` succeed on a fresh WSL clone.
2. `up` produces healthy Prometheus, Alertmanager, receiver, and target containers, all
   carrying the `alertdrill` project label.
3. `validate` passes the committed rules through promtool and rejects both a malformed
   rule file and a rule whose expression can never fire.
4. A declared rule fires from a condition injected through the target's own API, and the
   webhook receiver records the notification.
5. Fire latency is measured from condition start and compared against the declared bound,
   and exceeding the bound fails the drill.
6. The notification is checked against the declared receiver, labels, and annotation keys,
   and a rule routed to the wrong receiver fails while still firing.
7. Clearing the condition produces a resolved notification within the declared bound.
8. An active silence suppresses delivery, and the drill reports it as suppressed rather
   than as a pass.
9. JSON, Markdown, and JUnit evidence agree on outcome and counts and contain no secrets.
10. Local runs and GitHub Actions execute the same `./scripts/lab.sh` entrypoints, with no
    drill logic duplicated into CI.
11. Unit, contract, and gate tests pass, along with lint and shell syntax checks.
12. `down` leaves no `alertdrill` containers, and every neighbouring container is left in
    the exact state it was in beforehand.
