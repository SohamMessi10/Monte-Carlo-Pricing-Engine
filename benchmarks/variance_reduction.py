"""Variance-reduction factors of antithetic variates and the S_T control variate.

At equal path counts, VRF = (plain std error / method std error)^2. Efficiency gain also
charges for run time: VRF * (plain time / method time).

Usage: python benchmarks/variance_reduction.py [--paths N] [--repeats R]
"""

import argparse
import statistics

from env import print_environment

import mcpricer
from mcpricer import OptionType

BASE = {"rate": 0.05, "vol": 0.2, "maturity": 1.0, "spot": 100.0}
CASES = {
    "call K=80 (ITM)": (OptionType.CALL, {**BASE, "strike": 80.0}),
    "call K=100 (ATM)": (OptionType.CALL, {**BASE, "strike": 100.0}),
    "call K=130 (OTM)": (OptionType.CALL, {**BASE, "strike": 130.0}),
    "put K=100 (ATM)": (OptionType.PUT, {**BASE, "strike": 100.0}),
}
METHODS = {
    "plain": {},
    "antithetic": {"antithetic": True},
    "control": {"control_variate": True},
    "both": {"antithetic": True, "control_variate": True},
}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--paths", type=int, default=1_000_000)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    print_environment()
    print(f"{'paths':>18}: {args.paths:,} per run, seed 42, all hardware threads")
    print(f"{'repeats':>18}: {args.repeats} (time = median C++ elapsed_seconds)\n")

    print("| option | method | estimate | std error | VRF | median ms | efficiency gain |")
    print("|---|---|---:|---:|---:|---:|---:|")
    for case, (option_type, params) in CASES.items():
        exact = mcpricer.black_scholes(option_type=option_type, **params)
        plain_se = plain_time = None
        for method, flags in METHODS.items():
            runs = [
                mcpricer.price_european(
                    option_type=option_type, **params, n_paths=args.paths, seed=42, **flags
                )
                for _ in range(args.repeats + 1)
            ][1:]  # drop the first run: warm-up
            r = runs[0]
            t = statistics.median(x.elapsed_seconds for x in runs)
            if plain_se is None:
                plain_se, plain_time = r.std_error, t
            vrf = (plain_se / r.std_error) ** 2
            print(
                f"| {case} | {method} | {r.estimate:.5f} | {r.std_error:.5f} | {vrf:.2f} "
                f"| {t * 1e3:.1f} | {vrf * plain_time / t:.2f} |"
            )
        print(f"| {case} | Black–Scholes | {exact:.5f} | | | | |")


if __name__ == "__main__":
    main()
