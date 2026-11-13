"""Run every benchmark and save each one's full output to benchmarks/results/<name>.txt.

Each output starts with the environment (git commit, CPU, cores, OS, Python, compiler, build
type and flags), so every saved number carries its context. Figures go to benchmarks/figures/.

Usage: python benchmarks/run_all.py
"""

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCHMARKS = [
    ("thread_scaling", []),
    ("variance_reduction", []),
    ("numpy_comparison", []),
    ("qmc_convergence", []),
    ("heston_convergence", ["--max-log2", "10"]),
]


def main():
    results = HERE / "results"
    results.mkdir(exist_ok=True)
    for name, args in BENCHMARKS:
        command = [sys.executable, str(HERE / f"{name}.py"), *args]
        print(f"== {name} ==", flush=True)
        start = time.perf_counter()
        run = subprocess.run(command, capture_output=True, text=True, check=False)
        elapsed = time.perf_counter() - start
        if run.returncode != 0:
            print(run.stdout + run.stderr)
            raise SystemExit(f"{name} failed with exit code {run.returncode}")
        header = f"$ python benchmarks/{name}.py {' '.join(args)}".rstrip() + "\n\n"
        (results / f"{name}.txt").write_text(header + run.stdout)
        print(run.stdout)
        print(f"({elapsed:.1f} s, saved to benchmarks/results/{name}.txt)\n", flush=True)


if __name__ == "__main__":
    main()
