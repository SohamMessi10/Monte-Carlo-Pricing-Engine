# Progress

Status labels:
**VERIFIED** (run locally, passing output recorded) ·
**IMPLEMENTED** (code written, not yet verified) ·
**BLOCKED** · **FAILED** · **TODO**

| #  | Milestone                                              | Status                       |
|----|--------------------------------------------------------|------------------------------|
| 0  | Scaffold: build system, CI, tooling                    | VERIFIED (local + CI)        |
| 1  | GBM European call/put + Black–Scholes reference        | VERIFIED (local + CI)        |
| 2  | Multithreading + deterministic chunked RNG             | VERIFIED (local + CI)        |
| 3  | Variance reduction (antithetic, control variates)      | VERIFIED (local + CI)        |
| 4  | Arithmetic Asian (geometric CV) + discrete barrier     | VERIFIED (local + CI)        |
| 5  | Sobol QMC + Brownian bridge + random digital shift     | VERIFIED (local + CI)        |
| 6  | Heston (full-truncation Euler) + semi-analytic ref     | VERIFIED (local + CI)        |
| 7  | Benchmarks + figures                                   | VERIFIED (local)             |
| 8  | README, resume bullets, talking points                 | TODO                         |
| 9  | Final audit                                            | TODO                         |

## Log

### Milestone 0 — scaffold

- Build: scikit-build-core + CMake + pybind11, editable install with
  `pip install --no-build-isolation -e .`.
- `mcpricer._core.build_info()` reports compiler, build type, flags and `__cplusplus`.
- CI: ruff; build + test on ubuntu-latest and macos-latest (Python 3.11, 3.13);
  separate Linux ASan + UBSan job.
- Local verification (Apple Silicon MacBook Air):
  - AppleClang 17.0.0.17000013, Release, `-O3 -DNDEBUG`, `__cplusplus` = 202002
  - Python 3.13.18, CMake 4.4.4, scikit-build-core 1.1.2, pybind11 3.1.0,
    pytest 9.2.0, ruff 0.17.5
  - pytest: 3 passed; ruff check: all checks passed; ruff format --check: no changes
- CI verification: 6/6 jobs green on commit 848fe2a.

### Milestone 1 — European options under GBM

- Exact simulation: S_T = S_0 exp((r − σ²/2)T + σ√T Z).
- RNG: paths split into chunks of 16384; each chunk gets its own xoshiro256** seeded from
  SplitMix64(seed, chunk index). Chunks are merged in index order (Welford + Chan merge).
- Normals: our own inverse CDF (Wichura AS241), so libc++ and libstdc++ give identical bits.
- Python reference: closed-form Black–Scholes in `mcpricer.reference`.
- Tests: MC within 4 standard errors of Black–Scholes (4 parameter sets × call/put × 3 fixed
  seeds), put–call parity, bit-identical reruns, AS241 vs `scipy.special.ndtri`,
  invalid-input errors.
- Local verification (commits 43a779d, 213b0e2): pytest 68 passed; ruff check and
  ruff format --check clean.
- Sanity run, ATM call (S=K=100, r=0.05, σ=0.2, T=1), 1,000,000 paths, seed 42:
  estimate 10.436973, std error 0.014697; Black–Scholes 10.450584 (difference 0.93 SE).
- CI: the sanitizer job failed on 213b0e2. Two fixes:
  - Build: GCC's `-Warray-bounds` gave a false positive under ASan inside pybind11 headers;
    now `-Wno-error=array-bounds` for GCC sanitizer builds only (5280690).
  - Tests: ASan aborted on the first C++ `throw` (`real___cxa_throw` null) because Python
    doesn't link libstdc++; the job now preloads libstdc++ after libasan (da1e3e9).
    Sanitizer job runs pytest with `-v -s` so reports reach the log (61a84f9).
- CI verification: 6/6 jobs green on commit da1e3e9.

### Milestone 2 — multithreading

- `run_chunks` (cpp/include/mcpricer/parallel.hpp): std::thread pool; threads take chunk
  indices from an atomic counter, store each chunk's stats in its own slot, and the slots are
  merged in chunk order after join(). `n_threads=0` means one per hardware thread.
- GIL released during pricing (`py::call_guard<py::gil_scoped_release>`).
- Tests: bit-identical estimate and std error for 1, 2, 3, 4, 8 and auto threads; more threads
  than chunks; concurrent calls from Python threads; invalid thread counts.
- Local verification: pytest 76 passed; ruff check clean.
- Thread scaling, `python benchmarks/thread_scaling.py` (20,000,000 paths, ATM call,
  5 repeats, median of C++ elapsed time). Apple M3 (4 performance + 4 efficiency cores),
  macOS 15.5, AppleClang 17.0.0.17000013, Release `-O3 -DNDEBUG`, Python 3.13.18:

  | threads | median s | Mpaths/s | speedup |
  |--------:|---------:|---------:|--------:|
  |       1 |   0.3935 |     50.8 |    1.00 |
  |       2 |   0.1997 |    100.1 |    1.97 |
  |       4 |   0.1063 |    188.1 |    3.70 |
  |       8 |   0.0700 |    285.9 |    5.63 |

  All runs bit-identical to the 1-thread result. 1→4 threads is near-linear (3.70×); 8 threads
  give 5.63×, not 8×. Likely explanation (not separately measured): threads 5–8 run on the
  slower efficiency cores.
- CI verification: 6/6 jobs green on commit e299036.

### Milestone 3 — variance reduction

- Antithetic variates: each Z also gives a path from −Z; one sample is the pair average, and the
  standard error comes from the i.i.d. pair averages. `n_paths` counts terminal prices in every
  method, so comparisons are at equal path counts.
- Control variate: X = S_T with known mean S_0 e^{rT}; estimator Ȳ − b(X̄ − S_0 e^{rT}) with
  b = Cov(X, Y) / Var(X) estimated from the same paths; residual variance Var(Y)(1 − ρ²).
- `CovStats`: mergeable Welford accumulator for (x, y); y updates match `RunningStats`, so plain
  MC is bit-unchanged (1M paths, seed 42: estimate 10.436972760651598, std error
  0.014696893199983886, same as milestone 1).
- Tests: every method within 4 SE of Black–Scholes (4 cases × call/put × 3 seeds × 3 methods);
  lower SE than plain at equal paths; control variate exact for a linear payoff (K = 1e-6);
  bit-identical across threads; input validation.
- Local verification: pytest 163 passed; ruff check and ruff format --check clean.
- `python benchmarks/variance_reduction.py` (1,000,000 paths, seed 42, all 8 threads, median of
  5 timed runs after a warm-up; same machine and build as milestone 2).
  VRF = (plain SE / method SE)²; efficiency gain = VRF × plain time / method time.

  | option            | antithetic VRF | control VRF | both VRF | both efficiency gain |
  |-------------------|---------------:|------------:|---------:|---------------------:|
  | call K=80 (ITM)   |           8.73 |       64.00 |   513.51 |               814.96 |
  | call K=100 (ATM)  |           2.00 |        6.87 |    28.79 |                45.43 |
  | call K=130 (OTM)  |           1.08 |        1.68 |    13.30 |                21.06 |
  | put K=100 (ATM)   |           1.71 |        2.38 |     9.98 |                15.84 |

  Observations from these numbers:
  - Control-variate VRF falls as the option moves out of the money (64.00 → 6.87 → 1.68):
    the payoff is less linear in S_T, so ρ² is smaller.
  - The ATM call and ATM put have the same control-variate std error (0.00561) and the same
    combined std error (0.00274). Call − put = S_T − K is linear in the control, so the
    regression removes exactly that difference and leaves identical residuals (put–call parity).
  - Antithetic runs take ~2.2 ms vs ~3.6 ms for plain, so its efficiency gain exceeds its VRF.
    Likely cause (not profiled): it makes half as many RNG + inverse-CDF calls per path. At 1M paths each run is only a few ms,
    so thread start-up is a noticeable share of these timings.
- CI verification: 6/6 jobs green on commit 3e7cdba.

### Milestone 4 — path-dependent options

- Grid t_i = i T / m, i = 1..m, exact GBM steps in log space (no discretization error).
- Arithmetic Asian with the geometric Asian as control variate. Kemna–Vorst closed form for the
  discrete geometric average in C++ (control mean) and in Python (`mcpricer.geometric_asian`).
- Up-and-out call/put, knocked out if S(t_i) >= H at any monitoring date. Knocked-out paths
  still draw all m normals, so a seed gives the same paths for every barrier level.
- Control-variate algebra moved to `CovStats::control_variate()`; the European control-variate
  result is unchanged (1M paths, seed 42: estimate 10.444572534453995, std error
  0.005605819566981251, matching the milestone 3 table).
- Tests: geometric closed form = Black–Scholes at m = 1; C++ and Python closed forms agree to
  1e-12; geometric MC within 4 SE of the closed form; arithmetic at m = 1 within 4 SE of
  Black–Scholes; arithmetic call >= geometric call on the same paths; control variate agrees
  with plain MC and lowers the SE; barrier price monotone in H and within 4 SE of
  Black–Scholes at H = 1e12; single-date barrier within 4 SE of its closed form
  C(K) − C(H) − (H − K) e^{−rT} N(d2(H)); bit-identical across threads; input validation.
- Local verification: pytest 265 passed; ruff check and ruff format --check clean.
- CI verification: 6/6 jobs green on run 43375390806 (commit "Record milestone 3 CI and
  milestone 4 local verification").

### Milestone 5 — randomized quasi-Monte Carlo

- Sobol sequence, Gray-code order, 32-bit, first 1024 dimensions of Joe–Kuo
  new-joe-kuo-6.21201. `scripts/gen_sobol_header.py` turns the downloaded file into
  `cpp/include/mcpricer/sobol_directions.hpp` (checks the format; embeds
  `third_party/joe-kuo/LICENSE`). The raw download is git-ignored.
- Brownian bridge: W(T) first, then midpoints breadth first, so the leading Sobol
  coordinates set the large-scale path shape. `brownian_bridge=False` builds W step by step.
- Random digital shift per replication (XOR with a random 32-bit integer seeded from
  (seed, replication)); estimate = mean of replications, std error = their sd / √R.
- Tests: first 10 points equal Joe–Kuo's published sobol.cc output; first 512 points of all
  1024 dimensions stratified into 512 cells; European within 4 SE of Black–Scholes; geometric
  Asian within 4 SE of Kemna–Vorst at 1/7/16/64 steps with and without bridge; arithmetic
  Asian agrees with MC; QMC SE < half the MC SE at equal paths; bit-identical across threads;
  input validation.
- Local verification: pytest 301 passed; ruff check and ruff format --check clean.
- `python benchmarks/qmc_convergence.py` (same machine and build as milestone 2; ATM call,
  S = K = 100, r = 0.05, σ = 0.2, T = 1; 20 seeds per point; N = 2^9 … 2^18 paths per
  estimate, QMC = 2 shifts × N/2 points). Figure: `benchmarks/figures/qmc_convergence.png`.

  | product                       | method         | fitted slope | RMSE at N = 262,144 |
  |-------------------------------|----------------|-------------:|--------------------:|
  | European call (1 dim)         | MC             |       −0.429 |           3.581e-02 |
  | European call (1 dim)         | QMC            |       −0.900 |           3.353e-04 |
  | Geometric Asian call (64 dim) | MC             |       −0.491 |           1.335e-02 |
  | Geometric Asian call (64 dim) | QMC + bridge   |       −0.803 |           2.757e-04 |
  | Geometric Asian call (64 dim) | QMC, no bridge |       −0.618 |           1.766e-03 |

  - At N = 262,144, QMC's RMSE is 107× lower than MC for the European call and 48× lower for
    the 64-step Asian; the bridge makes QMC 6.4× more accurate than step-by-step construction.
  - MC's European slope (−0.429) is shallower than the theoretical −0.5; the 64-dimension MC
    fit gives −0.491. Each RMSE comes from only 20 errors (about ±16% sampling noise), and the
    points are correlated: for a given seed, the MC paths at N are a prefix of the paths at 2N.
    Not yet checked: rerunning with more trials (`--trials 100`) to tighten the fits.
- CI verification: 6/6 jobs green on run 43377102633 (commit 8f67810).

### Milestone 6 — Heston

- Full-truncation Euler (Lord, Koekkoek & van Dijk 2010): v may go negative, only
  v+ = max(v, 0) enters drift and diffusion; log-Euler for S, so the simulated S is an exact
  martingale given v+. Two correlated normals per step: Z_S = ρ Z_v + √(1 − ρ²) Z_2.
- Semi-analytic reference `mcpricer.heston`: "little Heston trap" characteristic function
  (Albrecher et al. 2007), Gil-Pelaez P1/P2 with `scipy.integrate.quad` on [0, ∞); put by
  parity. Uses `cmath`, so the package keeps no runtime dependencies (scipy is imported
  only by `heston()`).
- First test run FAILED: Feller-violated call at 200 steps was 5.1 SE above the reference
  (+0.0565, SE 0.0111). The benchmark below showed the bias keeps shrinking with the step
  count, so the reference is right and 200 steps is too coarse for that model. The test now
  uses 1024 steps there, and a new test checks the bias shrinks over 16 → 64 → 256 steps.
- Tests: reference → Black–Scholes(√θ) as ξ → 0 with v0 = θ; reference put–call parity and
  bounds; MC within 4 SE of the reference on fine grids (3 models × call/put); bias shrinks
  with steps; one Euler step = Black–Scholes(√v0); bit-identical across threads; validation.
- `python benchmarks/heston_convergence.py --max-log2 10` (1,000,000 paths, seed 42, ATM call
  S = K = 100, r = 0.03, T = 1; same machine and build as milestone 2).
  Figure: `benchmarks/figures/heston_bias.png`. Selected rows (the run printed every power of
  2 from 1 to 1024):

  | steps | bias, Feller holds | bias / SE | bias, Feller violated | bias / SE |
  |------:|-------------------:|----------:|----------------------:|----------:|
  |     1 |           +0.18154 |     +12.8 |              +2.69766 |    +190.7 |
  |     4 |           +0.08780 |      +7.4 |              +3.05276 |    +295.3 |
  |    16 |           +0.01431 |      +1.2 |              +1.07252 |    +169.7 |
  |    64 |           −0.00466 |      −0.4 |              +0.22366 |     +43.4 |
  |   256 |           +0.00270 |      +0.2 |              +0.04426 |      +9.0 |
  |   512 |           −0.00023 |      −0.0 |              +0.01889 |      +3.8 |
  |  1024 |           +0.02207 |      +1.9 |              +0.00909 |      +1.8 |

  References: 9.242521 (Feller holds: κ = 2, θ = 0.04, ξ = 0.3, ρ = −0.7, v0 = 0.04) and
  6.730395 (Feller violated: κ = 0.5, θ = 0.04, ξ = 1, ρ = −0.9, v0 = 0.04).
  - Feller holds: bias inside ±2 SE from 16 steps on. The +1.9 SE at 1024 steps is consistent
    with noise (each step count draws different numbers).
  - Feller violated: bias is positive and falls by a factor 2.1–2.4 per doubling from 64 steps
    on, i.e. roughly first order in Δt there; it is still 3.8 SE at 512 steps. Euler with
    full truncation needs fine grids when the variance spends time near zero.
- Local verification: pytest 340 passed; ruff check and ruff format --check clean.
- CI verification: 6/6 jobs green on run 43378025682 (commit 7701299).

### Milestone 7 — benchmarks and figures

- `python benchmarks/run_all.py` runs every benchmark and saves each full output, starting with
  the environment block, to `benchmarks/results/<name>.txt`. Figures: `benchmarks/figures/`
  (thread_scaling, qmc_convergence, heston_bias).
- Numbers below match the saved files: run on code commit 635a169 (`+dirty` = only
  PROGRESS.md uncommitted). Afterwards a lint-only fix (ruff B023, loop-variable binding in a
  lambda) changed `numpy_comparison.py` without changing what it measures. Apple M3 (4
  performance + 4 efficiency cores), macOS 15.5, AppleClang 17.0.0.17000013, Release
  `-O3 -DNDEBUG`, Python 3.13.18, NumPy 2.5.4. Timings are medians of 5 repeats.
- Variance reduction, QMC and Heston outputs are identical to the milestone 3, 5 and 6 runs
  (same seeds, same code). Thread scaling, 20M paths: 50.5 Mpaths/s on 1 thread, 3.83× on 4,
  5.57× on 8, bit-identical at every count (milestone 2 measured 3.70× and 5.63×; an
  intermediate run gave 3.85× and 5.77×: run-to-run variation of a few percent).
- C++ vs vectorized NumPy (wall-clock from Python, same estimator and path count, different
  random generators; all estimates agree within 4 combined SE):

  | product                          | NumPy     | C++, 1 thread       | C++, 8 threads       |
  |----------------------------------|-----------|---------------------|----------------------|
  | European call, 10M paths         | 0.117 s   | 0.198 s (0.59×)     | 0.034 s (3.42×)      |
  | Arithmetic Asian, 64 steps, 1M   | 0.650 s   | 0.643 s (1.01×)     | 0.128 s (5.09×)      |

  - Single-threaded, NumPy is faster than our C++ on the European call (85.7 vs 50.6
    Mpaths/s) and level on the Asian. The C++ speedup comes from multithreading.
  - Likely causes, not yet profiled: NumPy draws normals with the ziggurat method, while we
    use the inverse CDF (AS241: a log, a sqrt and rational polynomials per normal) to stay
    bit-identical across platforms; NumPy's array `exp` may also be SIMD-vectorized. Profiling
    the single-thread loop is listed as future work, not claimed as a fix.
