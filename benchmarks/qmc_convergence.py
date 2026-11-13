"""RMSE against path count for plain MC and randomized QMC, with fitted log-log slopes.

Each estimate uses N paths in total: plain MC with N paths, or QMC with 2 random digital
shifts of N/2 Sobol points each. RMSE is over independent seeds, against the exact price.
Writes benchmarks/figures/qmc_convergence.png.

Usage: python benchmarks/qmc_convergence.py [--min-log2 K] [--max-log2 K] [--trials T]
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from env import print_environment

import mcpricer
from mcpricer import Average, OptionType, Payoff

PARAMS = {"spot": 100.0, "strike": 100.0, "rate": 0.05, "vol": 0.2, "maturity": 1.0}
ASIAN_STEPS = 64
FIGURE = Path(__file__).resolve().parent / "figures" / "qmc_convergence.png"

# Reference palette, categorical slots 1-3 in fixed order, on the light chart surface.
COLORS = {"MC": "#2a78d6", "QMC + bridge": "#eb6834", "QMC, no bridge": "#1baf7a"}
MARKERS = {"MC": "o", "QMC + bridge": "s", "QMC, no bridge": "^"}
SURFACE, INK, INK_2 = "#fcfcfb", "#0b0b0b", "#52514e"


def estimator(product, method, n_total, seed):
    common = {"option_type": OptionType.CALL, **PARAMS, "seed": seed}
    if method == "MC":
        if product == "european":
            return mcpricer.price_european(**common, n_paths=n_total).estimate
        return mcpricer.price_asian(
            **common, n_steps=ASIAN_STEPS, n_paths=n_total, average=Average.GEOMETRIC
        ).estimate
    european = product == "european"
    return mcpricer.price_qmc(
        **common,
        n_steps=1 if european else ASIAN_STEPS,
        n_points=n_total // 2,
        n_replications=2,
        payoff=Payoff.EUROPEAN if european else Payoff.GEOMETRIC_ASIAN,
        brownian_bridge=method == "QMC + bridge",
    ).estimate


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--min-log2", type=int, default=9)
    parser.add_argument("--max-log2", type=int, default=18)
    parser.add_argument("--trials", type=int, default=20)
    args = parser.parse_args()

    print_environment()
    print(f"{'trials':>18}: {args.trials} seeds per point; N = total paths per estimate\n")

    products = {
        "european": (
            "European call (1 dimension)",
            mcpricer.black_scholes(option_type=OptionType.CALL, **PARAMS),
            ["MC", "QMC + bridge"],
        ),
        "asian": (
            f"Geometric Asian call ({ASIAN_STEPS} dimensions)",
            mcpricer.geometric_asian(option_type=OptionType.CALL, **PARAMS, n_steps=ASIAN_STEPS),
            ["MC", "QMC + bridge", "QMC, no bridge"],
        ),
    }
    sizes = [2**k for k in range(args.min_log2, args.max_log2 + 1)]
    seeds = range(1, args.trials + 1)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True, facecolor=SURFACE)
    for ax, (product, (title, exact, methods)) in zip(axes, products.items(), strict=True):
        print(f"{title}: exact price {exact:.6f}")
        print("| method | N | RMSE |")
        print("|---|---:|---:|")
        for method in methods:
            rmse = []
            for n in sizes:
                errors = [estimator(product, method, n, s) - exact for s in seeds]
                rmse.append(float(np.sqrt(np.mean(np.square(errors)))))
                print(f"| {method} | {n} | {rmse[-1]:.3e} |")
            slope = np.polyfit(np.log(sizes), np.log(rmse), 1)[0]
            print(f"fitted slope, {method}: {slope:.3f}\n")
            ax.loglog(
                sizes,
                rmse,
                color=COLORS[method],
                marker=MARKERS[method],
                markersize=6,
                linewidth=2,
                label=f"{method} (slope {slope:.2f})",
            )
            ax.annotate(
                f"{slope:.2f}",
                (sizes[-1], rmse[-1]),
                xytext=(6, 0),
                textcoords="offset points",
                va="center",
                color=INK_2,
                fontsize=9,
            )
        ax.set_title(title, color=INK, fontsize=11, loc="left")
        ax.set_xlabel("paths per estimate, N", color=INK_2)
        ax.set_facecolor(SURFACE)
        ax.grid(True, which="major", color="#e4e3df", linewidth=0.8)
        ax.tick_params(colors=INK_2)
        for spine in ax.spines.values():
            spine.set_color("#c9c8c2")
        ax.legend(frameon=False, labelcolor=INK, fontsize=9)
    axes[0].set_ylabel("RMSE vs exact price", color=INK_2)
    fig.suptitle(
        f"Convergence of plain MC and randomized QMC ({args.trials} seeds per point)",
        color=INK,
        fontsize=12,
    )
    fig.tight_layout()
    FIGURE.parent.mkdir(exist_ok=True)
    fig.savefig(FIGURE, dpi=150, facecolor=SURFACE)
    print(f"wrote {FIGURE}")


if __name__ == "__main__":
    main()
