"""Bounded, deterministic, no-network guest API latency/availability smoke gate.

Only synthesized guest requests run against an in-memory TestClient. This is
not a production benchmark, concurrency test or infrastructure SLA.
"""
import argparse
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from fastapi.testclient import TestClient
from nextrail_api import create_app


ROUTES = (
    ("health", "GET", "/health", None),
    ("ready", "GET", "/ready", None),
    ("skills", "GET", "/v1/skills", None),
    ("courses", "GET", "/v1/courses", None),
    ("pathway_preview", "POST", "/v1/pathways/preview",
     {"career_goal": "Frontend developer", "target_skill_ids": ["css"]}),
)


class PerformanceGateError(ValueError):
    """The offline reliability smoke test did not meet its contract."""


def percentile_95(values):
    if not values or any(not math.isfinite(v) or v < 0 for v in values):
        raise PerformanceGateError("Invalid latency sample collection")
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * 0.95) - 1]


def evaluate_guest_api(*, iterations=12, max_p95_ms=3000, app_factory=create_app):
    if type(iterations) is not int or not 1 <= iterations <= 20:
        raise PerformanceGateError("Iterations must be 1-20")
    if (type(max_p95_ms) not in (int, float) or not math.isfinite(max_p95_ms)
            or not 1 <= max_p95_ms <= 60000):
        raise PerformanceGateError("Latency budget must be 1-60000 milliseconds")

    durations = {name: [] for name, _, _, _ in ROUTES}
    with TestClient(app_factory()) as client:
        for _ in range(iterations):
            for name, method, path, body in ROUTES:
                started = time.perf_counter_ns()
                result = client.request(method, path, json=body) if body is not None else client.request(method, path)
                elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
                if result.status_code != 200:
                    raise PerformanceGateError(f"{name} returned an unexpected HTTP status")
                if result.headers.get("cache-control") != "no-store":
                    raise PerformanceGateError(f"{name} omitted the required privacy cache header")
                durations[name].append(elapsed_ms)

    measured = {
        name: {
            "requests": iterations,
            "p95_ms": round(percentile_95(samples), 2),
            "max_ms": round(max(samples), 2),
        }
        for name, samples in durations.items()
    }
    failed = [name for name, samples in durations.items()
              if percentile_95(samples) > max_p95_ms]
    if failed:
        raise PerformanceGateError(
            "Guest API latency smoke budget exceeded: " + ", ".join(failed)
        )
    return {
        "status": "pass",
        "profile": "in_memory_synthetic_guest",
        "total_requests": iterations * len(ROUTES),
        "max_p95_budget_ms": max_p95_ms,
        "routes": measured,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline guest API smoke latency gate")
    parser.add_argument("--iterations", type=int, default=12)
    parser.add_argument("--max-p95-ms", type=int, default=3000)
    args = parser.parse_args(argv)
    try:
        report = evaluate_guest_api(iterations=args.iterations, max_p95_ms=args.max_p95_ms)
    except PerformanceGateError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    print("No network, account records, credentials or production load used")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
