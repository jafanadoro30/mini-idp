"""
IDP Demo App — generates real HTTP metrics for the Grafana/Prometheus stack.
Exposes /metrics (Prometheus format), /health, and a few dummy endpoints
that intentionally produce varied latencies and occasional 5xx errors.
"""

import random
import time
import threading
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("demo-app")

PORT = 8082

# ── Minimal Prometheus metrics (no external deps) ─────────────────────────────

class Counter:
    def __init__(self, name, help_text, labels=()):
        self.name = name
        self.help = help_text
        self.label_names = labels
        self._values: dict[tuple, float] = {}

    def inc(self, label_values=(), amount=1):
        key = tuple(label_values)
        self._values[key] = self._values.get(key, 0) + amount

    def render(self):
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} counter"]
        for labels, val in self._values.items():
            if labels:
                lstr = ",".join(f'{n}="{v}"' for n, v in zip(self.label_names, labels))
                lines.append(f"{self.name}{{{lstr}}} {val}")
            else:
                lines.append(f"{self.name} {val}")
        return "\n".join(lines)


class Histogram:
    BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]

    def __init__(self, name, help_text, labels=()):
        self.name = name
        self.help = help_text
        self.label_names = labels
        self._counts: dict[tuple, list] = {}
        self._sums: dict[tuple, float] = {}
        self._totals: dict[tuple, float] = {}

    def observe(self, value, label_values=()):
        key = tuple(label_values)
        if key not in self._counts:
            self._counts[key] = [0] * (len(self.BUCKETS) + 1)
            self._sums[key] = 0.0
            self._totals[key] = 0
        for i, b in enumerate(self.BUCKETS):
            if value <= b:
                self._counts[key][i] += 1
        self._counts[key][-1] += 1   # +Inf
        self._sums[key] += value
        self._totals[key] += 1

    def render(self):
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} histogram"]
        for key in self._counts:
            lbase = ""
            if key:
                lbase = ",".join(f'{n}="{v}"' for n, v in zip(self.label_names, key))
            for i, b in enumerate(self.BUCKETS):
                bucket_labels = f'{lbase},le="{b}"' if lbase else f'le="{b}"'
                lines.append(f'{self.name}_bucket{{{bucket_labels}}} {self._counts[key][i]}')
            inf_labels = f'{lbase},le="+Inf"' if lbase else 'le="+Inf"'
            lines.append(f'{self.name}_bucket{{{inf_labels}}} {self._counts[key][-1]}')
            sum_labels = f'{{{lbase}}}' if lbase else ''
            lines.append(f'{self.name}_sum{sum_labels} {self._sums[key]:.6f}')
            lines.append(f'{self.name}_count{sum_labels} {self._totals[key]}')
        return "\n".join(lines)


# ── Metric instances ──────────────────────────────────────────────────────────

requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    labels=("job", "method", "path", "status"),
)
request_duration = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    labels=("job", "method", "path"),
)

JOB = "demo-app"


# ── Request handler ───────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        pass   # silence default access log — we track in metrics

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        start = time.monotonic()

        if path == "/metrics":
            self._metrics()
            return

        if path == "/":
            import json as _json
            body = _json.dumps({
                "service": "demo-app",
                "purpose": "Observability target for Prometheus/Grafana (Module 3)",
                "endpoints": {
                    "/metrics": "Prometheus metrics — scraped every 15s",
                    "/health":  "Health check",
                    "/fast":    "Low latency endpoint (~1-50ms)",
                    "/slow":    "High latency endpoint (~500ms-1.5s)",
                    "/flaky":   "15% error rate — triggers Grafana alerts",
                },
                "dashboards": "http://localhost:3000  (admin/admin)",
                "prometheus":  "http://localhost:9090/targets",
            }, indent=2).encode()
            self._json(200, body)
            status = "200"
        elif path == "/health":
            self._json(200, b'{"status":"ok","service":"demo-app"}')
            status = "200"
        elif path == "/fast":
            time.sleep(random.uniform(0.001, 0.05))
            self._json(200, b'{"endpoint":"fast"}')
            status = "200"
        elif path == "/slow":
            time.sleep(random.uniform(0.5, 1.5))
            self._json(200, b'{"endpoint":"slow"}')
            status = "200"
        elif path == "/flaky":
            # ~15% error rate to trigger alerts in demo
            if random.random() < 0.15:
                self._json(500, b'{"error":"random failure"}')
                status = "500"
            else:
                time.sleep(random.uniform(0.01, 0.2))
                self._json(200, b'{"endpoint":"flaky","status":"ok"}')
                status = "200"
        else:
            self._json(404, b'{"error":"not found"}')
            status = "404"

        duration = time.monotonic() - start
        requests_total.inc((JOB, "GET", path, status))
        request_duration.observe(duration, (JOB, "GET", path))

    def _json(self, code: int, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _metrics(self):
        body = "\n\n".join([
            requests_total.render(),
            request_duration.render(),
        ]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ── Background traffic generator (so dashboards show data from minute one) ────

def generate_traffic():
    """Continuously hits local endpoints to populate metrics."""
    import urllib.request
    endpoints = ["/fast", "/fast", "/fast", "/slow", "/flaky", "/flaky"]
    while True:
        try:
            path = random.choice(endpoints)
            urllib.request.urlopen(f"http://localhost:{PORT}{path}", timeout=3)
        except Exception:
            pass
        time.sleep(random.uniform(0.3, 1.2))


if __name__ == "__main__":
    t = threading.Thread(target=generate_traffic, daemon=True)
    t.start()
    logger.info("Demo app running on port %d", PORT)
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()
