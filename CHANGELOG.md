# Changelog

## Unreleased

### Added

- `alertctl validate`, running `promtool check config`, `promtool check rules`, and
  `amtool check-config` out of the same images the stack runs, so the validator cannot
  drift from the runtime it validates.
- A test that fails if the paths the validator mounts ever diverge from the paths the
  running containers mount, since that divergence would pass validation silently.
- Negative fixtures that `validate` requires the validators to reject: an unparseable
  PromQL expression, a rule with no `expr` at all, and an Alertmanager route pointing at
  an undefined receiver. Accepting any of them fails the gate and names the fixture.
- `promtool test rules` unit tests driving synthetic series through the real rule files,
  asserting which alerts exist at a given second with which labels and annotations,
  including that nothing fires inside the `for` window and that a scrape failure raises
  the warning alert rather than the critical one.
- Tests that fail if a rule unit test asserts nothing, never expects an alert to fire,
  never expects one to be absent, omits a rule the contract drills, or fails to pin a
  label the Alertmanager route matches on.

- Project plan with twelve testable done criteria and the drill, isolation, and evidence
  contracts.
- Declared alerting contract in `drill/contract.yaml`.
- Isolated four-service stack: Prometheus, Alertmanager, a webhook receiver, and a target
  service that can be driven into a failing state through its own API.
- `alertctl` with `doctor`, `up`, `down`, `status`, and `test`.
- Compose command detection covering both v1 and v2, and readiness polling against each
  service's own endpoint.
- Safety module that refuses to act on a container not carrying the `alertdrill` Compose
  project label.
- 20 unit and contract tests, including checks that an empty or incomplete contract is
  rejected rather than passing vacuously.
- GitHub Actions CI running the same entrypoints as a workstation.

### Fixed

- Receiver exited at startup because the named volume at `/captures` was root-owned and
  the container runs as UID 10001. The directory is created and owned in the image, so
  Docker copies that ownership when it first populates the volume.
- Compose v1 rejected the top-level `name:` key. The project name is supplied by `-p` in
  the command builder instead.
