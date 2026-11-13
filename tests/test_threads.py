"""Milestone 2: multithreading must not change a single bit of the result."""

from concurrent.futures import ThreadPoolExecutor

import pytest

import mcpricer
from mcpricer import OptionType

BASE = {"spot": 100.0, "strike": 100.0, "rate": 0.05, "vol": 0.2, "maturity": 1.0}
# 250_001 paths = 15 full chunks of 16384 plus a partial one: uneven work per thread.
N_PATHS = 250_001


def price(n_threads, *, seed=11, n_paths=N_PATHS, option_type=OptionType.CALL):
    return mcpricer.price_european(
        option_type=option_type, **BASE, n_paths=n_paths, seed=seed, n_threads=n_threads
    )


@pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
@pytest.mark.parametrize("seed", [11, 12])
def test_bit_identical_for_any_thread_count(seed, option_type):
    ref = price(1, seed=seed, option_type=option_type)
    for n_threads in [2, 3, 4, 8, 0]:
        r = price(n_threads, seed=seed, option_type=option_type)
        assert (r.estimate, r.std_error, r.n_paths) == (ref.estimate, ref.std_error, ref.n_paths)


def test_more_threads_than_chunks():
    ref = price(1, n_paths=100)
    r = price(16, n_paths=100)
    assert (r.estimate, r.std_error) == (ref.estimate, ref.std_error)


def test_concurrent_calls_from_python_threads():
    # The GIL is released during pricing, so these calls really overlap in C++.
    seeds = [21, 22, 23, 24]
    expected = [price(1, seed=s) for s in seeds]
    with ThreadPoolExecutor(max_workers=len(seeds)) as pool:
        got = list(pool.map(lambda s: price(2, seed=s), seeds))
    assert [(r.estimate, r.std_error) for r in got] == [(r.estimate, r.std_error) for r in expected]


@pytest.mark.parametrize("n_threads", [-1, 1025])
def test_rejects_bad_thread_count(n_threads):
    with pytest.raises(ValueError, match="n_threads"):
        price(n_threads, n_paths=100)
