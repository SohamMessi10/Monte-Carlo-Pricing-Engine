"""Discretization bias of full-truncation Euler for Heston, against the semi-analytic price.

bias = MC estimate - reference. Its standard error is the MC std error (the reference is
accurate to far better than that), so the plot shows bias with +-2 SE bars.
Writes benchmarks/figures/heston_bias.png.

Usage: python benchmarks/heston_convergence.py [--paths N] [--max-log2 K]
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from env import print_environment

import mcpricer
from mcpricer import OptionType

CONTRACT = {"spot": 100.0, "strike": 100.0, "rate": 0.03, "maturity": 1.0}
MODELS = {
    "Feller holds (κ=2, θ=0.04, ξ=0.3, ρ=−0.7)": {
        "v0": 0.04,
        "kappa": 2.0,
        "theta": 0.04,
        "xi": 0.3,
        "rho": -0.7,
    },
    "Feller violated (κ=0.5, θ=0.04, ξ=1, ρ=−0.9)": {
        "v0": 0.04,
        "kappa": 0.5,
        "theta": 0.04,
        "xi": 1.0,
        "rho": -0.9,
    },
}
FIGURE = Path(__file__).resolve().parent / "figures" / "heston_bias.png"
COLORS = ["#2a78d6", "#eb6834"]  # reference palette, categorical slots 1-2
MARKERS = ["o", "s"]
SURFACE, INK, INK_2 = "#fcfcfb", "#0b0b0b", "#52514e"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--paths", type=int, default=1_000_000)
    parser.add_argument("--max-log2", type=int, default=8)
    args = parser.parse_args()
    steps = [2**k for k in range(args.max_log2 + 1)]

    print_environment()
    print(f"{'paths':>18}: {args.paths:,} per run, seed 42, ATM call, T = 1\n")

    fig, ax = plt.subplots(figsize=(8, 4.5), facecolor=SURFACE)
    ax.axhline(0.0, color=INK_2, linewidth=1)
    for i, (label, model) in enumerate(MODELS.items()):
        exact = mcpricer.heston(option_type=OptionType.CALL, **CONTRACT, **model)
        print(f"{label}: reference price {exact:.6f}")
        print("| steps | estimate | std error | bias | bias / SE | seconds |")
        print("|---:|---:|---:|---:|---:|---:|")
        biases, errors = [], []
        for n in steps:
            r = mcpricer.price_heston(
                option_type=OptionType.CALL,
                **CONTRACT,
                **model,
                n_steps=n,
                n_paths=args.paths,
                seed=42,
            )
            bias = r.estimate - exact
            biases.append(bias)
            errors.append(2.0 * r.std_error)
            print(
                f"| {n} | {r.estimate:.5f} | {r.std_error:.5f} | {bias:+.5f} "
                f"| {bias / r.std_error:+.1f} | {r.elapsed_seconds:.3f} |"
            )
        print()
        ax.errorbar(
            steps,
            biases,
            yerr=errors,
            color=COLORS[i],
            marker=MARKERS[i],
            markersize=6,
            linewidth=2,
            capsize=3,
            label=label,
        )

    ax.set_xscale("log", base=2)
    # Linear within ±0.02 (where the fine-grid bias and the ±2 SE bars live), log beyond it,
    # so the coarse-grid bias of several units doesn't flatten everything else.
    ax.set_yscale("symlog", linthresh=0.02)
    ax.margins(y=0.08)  # keep the largest coarse-grid point off the frame
    ax.set_xlabel("Euler time steps per year", color=INK_2)
    ax.set_ylabel("bias = MC − semi-analytic price", color=INK_2)
    ax.set_title(
        f"Full-truncation Euler bias, ATM call ({args.paths:,} paths, ±2 SE)",
        color=INK,
        fontsize=11,
        loc="left",
    )
    ax.set_facecolor(SURFACE)
    ax.grid(True, color="#e4e3df", linewidth=0.8)
    ax.tick_params(colors=INK_2)
    for spine in ax.spines.values():
        spine.set_color("#c9c8c2")
    ax.legend(frameon=False, labelcolor=INK, fontsize=9)
    fig.tight_layout()
    FIGURE.parent.mkdir(exist_ok=True)
    fig.savefig(FIGURE, dpi=150, facecolor=SURFACE)
    print(f"wrote {FIGURE.relative_to(FIGURE.parents[2])}")


if __name__ == "__main__":
    main()
