#!/usr/bin/env bash
# The single operator entry point. Every command is a real alertctl subcommand, so CI and a
# workstation cannot drift apart by running different logic.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

if [[ ! -x .venv/bin/alertctl ]]; then
  echo "alertctl is not installed. Run ./scripts/bootstrap.sh first." >&2
  exit 1
fi

exec ./.venv/bin/alertctl "$@"
