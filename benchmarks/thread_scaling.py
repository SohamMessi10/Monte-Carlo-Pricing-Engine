"""Throughput (paths per second) of the European pricer against thread count.

Usage: python benchmarks/thread_scaling.py [--paths N] [--repeats R]
"""

import argparse
import os
import statistics

from env import print_environment

import mcpricer
from mcpricer import OptionType

PARAMS = {"spot": 100.0, "strike": 100.0, "rate": 0.05, "vol": 0.2, "maturity": 1.0}


def run(n_paths, n_threads):
    return mcpricer.price_european(
        option_type=OptionType.CALL, **PARAMS, n_paths=n_paths, seed=42, n_threads=n_threads
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--paths", type=int, default=20_000_000)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    thread_counts = sorted({1, 2, 4, 8, os.cpu_count() or 1})
    print_environment()
    print(f"{'paths':>18}: {args.paths:,}")
    print(f"{'repeats':>18}: {args.repeats} (timings are the C++ elapsed_seconds)\n")

    run(args.paths, 0)  # warm-up: page in code and data, wake every core
    reference = run(args.paths, 1)

    print("| threads | median s | min s | max s | median Mpaths/s | speedup vs 1 | bit-identical |")
    print("|--------:|---------:|------:|------:|----------------:|-------------:|:-------------:|")
    base = None
    for n_threads in thread_counts:
        results = [run(args.paths, n_threads) for _ in range(args.repeats)]
        times = [r.elapsed_seconds for r in results]
        median = statistics.median(times)
        base = base or median
        same = all(
            (r.estimate, r.std_error) == (reference.estimate, reference.std_error) for r in results
        )
        mpaths = args.paths / median / 1e6
        identical = "yes" if same else "NO"
        print(
            f"| {n_threads:7d} | {median:8.4f} | {min(times):5.3f} | {max(times):5.3f} "
            f"| {mpaths:15.1f} | {base / median:12.2f} | {identical:^13} |"
        )


if __name__ == "__main__":
    main()
