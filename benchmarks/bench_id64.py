"""
bench_id64.py — Simple throughput benchmark for Id64.

Run:
    python benchmarks/bench_id64.py

Measures IDs/sec for both permutation modes and the impact of block_size
on persistence overhead.
"""
from __future__ import annotations

import time
import tempfile
import os
from permid64 import Id64

WARMUP = 1_000
ITERATIONS = 1_000_000


def benchmark(label: str, gen: Id64, n: int = ITERATIONS) -> float:
    # warmup
    for _ in range(WARMUP):
        gen.next_u64()

    start = time.perf_counter()
    for _ in range(n):
        gen.next_u64()
    elapsed = time.perf_counter() - start

    rate = n / elapsed
    print(f"  {label:<40s}  {rate:>14,.0f} IDs/sec  ({elapsed:.3f}s)")
    return rate


def run_benchmarks():
    print("=" * 70)
    print("id64 benchmark")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:

        # ---- Permutation comparison (block_size=4096) ----
        print("\n[Permutation comparison — block_size=4096]")

        benchmark(
            "multiplicative (default keys)",
            Id64.multiplicative(
                instance_id=1,
                state_file=os.path.join(tmpdir, "mult.state"),
                block_size=4096,
            ),
        )

        benchmark(
            "feistel (6 rounds)",
            Id64.feistel(
                instance_id=1,
                state_file=os.path.join(tmpdir, "feistel6.state"),
                block_size=4096,
                rounds=6,
            ),
        )

        benchmark(
            "feistel (12 rounds)",
            Id64.feistel(
                instance_id=1,
                state_file=os.path.join(tmpdir, "feistel12.state"),
                block_size=4096,
                rounds=12,
            ),
        )

        # ---- Block size impact (multiplicative) ----
        print("\n[Block size impact — multiplicative permutation]")

        for block_size in [16, 64, 256, 1024, 4096, 65536]:
            benchmark(
                f"block_size={block_size}",
                Id64.multiplicative(
                    instance_id=1,
                    state_file=os.path.join(tmpdir, f"bs{block_size}.state"),
                    block_size=block_size,
                ),
                n=min(ITERATIONS, 200_000),  # fewer iterations for small blocks
            )

    print("\nDone.")


if __name__ == "__main__":
    run_benchmarks()
