"""Target service the drill breaks on purpose.

Exposes a Prometheus gauge and two control endpoints. The drill calls /break to start
the alerting condition and /fix to clear it, so the alert fires from a real state change
in a real scrape rather than from a metric written directly into Prometheus.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SERVICE = os.environ.get("DRILL_SERVICE_NAME", "drill-target")
state = {"healthy": True, "changed_at": None}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict) -> None:
        self._send(code, json.dumps(payload).encode(), "application/json")

    def do_GET(self) -> None:
        if self.path == "/metrics":
            healthy = 1 if state["healthy"] else 0
            body = (
                "# HELP drill_service_healthy Whether the target reports itself healthy.\n"
                "# TYPE drill_service_healthy gauge\n"
                f'drill_service_healthy{{service="{SERVICE}"}} {healthy}\n'
            ).encode()
            self._send(200, body, "text/plain; version=0.0.4")
        elif self.path in ("/", "/health"):
            code = 200 if state["healthy"] else 503
            self._json(code, {"service": SERVICE, "healthy": state["healthy"]})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path not in ("/break", "/fix"):
            self._json(404, {"error": "not found"})
            return
        state["healthy"] = self.path == "/fix"
        self._json(200, {"service": SERVICE, "healthy": state["healthy"]})

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
