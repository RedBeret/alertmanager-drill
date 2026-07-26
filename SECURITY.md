# Security policy

## Scope

alertmanager-drill is a local laboratory. It stands up Prometheus, Alertmanager, a webhook
receiver, and a deliberately breakable target service on loopback-only ports. It is not
intended to run in production, to receive production traffic, or to hold real credentials.

## Reporting

Report a vulnerability through GitHub's private security advisory form on this repository.
Please do not open a public issue for something exploitable.

## What the lab already enforces

- every published port binds to `127.0.0.1`, so no service is reachable off the host
- the lab containers run as UID 10001 rather than root
- destructive commands verify the Compose project label first and refuse to act on a
  container that does not carry it
- evidence must not contain webhook credentials or bearer tokens

## Dependencies

Python dependencies are pinned in `requirements-dev.txt` and container images are pinned
to explicit versions in `compose.yml`. Dependabot is enabled for pip, GitHub Actions, and
Docker.

Dependabot raises alerts it does not always open a pull request for, so check
`gh api repos/RedBeret/alertmanager-drill/dependabot/alerts` rather than relying on the
open pull request list alone.
