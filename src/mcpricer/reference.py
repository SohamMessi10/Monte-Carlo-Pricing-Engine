"""Closed-form reference prices used to validate the Monte Carlo engine."""

import cmath
import math

from ._core import OptionType


def _norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _validate(spot, strike, rate, vol, maturity):
    for name, value in (("spot", spot), ("strike", strike), ("vol", vol), ("maturity", maturity)):
        if not (value > 0 and math.isfinite(value)):
            raise ValueError(f"{name} must be positive and finite, got {value!r}")
    if not math.isfinite(rate):
        raise ValueError(f"rate must be finite, got {rate!r}")


def black_scholes(
    *,
    option_type: OptionType,
    spot: float,
    strike: float,
    rate: float,
    vol: float,
    maturity: float,
) -> float:
    """Black–Scholes price of a European call or put (no dividends)."""
    _validate(spot, strike, rate, vol, maturity)
    std_dev = vol * math.sqrt(maturity)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * maturity) / std_dev
    d2 = d1 - std_dev
    discount = math.exp(-rate * maturity)
    if option_type == OptionType.CALL:
        return spot * _norm_cdf(d1) - strike * discount * _norm_cdf(d2)
    return strike * discount * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def geometric_asian(
    *,
    option_type: OptionType,
    spot: float,
    strike: float,
    rate: float,
    vol: float,
    maturity: float,
    n_steps: int,
) -> float:
    """Discretely monitored geometric-average Asian option (Kemna–Vorst closed form).

    The average is over S(t_i), t_i = i T / m for i = 1..m (S_0 excluded). log G is then normal:
      mean     log S_0 + (r - vol^2 / 2) T (m + 1) / (2m)
      variance vol^2 T (m + 1)(2m + 1) / (6 m^2)
    so the price is a Black–Scholes-style formula in G. With m = 1 it is Black–Scholes.
    """
    _validate(spot, strike, rate, vol, maturity)
    if n_steps < 1:
        raise ValueError(f"n_steps must be at least 1, got {n_steps!r}")
    m = n_steps
    mean = math.log(spot) + (rate - 0.5 * vol * vol) * maturity * (m + 1) / (2 * m)
    var = vol * vol * maturity * (m + 1) * (2 * m + 1) / (6 * m * m)
    sd = math.sqrt(var)
    d1 = (mean - math.log(strike) + var) / sd
    d2 = d1 - sd
    forward = math.exp(mean + 0.5 * var)  # E[G]
    discount = math.exp(-rate * maturity)
    if option_type == OptionType.CALL:
        return discount * (forward * _norm_cdf(d1) - strike * _norm_cdf(d2))
    return discount * (strike * _norm_cdf(-d2) - forward * _norm_cdf(-d1))


def _heston_cf(u, *, spot, rate, maturity, v0, kappa, theta, xi, rho):
    """E[exp(i u log S_T)] in the "little Heston trap" form (Albrecher et al. 2007).

    The original Heston (1993) form uses g' = 1/g and exp(+dT); its complex logarithm can jump
    branches for long maturities. This form keeps |g e^{-dT}| < 1 and stays continuous.
    """
    iu = 1j * u
    beta = kappa - rho * xi * iu
    d = cmath.sqrt(beta * beta + xi * xi * (iu + u * u))
    g = (beta - d) / (beta + d)
    e = cmath.exp(-d * maturity)
    c = (kappa * theta / (xi * xi)) * (
        (beta - d) * maturity - 2.0 * cmath.log((1.0 - g * e) / (1.0 - g))
    )
    dv = (beta - d) / (xi * xi) * (1.0 - e) / (1.0 - g * e)
    return cmath.exp(iu * (math.log(spot) + rate * maturity) + c + dv * v0)


def heston(
    *,
    option_type: OptionType,
    spot: float,
    strike: float,
    rate: float,
    maturity: float,
    v0: float,
    kappa: float,
    theta: float,
    xi: float,
    rho: float,
) -> float:
    """Semi-analytic Heston price of a European call or put (needs scipy).

    Call = S_0 P_1 - K e^{-rT} P_2 with the Gil-Pelaez inversions
      P_2 = 1/2 + (1/pi) int_0^inf Re[e^{-iu log K} phi(u) / (iu)] du
      P_1 = 1/2 + (1/pi) int_0^inf Re[e^{-iu log K} phi(u - i) / (iu phi(-i))] du,
    phi(-i) = S_0 e^{rT}. The put follows from put-call parity.
    """
    from scipy.integrate import quad

    for name, value in (("spot", spot), ("strike", strike), ("maturity", maturity)):
        if not (value > 0 and math.isfinite(value)):
            raise ValueError(f"{name} must be positive and finite, got {value!r}")
    for name, value in (("kappa", kappa), ("theta", theta), ("xi", xi)):
        if not (value > 0 and math.isfinite(value)):
            raise ValueError(f"{name} must be positive and finite, got {value!r}")
    if not (v0 >= 0 and math.isfinite(v0)):
        raise ValueError(f"v0 must be non-negative and finite, got {v0!r}")
    if not math.isfinite(rate):
        raise ValueError(f"rate must be finite, got {rate!r}")
    if not -1.0 <= rho <= 1.0:
        raise ValueError(f"rho must be in [-1, 1], got {rho!r}")

    model = {
        "spot": spot,
        "rate": rate,
        "maturity": maturity,
        "v0": v0,
        "kappa": kappa,
        "theta": theta,
        "xi": xi,
        "rho": rho,
    }
    log_k = math.log(strike)
    forward = spot * math.exp(rate * maturity)  # phi(-i)

    def p2_integrand(u):
        return (cmath.exp(-1j * u * log_k) * _heston_cf(u, **model) / (1j * u)).real

    def p1_integrand(u):
        cf = _heston_cf(u - 1j, **model) / forward
        return (cmath.exp(-1j * u * log_k) * cf / (1j * u)).real

    opts = {"limit": 500, "epsabs": 1e-12, "epsrel": 1e-10}
    p1 = 0.5 + quad(p1_integrand, 0.0, math.inf, **opts)[0] / math.pi
    p2 = 0.5 + quad(p2_integrand, 0.0, math.inf, **opts)[0] / math.pi
    discount = math.exp(-rate * maturity)
    call = spot * p1 - strike * discount * p2
    if option_type == OptionType.CALL:
        return call
    return call - spot + strike * discount
