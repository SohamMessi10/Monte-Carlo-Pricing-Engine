"""Milestone 1: European options under GBM, checked against Black–Scholes."""

import math

import numpy as np
import pytest
from scipy.special import ndtri

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


def mc(option_type, params, *, seed, n_paths=N_PATHS):
    return mcpricer.price_european(option_type=option_type, **params, n_paths=n_paths, seed=seed)


def bs(option_type, params):
    return mcpricer.black_scholes(option_type=option_type, **params)


def test_black_scholes_textbook_values():
    assert bs(CALL, BASE) == pytest.approx(10.4506, abs=1e-4)
    assert bs(PUT, BASE) == pytest.approx(5.5735, abs=1e-4)


@pytest.mark.parametrize("params", CASES)
def test_black_scholes_put_call_parity(params):
    forward = params["spot"] - params["strike"] * math.exp(-params["rate"] * params["maturity"])
    assert bs(CALL, params) - bs(PUT, params) == pytest.approx(forward, rel=1e-12, abs=1e-12)


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("option_type", [CALL, PUT])
@pytest.mark.parametrize("params", CASES)
def test_mc_within_4_standard_errors(params, option_type, seed):
    result = mc(option_type, params, seed=seed)
    assert abs(result.estimate - bs(option_type, params)) < 4.0 * result.std_error


@pytest.mark.parametrize("params", CASES)
def test_mc_put_call_parity(params):
    call = mc(CALL, params, seed=7)
    put = mc(PUT, params, seed=7)
    forward = params["spot"] - params["strike"] * math.exp(-params["rate"] * params["maturity"])
    # sd(C - P) <= sd(C) + sd(P), so this bound holds whatever the correlation.
    assert abs((call.estimate - put.estimate) - forward) < 4.0 * (call.std_error + put.std_error)


def test_same_seed_is_bit_identical():
    a = mc(CALL, BASE, seed=123)
    b = mc(CALL, BASE, seed=123)
    assert (a.estimate, a.std_error) == (b.estimate, b.std_error)


def test_different_seeds_differ():
    assert mc(CALL, BASE, seed=1).estimate != mc(CALL, BASE, seed=2).estimate


@pytest.mark.parametrize("n_paths", [2, 16_383, 16_384, 16_385, 100_001])
def test_result_fields(n_paths):
    result = mc(CALL, {**BASE, "strike": 50.0}, seed=5, n_paths=n_paths)
    assert result.n_paths == n_paths
    assert result.std_error > 0
    assert result.elapsed_seconds >= 0
    assert "PricingResult(estimate=" in repr(result)


@pytest.mark.parametrize("bad", [0.0, -1.0, math.nan, math.inf])
@pytest.mark.parametrize("field", ["spot", "strike", "vol", "maturity"])
def test_rejects_non_positive_inputs(field, bad):
    params = {**BASE, field: bad}
    with pytest.raises(ValueError, match=field):
        mc(CALL, params, seed=1, n_paths=100)
    with pytest.raises(ValueError, match=field):
        bs(CALL, params)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_rejects_non_finite_rate(bad):
    params = {**BASE, "rate": bad}
    with pytest.raises(ValueError, match="rate"):
        mc(CALL, params, seed=1, n_paths=100)
    with pytest.raises(ValueError, match="rate"):
        bs(CALL, params)


@pytest.mark.parametrize("n_paths", [-5, 0, 1])
def test_rejects_too_few_paths(n_paths):
    with pytest.raises(ValueError, match="n_paths"):
        mc(CALL, BASE, seed=1, n_paths=n_paths)


def test_rejects_wrong_option_type():
    with pytest.raises(TypeError):
        mcpricer.price_european(option_type="call", **BASE, n_paths=100, seed=1)


def test_norm_inv_matches_scipy():
    tails = np.logspace(-300, -1, 300)
    p = np.concatenate([tails, np.linspace(0.01, 0.99, 981), 1.0 - np.logspace(-15, -1, 50)])
    ours = np.array([mcpricer._core._norm_inv(x) for x in p])
    np.testing.assert_allclose(ours, ndtri(p), rtol=1e-12, atol=1e-15)


def test_norm_inv_center_and_domain():
    assert mcpricer._core._norm_inv(0.5) == 0.0
    for bad in [0.0, 1.0, -0.1, math.nan]:
        with pytest.raises(ValueError, match="open interval"):
            mcpricer._core._norm_inv(bad)
