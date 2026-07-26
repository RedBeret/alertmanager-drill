from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts"
EVIDENCE = ARTIFACTS / "evidence"
STATE = ARTIFACTS / "state"
LAB = ROOT / "lab"
RULES_DIR = LAB / "prometheus" / "rules"
FIXTURES = ROOT / "tests" / "fixtures"
CONTRACT = ROOT / "drill" / "contract.yaml"
COMPOSE_FILE = ROOT / "compose.yml"

# The Compose project name doubles as the safety label. Nothing outside this project
# carries it, so a container without it is never a valid target for a destructive action.
COMPOSE_PROJECT = "alertdrill"
PROJECT_LABEL = "com.docker.compose.project"

PROMETHEUS_PORT = 19090
ALERTMANAGER_PORT = 19093
RECEIVER_PORT = 19094
TARGET_PORT = 19095

PROMETHEUS_URL = f"http://127.0.0.1:{PROMETHEUS_PORT}"
ALERTMANAGER_URL = f"http://127.0.0.1:{ALERTMANAGER_PORT}"
RECEIVER_URL = f"http://127.0.0.1:{RECEIVER_PORT}"
TARGET_URL = f"http://127.0.0.1:{TARGET_PORT}"

PROMETHEUS_IMAGE = "prom/prometheus:v3.7.3"
ALERTMANAGER_IMAGE = "prom/alertmanager:v0.28.1"
PYTHON_BASE_IMAGE = "python:3.12.11-slim"

SERVICES = ("target", "receiver", "prometheus", "alertmanager")
