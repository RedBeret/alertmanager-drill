# Work log

## 2026-07-26 - Stage 1

- Selected the repository name `alertmanager-drill` after checking the naming convention
  in the Prometheus ecosystem. Nothing in the prometheus org takes a `prometheus-` prefix,
  and third-party tools that operate on Prometheus mostly do not either.
- Confirmed the name was unused on GitHub before creating the repository.
- Created the repository with `delete_branch_on_merge`, topics, and the wiki and projects
  tabs already set, rather than leaving them to be fixed later.
- Wrote the project plan first, before any code, so the twelve done criteria exist to
  verify against.
- Chose ports 19090, 19093, 19094, and 19095, all bound to `127.0.0.1`, and confirmed they
  did not collide with the neighbouring labs.
- Built the target service so the drill breaks it through its own API. Writing a metric
  directly into Prometheus would prove the rule expression matches a number, not that a
  real state change produces a page.
- Built the receiver to record wall-clock arrival time, so latency is measured at the
  receiving end rather than from a timestamp the sender chose.
- Hit `PermissionError` on `/captures/notifications.json.tmp`. The named volume was
  created root-owned and the container runs as UID 10001. Fixed by creating the directory
  in the image and chowning it there, since Docker copies image ownership when it first
  populates a named volume.
- Hit a Compose v1 rejection of the top-level `name:` key. This box has docker-compose
  1.29.2 and no v2 plugin. Added command detection covering both, dropped the key, and
  moved the project name to `-p`. Also dropped `up --wait`, which v1 lacks and which
  reports the container started rather than the service answering.
- Replaced the readiness assumption with polling against each service's own endpoint, and
  made it report which service failed rather than a bare timeout.
- Pyright caught `log_message` overriding the base method with a renamed parameter, and a
  missing `runner` import in a test. Both were real.
- Verified the full path live: broke the target, the notification arrived at
  `oncall-critical` in 24 seconds against a declared bound of 60, carrying
  `severity=critical` and `team=platform`. Fixed the target and the resolved notification
  arrived in 11 seconds.
- 20 tests passing. `doctor` green.


## 2026-07-26 - Stage 2

- Found that promtool ships inside `prom/prometheus` and amtool inside `prom/alertmanager`,
  at exactly the versions already pinned in compose.yml. Ran the validators out of those
  images rather than pinning them separately, so the checker cannot drift from the runtime.
- Mounted the configs at the paths the running containers use, so promtool resolves the
  `rule_files` glob the way Prometheus will. Added a test that fails if those two mount
  paths ever diverge, since that divergence passes validation while the stack stays wrong.
  Checked it by breaking the mountpoint and watching it go red.
- Added three negative fixtures and made validate require their rejection. Everything
  before that only proved good files are accepted, which a validator accepting anything
  would also do. Checked by repairing one fixture: validate exited 1 and named it.
- Added promtool rule unit tests over synthetic series. The negative assertions carry the
  weight: nothing fires inside the `for` window, a target that recovers in time never
  fires, and a scrape failure raises the warning alert rather than the critical one.
- Checked those by changing `for: 15s` to 60s and separately by changing the team label.
  Both failed the suite. Restored and confirmed green.
- Added tests over the unit tests themselves, because a suite that only ever expected
  empty alert lists would pass against a deleted rule file.
- Wired validate into CI, which had been building images and running pytest without ever
  checking a rule file. Added workflow tests that fail if an entrypoint stops being
  invoked or if a run step reimplements what alertctl does.
- Four PRs, #3 through #6. 43 tests, up from 20. validate runs 7 checks.

Next: Stage 3, the live fire drill. Measure latency from condition start rather than from
when Prometheus noticed, and write the first evidence file.
