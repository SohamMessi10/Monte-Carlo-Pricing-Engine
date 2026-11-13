"""Milestone 3: antithetic variates and the S_T control variate."""

import math

import pytest

import mcpricer
from mcpricer import OptionType

CALL, PUT = OptionType.CALL, OptionType.PUT
BASE = {"spot": 100.0, "strike": 100.0, "rate": 0.05, "vol": 0.2, "maturity": 1.0}
N_PATHS = 200_000
CASES = [
    pytest.param(BASE, id="atm"),
    pytest.param({**BASE, "strike": 80.0}, id="low-strike"),
    pytest.param({**BASE, "strike": 130.0, "vol": 0.35, "maturity": 2.0}, id="high-strike-long"),
    pytest.param({**BASE, "rate": -0.01, "maturity": 0.25}, id="negative-rate-short"),
]
METHODS = [
    pytest.param({"antithetic": True}, id="antithetic"),
    pytest.param({"control_variate": True}, id="control"),
    pytest.param({"antithetic": True, "control_variate": True}, id="both"),
]


def mc(option_type, params, *, seed, n_paths=N_PATHS, **method):
    return mcpricer.price_european(
        option_type=option_type, **params, n_paths=n_paths, seed=seed, **method
    )


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("option_type", [CALL, PUT])
@pytest.mark.parametrize("params", CASES)
def test_within_4_standard_errors(params, option_type, seed, method):
    result = mc(option_type, params, seed=seed, **method)
    assert result.n_paths == N_PATHS
    exact = mcpricer.black_scholes(option_type=option_type, **params)
    assert abs(result.estimate - exact) < 4.0 * result.std_error


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("option_type", [CALL, PUT])
def test_reduces_standard_error_at_equal_path_count(option_type, method):
    plain = mc(option_type, BASE, seed=5)
    reduced = mc(option_type, BASE, seed=5, **method)
    assert reduced.std_error < plain.std_error


def test_control_variate_is_exact_for_a_linear_payoff():
    # With a tiny strike every call finishes in the money, so the payoff S_T - K is linear in
    # the control S_T. The regression then removes all the noise: price = S_0 - K e^{-rT}.
    params = {**BASE, "strike": 1e-6}
    result = mc(CALL, params, seed=9, control_variate=True)
    exact = params["spot"] - params["strike"] * math.exp(-params["rate"] * params["maturity"])
    # Plain MC has a relative error near 4e-4 here; what is left is floating-point rounding
    # (the variance is a difference of two sums near 1e8, so it keeps ~1e-7 of noise).
    assert result.estimate == pytest.approx(exact, rel=1e-10)
    assert result.std_error < 1e-5


@pytest.mark.parametrize("method", METHODS)
def test_bit_identical_across_threads(method):
    ref = mc(CALL, BASE, seed=13, n_paths=250_002, n_threads=1, **method)
    for n_threads in [2, 4, 8]:
        r = mc(CALL, BASE, seed=13, n_paths=250_002, n_threads=n_threads, **method)
        assert (r.estimate, r.std_error) == (ref.estimate, ref.std_error)


@pytest.mark.parametrize("n_paths", [2, 5, 1001])
def test_antithetic_rejects_bad_path_count(n_paths):
    with pytest.raises(ValueError, match="antithetic"):
        mc(CALL, BASE, seed=1, n_paths=n_paths, antithetic=True)


@pytest.mark.parametrize(
    ("n_paths", "method"),
    [(2, {"control_variate": True}), (4, {"control_variate": True, "antithetic": True})],
)
def test_control_variate_rejects_too_few_samples(n_paths, method):
    with pytest.raises(ValueError, match="control_variate"):
        mc(CALL, BASE, seed=1, n_paths=n_paths, **method)
