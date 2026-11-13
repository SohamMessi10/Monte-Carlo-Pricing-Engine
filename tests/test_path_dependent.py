"""Milestone 4: arithmetic/geometric Asian and discretely monitored up-and-out options."""

import math

import pytest

import mcpricer
from mcpricer import Average, OptionType

CALL, PUT = OptionType.CALL, OptionType.PUT
BASE = {"spot": 100.0, "strike": 100.0, "rate": 0.05, "vol": 0.2, "maturity": 1.0}
N_PATHS = 100_000
CASES = [
    pytest.param(BASE, id="atm"),
    pytest.param({**BASE, "strike": 90.0}, id="low-strike"),
    pytest.param({**BASE, "strike": 120.0, "vol": 0.35, "maturity": 2.0}, id="high-strike-long"),
    pytest.param({**BASE, "rate": -0.01, "maturity": 0.25}, id="negative-rate-short"),
]


def norm_cdf(x):
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def asian(option_type, params, *, n_steps=12, seed=1, n_paths=N_PATHS, **kwargs):
    return mcpricer.price_asian(
        option_type=option_type, **params, n_steps=n_steps, n_paths=n_paths, seed=seed, **kwargs
    )


def up_and_out(option_type, params, barrier, *, n_steps=50, seed=1, n_paths=N_PATHS, **kwargs):
    return mcpricer.price_up_and_out(
        option_type=option_type,
        **params,
        barrier=barrier,
        n_steps=n_steps,
        n_paths=n_paths,
        seed=seed,
        **kwargs,
    )


# --- geometric Asian closed form -----------------------------------------------------------


@pytest.mark.parametrize("option_type", [CALL, PUT])
@pytest.mark.parametrize("params", CASES)
def test_geometric_closed_form_with_one_step_is_black_scholes(params, option_type):
    geo = mcpricer.geometric_asian(option_type=option_type, **params, n_steps=1)
    bs = mcpricer.black_scholes(option_type=option_type, **params)
    assert geo == pytest.approx(bs, rel=1e-12)


@pytest.mark.parametrize("n_steps", [1, 12, 52, 250])
@pytest.mark.parametrize("option_type", [CALL, PUT])
@pytest.mark.parametrize("params", CASES)
def test_cpp_and_python_closed_forms_agree(params, option_type, n_steps):
    py = mcpricer.geometric_asian(option_type=option_type, **params, n_steps=n_steps)
    cpp = mcpricer._core._geometric_asian(option_type=option_type, **params, n_steps=n_steps)
    assert cpp == pytest.approx(py, rel=1e-12)


# --- Asian Monte Carlo -----------------------------------------------------------------------


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("option_type", [CALL, PUT])
@pytest.mark.parametrize("params", CASES)
def test_geometric_mc_within_4_standard_errors(params, option_type, seed):
    result = asian(option_type, params, seed=seed, average=Average.GEOMETRIC)
    exact = mcpricer.geometric_asian(option_type=option_type, **params, n_steps=12)
    assert abs(result.estimate - exact) < 4.0 * result.std_error


@pytest.mark.parametrize("option_type", [CALL, PUT])
def test_arithmetic_with_one_step_is_european(option_type):
    result = asian(option_type, BASE, n_steps=1, n_paths=200_000)
    bs = mcpricer.black_scholes(option_type=option_type, **BASE)
    assert abs(result.estimate - bs) < 4.0 * result.std_error


@pytest.mark.parametrize("params", CASES)
def test_arithmetic_call_at_least_geometric_on_same_paths(params):
    # AM >= GM on every path, and the call payoff is increasing in the average.
    arithmetic = asian(CALL, params, seed=4)
    geometric = asian(CALL, params, seed=4, average=Average.GEOMETRIC)
    assert arithmetic.estimate >= geometric.estimate


@pytest.mark.parametrize("option_type", [CALL, PUT])
@pytest.mark.parametrize("params", CASES)
def test_control_variate_agrees_with_plain_and_reduces_error(params, option_type):
    plain = asian(option_type, params, seed=5)
    cv_same_seed = asian(option_type, params, seed=5, control_variate=True)
    cv = asian(option_type, params, seed=6, control_variate=True)
    # Different seeds, so plain and cv are independent estimates of the same price.
    assert abs(cv.estimate - plain.estimate) < 4.0 * math.hypot(cv.std_error, plain.std_error)
    assert cv_same_seed.std_error < plain.std_error


def test_control_variate_requires_arithmetic_average():
    with pytest.raises(ValueError, match="control_variate"):
        asian(CALL, BASE, average=Average.GEOMETRIC, control_variate=True)


@pytest.mark.parametrize("n_steps", [0, -3, 100_001])
def test_rejects_bad_step_count(n_steps):
    with pytest.raises(ValueError, match="n_steps"):
        asian(CALL, BASE, n_steps=n_steps, n_paths=100)
    with pytest.raises(ValueError, match="n_steps"):
        up_and_out(CALL, BASE, 150.0, n_steps=n_steps, n_paths=100)


# --- up-and-out barrier ----------------------------------------------------------------------


@pytest.mark.parametrize("option_type", [CALL, PUT])
def test_barrier_price_is_monotone_in_barrier_and_bounded_by_vanilla(option_type):
    # Same seed and grid: every path is the same for every barrier level, so raising the
    # barrier can only keep more paths alive. A barrier of 1e12 never knocks out (vanilla).
    barriers = [101.0, 105.0, 110.0, 120.0, 140.0, 200.0, 1e12]
    prices = [up_and_out(option_type, BASE, h, seed=8).estimate for h in barriers]
    assert prices == sorted(prices)
    assert prices[0] < prices[-1]


@pytest.mark.parametrize("option_type", [CALL, PUT])
@pytest.mark.parametrize("params", CASES)
def test_barrier_at_infinity_is_vanilla(params, option_type):
    result = up_and_out(option_type, params, 1e12, seed=2)
    bs = mcpricer.black_scholes(option_type=option_type, **params)
    assert abs(result.estimate - bs) < 4.0 * result.std_error


@pytest.mark.parametrize(("strike", "barrier"), [(100.0, 130.0), (90.0, 120.0), (110.0, 115.0)])
def test_single_monitoring_date_matches_closed_form(strike, barrier):
    # Monitored only at T, the call pays (S_T - K) 1{S_T < H}: a call spread minus a digital,
    # C(K) - C(H) - (H - K) e^{-rT} N(d2(H)).
    p = {**BASE, "strike": strike}
    r, vol, t = p["rate"], p["vol"], p["maturity"]
    d2_h = (math.log(p["spot"] / barrier) + (r - 0.5 * vol * vol) * t) / (vol * math.sqrt(t))
    exact = (
        mcpricer.black_scholes(option_type=CALL, **p)
        - mcpricer.black_scholes(option_type=CALL, **{**p, "strike": barrier})
        - (barrier - strike) * math.exp(-r * t) * norm_cdf(d2_h)
    )
    result = up_and_out(CALL, p, barrier, n_steps=1, n_paths=200_000, seed=3)
    assert abs(result.estimate - exact) < 4.0 * result.std_error


@pytest.mark.parametrize("barrier", [100.0, 50.0, 0.0, -1.0, math.nan, math.inf])
def test_rejects_bad_barrier(barrier):
    with pytest.raises(ValueError, match="barrier"):
        up_and_out(CALL, BASE, barrier, n_paths=100)


# --- determinism -----------------------------------------------------------------------------


def test_bit_identical_across_threads():
    def run(n_threads):
        a = asian(CALL, BASE, n_paths=50_001, n_threads=n_threads, control_variate=True)
        b = up_and_out(PUT, BASE, 120.0, n_paths=50_001, n_threads=n_threads)
        return a.estimate, a.std_error, b.estimate, b.std_error

    ref = run(1)
    for n_threads in [2, 4, 8]:
        assert run(n_threads) == ref
