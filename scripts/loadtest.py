#!/usr/bin/env python3
"""
Load generator for the Clowdy fleet.

Fires N concurrent invocations at a function and reports what the platform did
with them: latency percentiles, cold-start rate, throttles, and how the work
actually distributed across workers. The distribution table is the point --
it is the difference between claiming the scheduler balances load and showing
that it does.

Usage:
    python scripts/loadtest.py <function_id> --requests 200 --concurrency 20

    # against the compose stack
    python scripts/loadtest.py abc123 --url http://localhost:8080 -n 500 -c 50

Needs only httpx, which the backend already depends on.
"""

import argparse
import asyncio
import statistics
import sys
import time
from collections import Counter

import httpx


async def _one(client: httpx.AsyncClient, url: str, payload: dict) -> dict:
    """Run a single invocation and describe what happened to it."""
    started = time.perf_counter()
    try:
        response = await client.post(url, json={"input": payload})
    except httpx.HTTPError as exc:
        return {"ok": False, "reason": type(exc).__name__, "ms": 0}

    elapsed_ms = (time.perf_counter() - started) * 1000

    if response.status_code == 503:
        return {"ok": False, "reason": "throttled", "ms": elapsed_ms}
    if response.status_code != 200:
        return {"ok": False, "reason": f"http {response.status_code}", "ms": elapsed_ms}

    body = response.json()
    return {
        "ok": bool(body.get("success")),
        "reason": None if body.get("success") else "function error",
        "ms": elapsed_ms,
        "worker": body.get("worker_id", "unknown"),
        "cold": bool(body.get("cold_start")),
    }


async def run(base_url: str, function_id: str, total: int, concurrency: int) -> int:
    invoke_url = f"{base_url}/api/invoke/{function_id}"
    gate = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(timeout=90.0) as client:
        async def bounded(i: int) -> dict:
            async with gate:
                return await _one(client, invoke_url, {"n": i})

        print(
            f"Firing {total} invocations at {invoke_url} "
            f"({concurrency} concurrent)...\n"
        )
        wall_start = time.perf_counter()
        results = await asyncio.gather(*(bounded(i) for i in range(total)))
        wall = time.perf_counter() - wall_start

        cluster = {}
        try:
            cluster = (await client.get(f"{base_url}/api/cluster")).json()
        except (httpx.HTTPError, ValueError):
            pass

    ok = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]
    latencies = sorted(r["ms"] for r in ok)

    def pct(p: float) -> float:
        if not latencies:
            return 0.0
        return latencies[min(len(latencies) - 1, int(len(latencies) * p))]

    print(f"  mode           {cluster.get('mode', 'unknown')}")
    print(f"  wall clock     {wall:.2f}s")
    print(f"  throughput     {total / wall:.1f} req/s")
    print(f"  succeeded      {len(ok)}/{total}")
    if latencies:
        print(f"  latency  p50   {pct(0.50):.0f} ms")
        print(f"           p95   {pct(0.95):.0f} ms")
        print(f"           p99   {pct(0.99):.0f} ms")
        print(f"           mean  {statistics.mean(latencies):.0f} ms")

    cold = sum(1 for r in ok if r.get("cold"))
    if ok:
        print(f"  cold starts    {cold} ({cold / len(ok) * 100:.1f}%)")

    if failed:
        print("\n  failures")
        for reason, count in Counter(r["reason"] for r in failed).most_common():
            print(f"    {reason:<24} {count}")

    placement = Counter(r["worker"] for r in ok)
    if placement:
        print("\n  placement")
        widest = max(len(w) for w in placement)
        for worker, count in placement.most_common():
            share = count / len(ok)
            bar = "#" * round(share * 40)
            print(f"    {worker:<{widest}}  {count:>5}  {share * 100:5.1f}%  {bar}")

        if len(placement) > 1:
            counts = list(placement.values())
            spread = (max(counts) - min(counts)) / statistics.mean(counts)
            print(f"\n  imbalance      {spread * 100:.1f}% (max-min spread over mean)")

    return 0 if len(ok) == total else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("function_id", help="ID of a deployed function to invoke")
    parser.add_argument(
        "--url", default="http://localhost:8000", help="control plane or LB base URL"
    )
    parser.add_argument("-n", "--requests", type=int, default=100)
    parser.add_argument("-c", "--concurrency", type=int, default=10)
    args = parser.parse_args()

    return asyncio.run(
        run(args.url.rstrip("/"), args.function_id, args.requests, args.concurrency)
    )


if __name__ == "__main__":
    sys.exit(main())
