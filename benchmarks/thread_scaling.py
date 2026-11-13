"""Throughput (paths per second) of the European pricer against thread count.

Writes benchmarks/figures/thread_scaling.png.

Usage: python benchmarks/thread_scaling.py [--paths N] [--repeats R]
"""

import argparse
import os
import statistics
from pathlib import Path

import matplotlib.pyplot as plt
from env import print_environment

import mcpricer
from mcpricer import OptionType

PARAMS = {"spot": 100.0, "strike": 100.0, "rate": 0.05, "vol": 0.2, "maturity": 1.0}
FIGURE = Path(__file__).resolve().parent / "figures" / "thread_scaling.png"
SURFACE, INK, INK_2, SERIES_1 = "#fcfcfb", "#0b0b0b", "#52514e", "#2a78d6"


def run(n_paths, n_threads):
    return mcpricer.price_european(
        option_type=OptionType.CALL, **PARAMS, n_paths=n_paths, seed=42, n_threads=n_threads
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--paths", type=int, default=20_000_000)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    thread_counts = list(range(1, (os.cpu_count() or 1) + 1))
    print_environment()
    print(f"{'paths':>18}: {args.paths:,}")
    print(f"{'repeats':>18}: {args.repeats} (timings are the C++ elapsed_seconds)\n")

    run(args.paths, 0)  # warm-up: page in code and data, wake every core
    reference = run(args.paths, 1)

    print("| threads | median s | min s | max s | median Mpaths/s | speedup vs 1 | bit-identical |")
    print("|--------:|---------:|------:|------:|----------------:|-------------:|:-------------:|")
    base = None
    speedups = []
    for n_threads in thread_counts:
        results = [run(args.paths, n_threads) for _ in range(args.repeats)]
        times = [r.elapsed_seconds for r in results]
        median = statistics.median(times)
        base = base or median
        speedups.append(base / median)
        same = all(
            (r.estimate, r.std_error) == (reference.estimate, reference.std_error) for r in results
        )
        mpaths = args.paths / median / 1e6
        identical = "yes" if same else "NO"
        print(
            f"| {n_threads:7d} | {median:8.4f} | {min(times):5.3f} | {max(times):5.3f} "
            f"| {mpaths:15.1f} | {base / median:12.2f} | {identical:^13} |"
        )

    fig, ax = plt.subplots(figsize=(6.5, 4.5), facecolor=SURFACE)
    ax.plot(thread_counts, thread_counts, color=INK_2, linewidth=1, linestyle="--")
    ax.annotate(
        "ideal",
        (thread_counts[-1], thread_counts[-1]),
        xytext=(-30, 0),
        textcoords="offset points",
        color=INK_2,
        fontsize=9,
        va="center",
    )
    ax.plot(thread_counts, speedups, color=SERIES_1, marker="o", markersize=6, linewidth=2)
    for n, s in zip(thread_counts, speedups, strict=True):
        if n in (1, 4, thread_counts[-1]):
            ax.annotate(
                f"{s:.2f}×",
                (n, s),
                xytext=(0, -14),
                textcoords="offset points",
                ha="center",
                color=INK,
                fontsize=9,
            )
    ax.set_xlabel("threads", color=INK_2)
    ax.set_ylabel("speedup vs 1 thread (median of repeats)", color=INK_2)
    ax.set_title(
        f"European pricer thread scaling ({args.paths:,} paths)", color=INK, fontsize=11, loc="left"
    )
    ax.set_xticks(thread_counts)
    ax.set_facecolor(SURFACE)
    ax.grid(True, color="#e4e3df", linewidth=0.8)
    ax.tick_params(colors=INK_2)
    for spine in ax.spines.values():
        spine.set_color("#c9c8c2")
    ax.margins(x=0.05, y=0.1)
    fig.tight_layout()
    FIGURE.parent.mkdir(exist_ok=True)
    fig.savefig(FIGURE, dpi=150, facecolor=SURFACE)
    print(f"\nwrote {FIGURE}")


if __name__ == "__main__":
    main()
