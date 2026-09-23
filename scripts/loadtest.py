"""Load harness for the local staging deployment (blueprint §7).

Drives N users against the load balancer:
  * ramp phase — users arrive 0 -> N over ``--ramp`` seconds
  * sustain phase — all N users keep sending /chat turns for ``--sustain`` s

Each request's status and latency are recorded; the replica processes' RSS is
sampled periodically for the "memory stable" threshold. A JSON report is
written to ``--out``.

    python scripts/loadtest.py --base-url http://127.0.0.1:8080 \
        --users 50 --ramp 300 --sustain 600 \
        --replica-pids 1234,5678 --out C:\\evoa-infra\\report-provider.json
"""

import argparse
import asyncio
import json
import statistics
import time

import httpx

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


def percentile(values, pct):
    if not values:
        return None
    s = sorted(values)
    idx = min(len(s) - 1, int(round(pct / 100 * (len(s) - 1))))
    return s[idx]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--users", type=int, default=50)
    parser.add_argument("--ramp", type=float, default=300.0, help="seconds for 0 -> users")
    parser.add_argument("--sustain", type=float, default=600.0, help="seconds at full load")
    parser.add_argument("--think", type=float, default=0.2, help="seconds between a user's requests")
    parser.add_argument("--replica-pids", default="", help="comma-separated PIDs for memory sampling")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    latencies: list[float] = []
    statuses: dict[int, int] = {}
    lock = asyncio.Lock()

    async def record(client, token, username, until):
        while time.monotonic() < until:
            start = time.perf_counter()
            try:
                resp = await client.post(
                    "/chat",
                    json={"message": f"ping {username} {time.time_ns()}", "response_mode": "text"},
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=30.0,
                )
                status = resp.status_code
            except Exception:
                status = 599  # harness-side failure (timeout/connection)
            elapsed_ms = (time.perf_counter() - start) * 1000
            async with lock:
                latencies.append(elapsed_ms)
                statuses[status] = statuses.get(status, 0) + 1
            await asyncio.sleep(args.think)

    pids = [int(p) for p in args.replica_pids.split(",") if p.strip()] if psutil else []
    mem_samples: list[dict] = []

    async def sample_memory(stop):
        while not stop.is_set():
            if pids:
                total = 0
                for pid in pids:
                    try:
                        total += psutil.Process(pid).memory_info().rss
                    except Exception:
                        pass
                mem_samples.append({"t": round(time.time()), "mb_total": round(total / 1e6, 1)})
            await asyncio.sleep(30)

    async def run():
        # Setup: register + login for all users (sequential, off the load window).
        tokens = {}
        async with httpx.AsyncClient(base_url=args.base_url, timeout=30) as client:
            for i in range(args.users):
                name = f"load-{args.users}-{i}"
                r = await client.post("/auth/register", json={"username": name, "password": "loadpass123"})
                if r.status_code != 200:
                    r = await client.post("/auth/login", json={"username": name, "password": "loadpass123"})
                tokens[name] = r.json()["token"]

        stop = asyncio.Event()
        mem_task = asyncio.create_task(sample_memory(stop))

        async def _delayed_record(c, tok, name, offset, until):
            start_at = t_ramp_start + offset
            now = time.monotonic()
            if start_at > now:
                await asyncio.sleep(start_at - now)
            await record(c, tok, name, until)

        async with httpx.AsyncClient(base_url=args.base_url, timeout=30) as client:
            t_ramp_start = time.monotonic()
            # Ramp: each user begins at an evenly spaced offset.
            tasks = []
            for i, (name, token) in enumerate(tokens.items()):
                offset = (i / max(1, args.users)) * args.ramp
                tasks.append(
                    asyncio.create_task(
                        _delayed_record(client, token, name, offset, t_ramp_start + args.ramp + args.sustain)
                    )
                )

            await asyncio.gather(*tasks)

        stop.set()
        await mem_task

        ok = sum(v for k, v in statuses.items() if 200 <= k < 300)
        total = len(latencies)
        total_seconds = args.ramp + args.sustain
        report = {
            "label": args.out,
            "users": args.users,
            "ramp_s": args.ramp,
            "sustain_s": args.sustain,
            "total_requests": total,
            "ok_2xx": ok,
            "errors": {str(k): v for k, v in sorted(statuses.items()) if k >= 300},
            "error_rate_pct": round((total - ok) / total * 100, 4) if total else None,
            "rps": round(total / total_seconds, 2),
            "latency_ms": {
                "p50": round(percentile(latencies, 50), 1) if latencies else None,
                "p95": round(percentile(latencies, 95), 1) if latencies else None,
                "p99": round(percentile(latencies, 99), 1) if latencies else None,
                "max": round(max(latencies), 1) if latencies else None,
            },
            "memory_mb": {
                "first": mem_samples[0]["mb_total"] if mem_samples else None,
                "last": mem_samples[-1]["mb_total"] if mem_samples else None,
                "samples": mem_samples,
            },
        }
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(json.dumps({k: v for k, v in report.items() if k != "memory_mb"}, indent=2))
        print("memory first/last MB:", report["memory_mb"]["first"], report["memory_mb"]["last"])

    await run()


if __name__ == "__main__":
    asyncio.run(main())
