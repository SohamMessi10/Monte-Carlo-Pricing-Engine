"""C++ engine against a vectorized NumPy implementation of the same estimators.

NumPy uses its default generator (PCG64 + ziggurat normals), so the two use different random
numbers: the estimates should agree within their combined standard error, not bit for bit.
Times are wall-clock from Python (time.perf_counter) for both, median of the repeats.

Usage: python benchmarks/numpy_comparison.py [--repeats R]
"""

import argparse
import math
import statistics
import time

import numpy as np
from env import print_environment

import mcpricer
from mcpricer import OptionType

S0, K, R, VOL, T = 100.0, 100.0, 0.05, 0.2, 1.0
PARAMS = {"spot": S0, "strike": K, "rate": R, "vol": VOL, "maturity": T}
EUROPEAN_PATHS = 10_000_000
ASIAN_PATHS, ASIAN_STEPS = 1_000_000, 64
BATCH_ELEMENTS = 4_000_000  # normals per NumPy batch, to bound memory


def finish(total, total_sq, n):
    mean = total / n
    var = (total_sq - n * mean * mean) / (n - 1)
    discount = math.exp(-R * T)
    return discount * mean, discount * math.sqrt(var / n)


def numpy_european(n_paths, seed):
    rng = np.random.default_rng(seed)
    drift, diffusion = (R - 0.5 * VOL * VOL) * T, VOL * math.sqrt(T)
    total = total_sq = 0.0
    for start in range(0, n_paths, BATCH_ELEMENTS):
        z = rng.standard_normal(min(BATCH_ELEMENTS, n_paths - start))
        payoff = np.maximum(S0 * np.exp(drift + diffusion * z) - K, 0.0)
        total += payoff.sum()
        total_sq += np.dot(payoff, payoff)
    return finish(total, total_sq, n_paths)


def numpy_asian(n_paths, n_steps, seed):
    rng = np.random.default_rng(seed)
    dt = T / n_steps
    drift, diffusion = (R - 0.5 * VOL * VOL) * dt, VOL * math.sqrt(dt)
    batch = max(1, BATCH_ELEMENTS // n_steps)
    total = total_sq = 0.0
    for start in range(0, n_paths, batch):
        z = rng.standard_normal((min(batch, n_paths - start), n_steps))
        log_s = math.log(S0) + np.cumsum(drift + diffusion * z, axis=1)
        payoff = np.maximum(np.exp(log_s).mean(axis=1) - K, 0.0)
        total += payoff.sum()
        total_sq += np.dot(payoff, payoff)
    return finish(total, total_sq, n_paths)


def timed(fn, repeats):
    fn()  # warm-up
    times, result = [], None
    for _ in range(repeats):
        start = time.perf_counter()
        result = fn()
        times.append(time.perf_counter() - start)
    return result, statistics.median(times)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    print_environment()
    print(f"{'numpy':>18}: {np.__version__}")
    print(f"{'repeats':>18}: {args.repeats} (median wall-clock seconds after a warm-up)\n")

    cases = {
        f"European call, {EUROPEAN_PATHS:,} paths": (
            EUROPEAN_PATHS,
            lambda: numpy_european(EUROPEAN_PATHS, 42),
            lambda threads: mcpricer.price_european(
                option_type=OptionType.CALL,
                **PARAMS,
                n_paths=EUROPEAN_PATHS,
                seed=42,
                n_threads=threads,
            ),
        ),
        f"Arithmetic Asian call, {ASIAN_STEPS} steps, {ASIAN_PATHS:,} paths": (
            ASIAN_PATHS,
            lambda: numpy_asian(ASIAN_PATHS, ASIAN_STEPS, 42),
            lambda threads: mcpricer.price_asian(
                option_type=OptionType.CALL,
                **PARAMS,
                n_steps=ASIAN_STEPS,
                n_paths=ASIAN_PATHS,
                seed=42,
                n_threads=threads,
            ),
        ),
    }

    print("| product | implementation | median s | Mpaths/s | speedup vs NumPy | estimate ± SE |")
    print("|---|---|---:|---:|---:|---|")
    for label, (n_paths, numpy_fn, cpp_fn) in cases.items():
        (np_est, np_se), np_time = timed(numpy_fn, args.repeats)
        rows = [("NumPy (vectorized)", np_time, np_est, np_se)]
        for threads, name in ((1, "C++, 1 thread"), (0, "C++, all threads")):
            r, t = timed(lambda threads=threads: cpp_fn(threads), args.repeats)
            rows.append((name, t, r.estimate, r.std_error))
            gap = abs(r.estimate - np_est) / math.hypot(r.std_error, np_se)
            if gap >= 4.0:
                print(f"WARNING: {name} differs from NumPy by {gap:.1f} combined SE")
        for name, t, est, se in rows:
            print(
                f"| {label} | {name} | {t:.3f} | {n_paths / t / 1e6:.1f} "
                f"| {np_time / t:.2f} | {est:.4f} ± {se:.4f} |"
            )


if __name__ == "__main__":
    main()
