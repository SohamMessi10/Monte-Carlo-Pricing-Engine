"""Milestone 6: Heston, full-truncation Euler Monte Carlo against the semi-analytic price."""

import math

import pytest

import mcpricer
from mcpricer import OptionType

CALL, PUT = OptionType.CALL, OptionType.PUT
CONTRACT = {"spot": 100.0, "strike": 100.0, "rate": 0.03, "maturity": 1.0}
MODELS = [
    # 2 kappa theta = 0.16 > xi^2 = 0.09: Feller condition holds, v stays positive.
    pytest.param({"v0": 0.04, "kappa": 2.0, "theta": 0.04, "xi": 0.3, "rho": -0.7}, id="feller"),
    # 2 kappa theta = 0.04 < xi^2 = 1: v hits 0 often; the hard case for Euler schemes.
    pytest.param(
        {"v0": 0.04, "kappa": 0.5, "theta": 0.04, "xi": 1.0, "rho": -0.9}, id="feller-violated"
    ),
    pytest.param({"v0": 0.09, "kappa": 1.0, "theta": 0.06, "xi": 0.5, "rho": 0.3}, id="pos-rho"),
]


def mc(option_type, model, *, n_steps, n_paths=200_000, seed=1, contract=CONTRACT, **kw):
    return mcpricer.price_heston(
        option_type=option_type,
        **contract,
        **model,
        n_steps=n_steps,
        n_paths=n_paths,
        seed=seed,
        **kw,
    )


def reference(option_type, model, contract=CONTRACT):
    return mcpricer.heston(option_type=option_type, **contract, **model)


# --- semi-analytic reference -----------------------------------------------------------------


@pytest.mark.parametrize("rho", [-0.5, 0.0, 0.5])
@pytest.mark.parametrize("option_type", [CALL, PUT])
@pytest.mark.parametrize("strike", [80.0, 100.0, 120.0])
def test_reference_tends_to_black_scholes_as_xi_vanishes(strike, option_type, rho):
    # v0 = theta and xi -> 0: the variance stays at theta, so Heston is Black-Scholes with
    # vol sqrt(theta). The Heston correction is O(rho xi), well below 1e-3 here; a smaller xi
    # would lose digits to cancellation in (beta - d) / xi^2.
    contract = {**CONTRACT, "strike": strike}
    model = {"v0": 0.04, "kappa": 1.0, "theta": 0.04, "xi": 1e-4, "rho": rho}
    bs = mcpricer.black_scholes(option_type=option_type, **contract, vol=0.2)
    assert reference(option_type, model, contract) == pytest.approx(bs, abs=1e-3)


@pytest.mark.parametrize("model", MODELS)
def test_reference_put_call_parity_and_bounds(model):
    call, put = reference(CALL, model), reference(PUT, model)
    s, k, r, t = (CONTRACT[x] for x in ("spot", "strike", "rate", "maturity"))
    assert call - put == pytest.approx(s - k * math.exp(-r * t), abs=1e-10)
    assert max(s - k * math.exp(-r * t), 0.0) < call < s


# --- Monte Carlo -----------------------------------------------------------------------------


@pytest.mark.parametrize("option_type", [CALL, PUT])
@pytest.mark.parametrize(
    ("model", "n_steps"),
    [
        (MODELS[0].values[0], 200),
        # Measured (benchmarks/heston_convergence.py, 1M paths): the call bias is +0.044 at
        # 256 steps and +0.009 at 1024 for this model, so 200 steps is not fine enough here.
        (MODELS[1].values[0], 1024),
        (MODELS[2].values[0], 200),
    ],
    ids=["feller", "feller-violated", "pos-rho"],
)
def test_fine_grid_within_4_standard_errors(model, n_steps, option_type):
    result = mc(option_type, model, n_steps=n_steps)
    assert abs(result.estimate - reference(option_type, model)) < 4.0 * result.std_error


def test_bias_shrinks_as_steps_increase():
    # Feller violated: the bias is far larger than the statistical error on coarse grids
    # (measured +1.07, +0.22, +0.044 at 16, 64, 256 steps; SE here is about 0.011).
    model = MODELS[1].values[0]
    exact = reference(CALL, model)
    errors = [abs(mc(CALL, model, n_steps=n).estimate - exact) for n in (16, 64, 256)]
    assert errors[0] > errors[1] > errors[2]


@pytest.mark.parametrize("option_type", [CALL, PUT])
def test_one_step_is_black_scholes_with_initial_vol(option_type):
    # One Euler step: log S_T = log S_0 + (r - v0/2) T + sqrt(v0 T) Z, exactly lognormal.
    model = {"v0": 0.09, "kappa": 1.0, "theta": 0.04, "xi": 0.8, "rho": -0.5}
    result = mc(option_type, model, n_steps=1)
    bs = mcpricer.black_scholes(option_type=option_type, **CONTRACT, vol=0.3)
    assert abs(result.estimate - bs) < 4.0 * result.std_error


def test_bit_identical_across_threads():
    model = MODELS[1].values[0]
    ref = mc(CALL, model, n_steps=20, n_paths=50_001, n_threads=1)
    for n_threads in [2, 4, 8]:
        r = mc(CALL, model, n_steps=20, n_paths=50_001, n_threads=n_threads)
        assert (r.estimate, r.std_error) == (ref.estimate, ref.std_error)


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("v0", -0.01),
        ("kappa", 0.0),
        ("theta", -1.0),
        ("xi", 0.0),
        ("rho", 1.5),
        ("rho", math.nan),
    ],
)
def test_rejects_bad_model_parameters(field, bad):
    model = {**MODELS[0].values[0], field: bad}
    with pytest.raises(ValueError, match=field):
        mc(CALL, model, n_steps=10, n_paths=100)
    with pytest.raises(ValueError, match=field):
        reference(CALL, model)


@pytest.mark.parametrize("n_steps", [0, 100_001])
def test_rejects_bad_step_count(n_steps):
    with pytest.raises(ValueError, match="n_steps"):
        mc(CALL, MODELS[0].values[0], n_steps=n_steps, n_paths=100)
