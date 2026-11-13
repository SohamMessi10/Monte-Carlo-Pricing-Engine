"""Milestone 5: Sobol points, Brownian bridge, randomized QMC with error bars."""

import math

import numpy as np
import pytest

import mcpricer
from mcpricer import OptionType, Payoff

CALL, PUT = OptionType.CALL, OptionType.PUT
BASE = {"spot": 100.0, "strike": 100.0, "rate": 0.05, "vol": 0.2, "maturity": 1.0}

# First 10 points in 3 dimensions printed by Joe & Kuo's reference program sobol.cc
# (https://web.maths.unsw.edu.au/~fkuo/sobol/) for new-joe-kuo-6.21201.
JOE_KUO_FIRST_10 = [
    [0.0, 0.0, 0.0],
    [0.5, 0.5, 0.5],
    [0.75, 0.25, 0.25],
    [0.25, 0.75, 0.75],
    [0.375, 0.375, 0.625],
    [0.875, 0.875, 0.125],
    [0.625, 0.125, 0.875],
    [0.125, 0.625, 0.375],
    [0.1875, 0.3125, 0.9375],
    [0.6875, 0.8125, 0.4375],
]


def qmc(option_type=CALL, params=BASE, *, n_steps=1, n_points=2**14, reps=16, seed=1, **kw):
    return mcpricer.price_qmc(
        option_type=option_type,
        **params,
        n_steps=n_steps,
        n_points=n_points,
        n_replications=reps,
        seed=seed,
        **kw,
    )


# --- the Sobol sequence itself ---------------------------------------------------------------


def test_matches_joe_kuo_reference_points():
    assert mcpricer._core._sobol_points(10, 3) == JOE_KUO_FIRST_10


def test_every_dimension_is_stratified():
    # The first 2^k points of any Sobol dimension hit each interval [i/2^k, (i+1)/2^k) exactly
    # once. Checking all 1024 dimensions exercises every table row and the recurrence.
    k = 9
    points = np.array(mcpricer._core._sobol_points(2**k, 1024))
    cells = np.sort(np.floor(points * 2**k).astype(np.int64), axis=0)
    expected = np.arange(2**k)[:, None]
    assert np.array_equal(cells, np.broadcast_to(expected, cells.shape))


# --- pricing ---------------------------------------------------------------------------------


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("option_type", [CALL, PUT])
def test_european_within_4_standard_errors(option_type, seed):
    result = qmc(option_type, seed=seed)
    exact = mcpricer.black_scholes(option_type=option_type, **BASE)
    assert result.n_paths == 2**14 * 16
    assert abs(result.estimate - exact) < 4.0 * result.std_error


@pytest.mark.parametrize("bridge", [True, False])
@pytest.mark.parametrize("n_steps", [1, 7, 16, 64])
@pytest.mark.parametrize("option_type", [CALL, PUT])
def test_geometric_asian_within_4_standard_errors(option_type, n_steps, bridge):
    result = qmc(
        option_type, n_steps=n_steps, payoff=Payoff.GEOMETRIC_ASIAN, brownian_bridge=bridge
    )
    exact = mcpricer.geometric_asian(option_type=option_type, **BASE, n_steps=n_steps)
    assert abs(result.estimate - exact) < 4.0 * result.std_error


@pytest.mark.parametrize("option_type", [CALL, PUT])
def test_arithmetic_asian_agrees_with_monte_carlo(option_type):
    q = qmc(option_type, n_steps=12, payoff=Payoff.ARITHMETIC_ASIAN)
    mc = mcpricer.price_asian(
        option_type=option_type, **BASE, n_steps=12, n_paths=400_000, seed=3, control_variate=True
    )
    assert abs(q.estimate - mc.estimate) < 4.0 * math.hypot(q.std_error, mc.std_error)


def test_qmc_error_bar_beats_monte_carlo_at_equal_path_count():
    q = qmc(CALL)
    mc = mcpricer.price_european(option_type=CALL, **BASE, n_paths=q.n_paths, seed=1)
    assert q.std_error < 0.5 * mc.std_error


def test_bit_identical_across_threads():
    def run(n_threads):
        r = qmc(
            n_steps=32,
            n_points=40_000,
            reps=4,
            payoff=Payoff.ARITHMETIC_ASIAN,
            n_threads=n_threads,
        )
        return r.estimate, r.std_error

    ref = run(1)
    for n_threads in [2, 4, 8]:
        assert run(n_threads) == ref


def test_different_seeds_give_different_shifts():
    assert qmc(seed=1).estimate != qmc(seed=2).estimate


# --- validation ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"n_steps": 0}, "n_steps"),
        ({"n_steps": 1025}, "n_steps"),
        ({"n_points": 0}, "n_points"),
        ({"n_points": 2**32 + 1}, "n_points"),
        ({"reps": 1}, "n_replications"),
        ({"reps": 4097}, "n_replications"),
        ({"n_threads": -1}, "n_threads"),
    ],
)
def test_rejects_bad_input(kwargs, match):
    with pytest.raises(ValueError, match=match):
        qmc(**kwargs)
