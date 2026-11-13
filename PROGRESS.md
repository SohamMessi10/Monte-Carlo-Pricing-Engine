# Progress

Status labels:
**VERIFIED** (run locally, passing output recorded) ·
**IMPLEMENTED** (code written, not yet verified) ·
**BLOCKED** · **FAILED** · **TODO**

| #  | Milestone                                              | Status                       |
|----|--------------------------------------------------------|------------------------------|
| 0  | Scaffold: build system, CI, tooling                    | VERIFIED (local + CI)        |
| 1  | GBM European call/put + Black–Scholes reference        | VERIFIED (local + CI)        |
| 2  | Multithreading + deterministic chunked RNG             | VERIFIED (local); CI pending |
| 3  | Variance reduction (antithetic, control variates)      | TODO                         |
| 4  | Arithmetic Asian (geometric CV) + discrete barrier     | TODO                         |
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
