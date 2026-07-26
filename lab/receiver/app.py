"""Webhook receiver standing in for a paging vendor.

Records every Alertmanager notification with the wall-clock time it arrived, which is
what lets the drill measure delivery latency from the receiving end rather than trusting
a timestamp the sender chose.
"""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CAPTURE = os.environ.get("DRILL_CAPTURE_PATH", "/captures/notifications.json")
lock = threading.Lock()
received: list[dict] = []


def _persist() -> None:
    tmp = f"{CAPTURE}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(received, handle, indent=2)
    os.replace(tmp, CAPTURE)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/notifications":
            with lock:
                self._send(200, {"count": len(received), "notifications": received})
        elif self.path == "/health":
            self._send(200, {"healthy": True})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/reset":
            with lock:
                received.clear()
                _persist()
                self._send(200, {"count": 0})
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid json"})
            return
        entry = {
            "received_at": time.time(),
            "receiver_path": self.path,
            "payload": payload,
        }
        with lock:
            received.append(entry)
            _persist()
            self._send(200, {"count": len(received)})

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    os.makedirs(os.path.dirname(CAPTURE), exist_ok=True)
    with lock:
        _persist()
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
