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
| 4  | Arithmetic Asian (geometric CV) + discrete barrier     | VERIFIED (local); CI pending |
| 5  | Sobol QMC + Brownian bridge + random digital shift     | TODO                         |
| 6  | Heston (full-truncation Euler) + semi-analytic ref     | TODO                         |
| 7  | Benchmarks + figures                                   | TODO                         |
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
