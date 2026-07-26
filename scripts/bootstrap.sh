#!/usr/bin/env bash
# Build the project-local Python environment. Nothing is installed globally and no system
# package is touched, so a clean clone can be brought up without root.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

./.venv/bin/python -m pip install --quiet --upgrade pip
./.venv/bin/python -m pip install --quiet -r requirements-dev.txt
./.venv/bin/python -m pip install --quiet --editable .

mkdir -p artifacts/evidence artifacts/state

echo "bootstrap complete"
echo "next: ./scripts/lab.sh doctor"
